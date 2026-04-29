import asyncio
import logging
from typing import Any, Dict, List
from sqlmodel import select
from core.config import settings
from core.database import async_session_maker
from models import Product
from datetime import datetime, timedelta
from parsers.onliner import OnlinerParser
from core.logger import logger
from services.backup_service import backup_service
from services.supplier_sync_service import SupplierSyncService

class SchedulerService:
    def __init__(self):
        self.parser = OnlinerParser()

    async def get_sync_mode(self) -> int:
        """
        Получает режим синхронизации из базы данных.
        0 - Выкл (Disabled)
        1 - Только хиты (Hits Only)
        2 - Все (All)
        """
        from models import GlobalConfig
        async with async_session_maker() as session:
            stmt = select(GlobalConfig).where(GlobalConfig.key == "sync_mode")
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()
            if config:
                try:
                    return int(config.value)
                except ValueError:
                    return 0
            return 2 # По умолчанию - все, если не настроено

    async def _get_global_config_value(self, key: str, default: str) -> str:
        from models import GlobalConfig

        async with async_session_maker() as session:
            stmt = select(GlobalConfig).where(GlobalConfig.key == key)
            result = await session.execute(stmt)
            cfg = result.scalar_one_or_none()
            return cfg.value if cfg and cfg.value is not None else default

    async def update_all_prices(self):
        """
        Проходит по товарам и обновляет их цены в зависимости от режима.
        """
        mode = await self.get_sync_mode()
        if mode == 0:
            logger.info("Price sync is DISABLED globally.")
            return

        logger.info(f"Starting scheduled price update (Mode: {mode})...")
        async with async_session_maker() as session:
            if mode == 1:
                # Только товары с тегом "hit" (Хит продаж)
                from models import Tag
                stmt = (
                    select(
                        Product.id.label("id"),
                        Product.title.label("title"),
                        Product.source_url.label("source_url"),
                        Product.price.label("price"),
                    )
                    .join(Product.tags)
                    .where(Tag.slug == "hit", Product.source_url != None)
                )
            else:
                # Все товары с URL
                stmt = select(
                    Product.id.label("id"),
                    Product.title.label("title"),
                    Product.source_url.label("source_url"),
                    Product.price.label("price"),
                ).where(Product.source_url != None)

            result = await session.execute(stmt)
            product_rows = [dict(row) for row in result.mappings().unique().all()]

        updates: List[Dict[str, Any]] = []
        for product in product_rows:
            try:
                logger.info(f"Checking price for: {product['title']}")
                data = await self.parser.parse(product["source_url"])
                new_price = data.get("price")

                if new_price and new_price != product["price"]:
                    logger.info(
                        f"Price updated for {product['title']}: {product['price']} -> {new_price}"
                    )
                    updates.append(
                        {
                            "id": product["id"],
                            "old_price": product["price"],
                            "new_price": new_price,
                        }
                    )

                # Sleep to avoid rate limiting
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Error updating price for {product['title']}: {e}")

        if updates:
            updated_count = 0
            async with async_session_maker() as session:
                for item in updates:
                    product = await session.get(Product, item["id"])
                    if not product:
                        continue
                    product.old_price = item["old_price"]
                    product.price = item["new_price"]
                    session.add(product)
                    updated_count += 1
                if updated_count:
                    await session.commit()
            logger.info(f"Finished price update. {updated_count} products updated.")
        else:
            logger.info("Finished price update. No changes found.")

    async def start_loop(self, interval_hours: int = 6):
        """
        Запускает фоновые задачи: синхронизация цен и автоматизация CRM.
        """
        logger.info(f"Scheduler started. Price Interval: {interval_hours}h.")
        
        # Run price sync loop
        asyncio.create_task(self._price_sync_loop(interval_hours))
        
        # Run stalled deal loop (once a day)
        asyncio.create_task(self._stalled_deal_loop())

        # Run backup loop (once a day)
        if settings.is_production:
            asyncio.create_task(self._backup_loop())
        else:
            logger.warning(
                "Daily backup loop is disabled for ENVIRONMENT=%s. "
                "Set ENVIRONMENT=production to enable scheduled Drive backups.",
                settings.ENVIRONMENT,
            )

        # Run lead archive loop (once a day)
        asyncio.create_task(self._lead_archive_loop())

        # Run supplier sheets sync loop
        asyncio.create_task(self._supplier_sync_loop())

        # Keep the main loop alive 
        while True:
            await asyncio.sleep(3600)

    async def _price_sync_loop(self, interval_hours: int):
        while True:
            try:
                await self.update_all_prices()
            except Exception as e:
                logger.error(f"Critical error in price sync loop: {e}")
            await asyncio.sleep(interval_hours * 3600)

    async def _stalled_deal_loop(self):
        """Checks for stalled deals once every 24 hours."""
        while True:
            try:
                logger.info("⏳ Checking Stalled Deals...")
                async with async_session_maker() as session:
                    await self.check_stalled_deals(session)
                logger.info("✅ Stalled Deal Check Done. Sleeping 24 hours.")
                await asyncio.sleep(24 * 3600)
            except Exception as e:
                logger.error(f"❌ Stalled Deal Check Error: {e}")
                await asyncio.sleep(3600)  # Retry in 1 hour

    async def check_stalled_deals(self, session):
        """
        Moves deals from NEGOTIATION to DEFERRED if updated_at > 14 days ago.
        """
        from models import Order, OrderStatus
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=14)
        
        # Select orders in Negotiation older than 14 days
        stmt = select(Order).where(
            Order.status == OrderStatus.NEGOTIATION,
            Order.updated_at < cutoff_date
        )
        res = await session.execute(stmt)
        stalled_orders = res.scalars().all()
        
        for order in stalled_orders:
            logger.warning(f"⚠️ Deferring Stalled Order #{order.id} (Last update: {order.updated_at})")
            order.status = OrderStatus.DEFERRED
            order.technical_meta = {**(order.technical_meta or {}), "deferred_reason": "Auto-deferred: >14 days in Negotiation"}
            order.next_followup_date = datetime.now() + timedelta(days=7)
            session.add(order)
            
        if stalled_orders:
            await session.commit()
            logger.info(f"🔄 Auto-deferred {len(stalled_orders)} stalled orders.")

    async def _backup_loop(self):
        """Runs database backup every day at 3:00 AM."""
        while True:
            try:
                now = datetime.now()
                target_time = now.replace(hour=3, minute=0, second=0, microsecond=0)
                
                # If 3 AM has already passed today, schedule for tomorrow
                if now >= target_time:
                    target_time += timedelta(days=1)
                
                wait_seconds = (target_time - now).total_seconds()
                logger.info(f"⏳ Next Backup scheduled for {target_time} (in {wait_seconds/3600:.2f} hours)")
                
                await asyncio.sleep(wait_seconds)
                
                logger.info("⏳ Starting Daily Backup (DB + Media)...")
                # We need to run sync method in thread executor because subprocess is blocking
                await asyncio.to_thread(backup_service.perform_backup, cleanup=True)
                logger.info("✅ Daily Backup Completed.")
                
            except Exception as e:
                logger.error(f"❌ Backup Loop Error: {e}")
                # Retry in 1 hour if it crashed to avoid loop spam
                await asyncio.sleep(3600)

    async def _lead_archive_loop(self):
        """Archives lost/spam leads older than 90 days once every 24 hours."""
        while True:
            try:
                logger.info("⏳ Lead archive job started...")
                from services.lead_service import LeadService
                async with async_session_maker() as session:
                    archived_count = await LeadService.archive_expired_lost_leads(session=session, older_than_days=90)
                logger.info(f"✅ Lead archive job done. Archived: {archived_count}")
                await asyncio.sleep(24 * 3600)
            except Exception as e:
                logger.error(f"❌ Lead archive loop error: {e}")
                await asyncio.sleep(3600)

    async def _supplier_sync_loop(self):
        while True:
            try:
                enabled_value = await self._get_global_config_value("supplier_sync_enabled", "true")
                enabled = str(enabled_value).strip().lower() in {"1", "true", "yes", "on"}
                if enabled:
                    interval_raw = await self._get_global_config_value("supplier_sync_interval_minutes", "60")
                    try:
                        interval_minutes = max(5, int(interval_raw))
                    except ValueError:
                        interval_minutes = 60

                    logger.info("⏳ Supplier sync job started...")
                    async with async_session_maker() as session:
                        results = await SupplierSyncService.sync_all_active_sources(session)
                    logger.info(f"✅ Supplier sync done. Sources: {len(results)}")
                    await asyncio.sleep(interval_minutes * 60)
                else:
                    await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"❌ Supplier sync loop error: {e}")
                await asyncio.sleep(300)

scheduler_service = SchedulerService()
