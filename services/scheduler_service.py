import asyncio
import logging
from typing import List
from sqlmodel import select
from core.database import async_session_maker
from models import Product
from parsers.onliner import OnlinerParser
from core.logger import logger

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
                stmt = select(Product).join(Product.tags).where(Tag.slug == "hit", Product.source_url != None)
            else:
                # Все товары с URL
                stmt = select(Product).where(Product.source_url != None)
            
            result = await session.execute(stmt)
            products = result.scalars().unique().all()
            
            updated_count = 0
            for product in products:
                try:
                    logger.info(f"Checking price for: {product.title}")
                    data = await self.parser.parse(product.source_url)
                    new_price = data.get('price')
                    
                    if new_price and new_price != product.price:
                        logger.info(f"Price updated for {product.title}: {product.price} -> {new_price}")
                        product.old_price = product.price
                        product.price = new_price
                        session.add(product)
                        updated_count += 1
                    
                    # Sleep to avoid rate limiting
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Error updating price for {product.title}: {e}")

            if updated_count > 0:
                await session.commit()
                logger.info(f"Finished price update. {updated_count} products updated.")
            else:
                logger.info("Finished price update. No changes found.")

    async def start_loop(self, interval_hours: int = 6):
        """
        Запускает бесконечный цикл обновления цен.
        """
        logger.info(f"Price sync loop started. Interval: {interval_hours} hours.")
        while True:
            try:
                await self.update_all_prices()
            except Exception as e:
                logger.error(f"Critical error in scheduler loop: {e}")
            
            await asyncio.sleep(interval_hours * 3600)

scheduler_service = SchedulerService()
