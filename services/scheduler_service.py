import asyncio
from typing import Any, Dict, List
from sqlmodel import select
from core.config import settings
from core.database import async_session_maker
from models import Product
from datetime import datetime, timedelta
from parsers.onliner import OnlinerParser
from core.logger import logger
from services.backup_service import backup_service
from services.catalog_revision_service import CatalogRevisionService
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
                        Product.slug.label("slug"),
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
                    Product.slug.label("slug"),
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
                            "slug": product["slug"],
                            "old_price": product["price"],
                            "new_price": new_price,
                        }
                    )

                # Sleep to avoid rate limiting
                await asyncio.sleep(2)
            except Exception:
                logger.exception("Error updating price for %s", product["title"])

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
                    await CatalogRevisionService.stage_invalidation(
                        session,
                        reason="scheduled_product_price_sync",
                        product_ids=[item["id"] for item in updates],
                        slugs=[item["slug"] for item in updates],
                    )
                    await session.commit()
            logger.info(f"Finished price update. {updated_count} products updated.")
        else:
            logger.info("Finished price update. No changes found.")

    async def start_loop(self, interval_hours: int = 6):
        """
        Запускает фоновые задачи: синхронизация цен и автоматизация CRM.
        """
        logger.info(f"Scheduler started. Price Interval: {interval_hours}h.")

        tasks = []

        # Run price sync loop
        tasks.append(asyncio.create_task(self._price_sync_loop(interval_hours)))

        # Run stalled deal loop (once a day)
        tasks.append(asyncio.create_task(self._stalled_deal_loop()))

        # Run backup loop (once a day)
        if settings.is_production:
            tasks.append(asyncio.create_task(self._backup_loop()))
        else:
            logger.warning(
                "Daily backup loop is disabled for ENVIRONMENT=%s. "
                "Set ENVIRONMENT=production to enable scheduled Drive backups.",
                settings.ENVIRONMENT,
            )

        # Run lead archive loop (once a day)
        tasks.append(asyncio.create_task(self._lead_archive_loop()))

        # Run supplier sheets sync loop
        tasks.append(asyncio.create_task(self._supplier_sync_loop()))

        # Build internal equipment maintenance reminders once a day.
        tasks.append(asyncio.create_task(self._equipment_maintenance_reminder_loop()))

        # Materialize idempotent staff departure reminders every five minutes.
        tasks.append(asyncio.create_task(self._staff_task_departure_reminder_loop()))

        # Delete external order documents only after their database transaction commits.
        tasks.append(asyncio.create_task(self._order_document_cleanup_loop()))

        # Consume catalog cache invalidations outside producer transactions.
        tasks.append(asyncio.create_task(self._catalog_invalidation_loop()))

        # Recover durable repair AI jobs after request/process failures.
        tasks.append(asyncio.create_task(self._repair_diagnostic_ai_job_loop()))

        # Enforce the documented public-write replay horizon in bounded batches.
        tasks.append(asyncio.create_task(self._public_write_receipt_retention_loop()))

        # Reconcile crash-left installation objects only after a long grace period.
        tasks.append(asyncio.create_task(self._private_attachment_orphan_loop()))

        # Run bank receipt IMAP import loop
        tasks.append(asyncio.create_task(self._bank_mail_import_loop()))

        # Run email lead IMAP import loop. Disabled by default to avoid unplanned AI usage.
        tasks.append(asyncio.create_task(self._email_lead_import_loop()))

        try:
            # Keep the main loop alive.
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _price_sync_loop(self, interval_hours: int):
        while True:
            try:
                await self.update_all_prices()
            except Exception:
                logger.exception("Critical error in price sync loop")
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
            except Exception:
                logger.exception("❌ Stalled Deal Check Error")
                await asyncio.sleep(3600)  # Retry in 1 hour

    async def check_stalled_deals(self, session):
        """
        Marks stale negotiation orders for follow-up instead of moving them to
        a legacy deferred status.
        """
        from models import Order, OrderStatus
        from datetime import datetime, timedelta

        cutoff_date = datetime.now() - timedelta(days=14)
        
        # Select orders in Negotiation older than 14 days
        stmt = select(Order).where(
            Order.status == OrderStatus.NEGOTIATION,
            Order.updated_at < cutoff_date,
            Order.negotiation_status != "follow_up",
        )
        res = await session.execute(stmt)
        stalled_orders = res.scalars().all()
        
        for order in stalled_orders:
            logger.warning(
                "⚠️ Marking stalled negotiation order #%s for follow-up (Last update: %s)",
                order.id,
                order.updated_at,
            )
            order.status = OrderStatus.NEGOTIATION
            order.negotiation_status = "follow_up"
            order.negotiation_status_changed_at = datetime.now()
            order.technical_meta = {
                **(order.technical_meta or {}),
                "stalled_follow_up_reason": "Auto follow-up: >14 days in Negotiation",
            }
            order.next_followup_date = datetime.now() + timedelta(days=7)
            session.add(order)
            
        if stalled_orders:
            await session.commit()
            logger.info("🔄 Marked %s stalled orders for follow-up.", len(stalled_orders))

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
                await self._run_daily_backup()
                
            except Exception:
                logger.exception("❌ Backup Loop Error")
                # Retry in 1 hour if it crashed to avoid loop spam
                await asyncio.sleep(3600)

    async def _run_daily_backup(self) -> None:
        """Run one production backup and reject skipped/partial success states."""
        result = await asyncio.to_thread(backup_service.perform_backup, cleanup=True)
        if result is not True:
            raise RuntimeError("Daily backup was skipped or did not complete")
        logger.info("✅ Daily Backup Completed.")

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
            except Exception:
                logger.exception("❌ Lead archive loop error")
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
            except Exception:
                logger.exception("❌ Supplier sync loop error")
                await asyncio.sleep(300)

    async def _equipment_maintenance_reminder_loop(self):
        while True:
            try:
                from services.warranty_service import WarrantyService

                logger.info("Equipment maintenance reminder job started")
                async with async_session_maker() as session:
                    result = await WarrantyService.generate_maintenance_reminders(session)
                logger.info(
                    "Equipment maintenance reminders done. coverages=%s created=%s skipped=%s",
                    result["coverages"],
                    result["created"],
                    result["skipped"],
                )
                await asyncio.sleep(24 * 3600)
            except Exception:
                logger.exception("Equipment maintenance reminder loop error")
                await asyncio.sleep(3600)

    async def _staff_task_departure_reminder_loop(self):
        from services.staff_task_notification_event_service import (
            StaffTaskNotificationEventService,
        )
        from services.tenant_scope_service import SystemTenantScopeResolver

        while True:
            try:
                async with async_session_maker() as session:
                    tenant_scope = await SystemTenantScopeResolver.resolve(session)
                    created = (
                        await StaffTaskNotificationEventService.enqueue_departure_reminders(
                            session,
                            offset_minutes=120,
                            scan_window_minutes=10,
                            tenant_scope=tenant_scope,
                        )
                    )
                    await session.commit()
                if created:
                    logger.info("Staff departure reminders enqueued: %s", created)
            except Exception:
                logger.exception("Staff departure reminder loop error")
            await asyncio.sleep(5 * 60)

    async def _order_document_cleanup_loop(self):
        from services.order_document_cleanup_service import (
            OrderDocumentCleanupService,
        )

        while True:
            try:
                outcomes = await OrderDocumentCleanupService.process_batch(
                    worker_id="scheduler-order-document-cleanup",
                    limit=25,
                )
                if outcomes:
                    logger.info(
                        "Order document cleanup batch processed: total=%s deleted=%s retry=%s dead=%s",
                        len(outcomes),
                        sum(item.outcome == "deleted" for item in outcomes),
                        sum(item.outcome == "retry_scheduled" for item in outcomes),
                        sum(item.outcome == "dead" for item in outcomes),
                    )
                    await asyncio.sleep(1)
                else:
                    await asyncio.sleep(30)
            except Exception:
                logger.exception("Order document cleanup loop error")
                await asyncio.sleep(60)

    async def _catalog_invalidation_loop(self):
        from services.catalog_invalidation_worker import CatalogInvalidationWorker

        worker = CatalogInvalidationWorker(
            worker_id="scheduler-catalog-invalidation",
            lease_seconds=settings.CATALOG_INVALIDATION_WORKER_LEASE_SECONDS,
            recovery_limit=settings.CATALOG_INVALIDATION_WORKER_RECOVERY_LIMIT,
        )
        while True:
            poll_seconds = max(
                0.1,
                float(settings.CATALOG_INVALIDATION_WORKER_POLL_SECONDS),
            )
            if not settings.CATALOG_INVALIDATION_WORKER_ENABLED:
                await asyncio.sleep(max(30.0, poll_seconds))
                continue
            try:
                outcome = await worker.run_once()
                if outcome.outcome == "configuration_blocked":
                    logger.warning(
                        "Catalog invalidation worker is blocked by Cloudflare "
                        "configuration mode=%s",
                        outcome.configuration_mode,
                    )
                    await asyncio.sleep(max(30.0, poll_seconds))
                elif outcome.outcome == "idle":
                    await asyncio.sleep(poll_seconds)
            except Exception:
                logger.exception("Catalog invalidation worker loop error")
                await asyncio.sleep(max(5.0, poll_seconds))

    async def _repair_diagnostic_ai_job_loop(self):
        from services.repair_diagnostic_ai_job_service import (
            RepairDiagnosticAiJobService,
        )

        while True:
            try:
                processed = await RepairDiagnosticAiJobService.process_batch(
                    worker_id="scheduler-repair-diagnostic-ai",
                    limit=10,
                )
                await asyncio.sleep(1 if processed else 15)
            except Exception:
                logger.exception("Repair diagnostic AI job loop error")
                await asyncio.sleep(30)

    async def _public_write_receipt_retention_loop(self):
        from services.public_write_idempotency_retention_service import (
            PublicWriteIdempotencyRetentionService,
        )

        while True:
            try:
                async with async_session_maker() as session:
                    deleted = (
                        await PublicWriteIdempotencyRetentionService.delete_expired_batch(
                            session,
                            limit=1000,
                        )
                    )
                    await session.commit()
                if deleted:
                    logger.info("Expired public write receipts deleted: %s", deleted)
                await asyncio.sleep(3600)
            except Exception:
                logger.exception("Public write receipt retention loop error")
                await asyncio.sleep(300)

    async def _private_attachment_orphan_loop(self):
        from services.private_attachment_orphan_reconciler import (
            PrivateAttachmentOrphanReconciler,
        )

        while True:
            try:
                async with async_session_maker() as session:
                    deleted = await PrivateAttachmentOrphanReconciler.process_batch(
                        session,
                        limit=100,
                    )
                if deleted:
                    logger.info("Private installation orphans deleted: %s", deleted)
                await asyncio.sleep(3600)
            except Exception:
                logger.exception("Private attachment orphan loop error")
                await asyncio.sleep(300)

    async def _bank_mail_import_loop(self):
        while True:
            interval_minutes = max(1, int(settings.MAIL_IMAP_IMPORT_INTERVAL_MINUTES or 20))
            try:
                if not settings.MAIL_IMAP_AUTO_IMPORT_ENABLED:
                    await asyncio.sleep(interval_minutes * 60)
                    continue
                if not settings.MAIL_IMAP_USERNAME or not settings.MAIL_IMAP_PASSWORD:
                    logger.info("Bank mail import skipped: IMAP credentials are not configured.")
                    await asyncio.sleep(interval_minutes * 60)
                    continue

                from services.mail_imap_service import MailImapService
                from services.notification_service import NotificationService
                from services.tenant_scope_service import SystemTenantScopeResolver

                logger.info("⏳ Bank mail import job started...")
                async with async_session_maker() as session:
                    tenant_scope = await SystemTenantScopeResolver.resolve(session)
                    result = await MailImapService.import_bank_receipts(session, limit=50)
                    notified_admins = await NotificationService.notify_admins_bank_receipts_imported(
                        session,
                        result.created_receipt_ids,
                        tenant_scope=tenant_scope,
                    )
                logger.info(
                    "✅ Bank mail import done. processed=%s created=%s duplicates=%s failed=%s notified_admins=%s",
                    result.processed,
                    result.created,
                    result.duplicates,
                    result.failed,
                    notified_admins,
                )
            except Exception:
                logger.exception("❌ Bank mail import loop error")
            await asyncio.sleep(interval_minutes * 60)

    async def _email_lead_import_loop(self):
        while True:
            interval_value = await self._get_global_config_value(
                "mail_lead_import_interval_minutes",
                str(settings.MAIL_IMAP_LEAD_IMPORT_INTERVAL_MINUTES or 20),
            )
            try:
                interval_minutes = max(1, int(interval_value or 20))
            except (TypeError, ValueError):
                interval_minutes = max(1, int(settings.MAIL_IMAP_LEAD_IMPORT_INTERVAL_MINUTES or 20))
            try:
                enabled_value = await self._get_global_config_value(
                    "mail_lead_auto_import_enabled",
                    "true" if settings.MAIL_IMAP_LEAD_AUTO_IMPORT_ENABLED else "false",
                )
                enabled = str(enabled_value).strip().lower() in {"1", "true", "yes", "on"}
                if not enabled:
                    await asyncio.sleep(interval_minutes * 60)
                    continue
                if not settings.MAIL_IMAP_USERNAME or not settings.MAIL_IMAP_PASSWORD:
                    logger.info("Email lead import skipped: IMAP credentials are not configured.")
                    await asyncio.sleep(interval_minutes * 60)
                    continue

                from services.email_lead_import_job_service import EmailLeadImportJobService

                logger.info("⏳ Email lead import job started...")
                snapshot = await EmailLeadImportJobService.run_scheduled_import()
                result = snapshot.result
                if snapshot.already_running:
                    logger.info("Email lead import skipped: another import is already running.")
                    await asyncio.sleep(interval_minutes * 60)
                    continue
                if not result:
                    logger.warning("Email lead import finished without result. status=%s error=%s", snapshot.status, snapshot.error)
                    await asyncio.sleep(interval_minutes * 60)
                    continue
                logger.info(
                    "✅ Email lead import done. processed=%s candidates=%s ai_checked=%s created=%s duplicates=%s rejected=%s failed=%s notified_admins=%s",
                    result.processed,
                    result.candidates,
                    result.ai_checked,
                    result.created,
                    result.duplicates,
                    result.rejected,
                    result.failed,
                    snapshot.notified_admins,
                )
            except Exception:
                logger.exception("❌ Email lead import loop error")
            await asyncio.sleep(interval_minutes * 60)

scheduler_service = SchedulerService()
