import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime

from services.email_lead_intake_service import EmailLeadImportResult
from services.mail_imap_service import MailImapService

logger = logging.getLogger(__name__)


@dataclass
class EmailLeadImportJobSnapshot:
    status: str = "idle"
    source: str | None = None
    dry_run: bool = False
    lookback_days: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_import_at: str | None = None
    notified_admins: int = 0
    already_running: bool = False
    error: str | None = None
    message: str | None = None
    result: EmailLeadImportResult | None = None


class EmailLeadImportJobService:
    _lock = asyncio.Lock()
    _snapshot = EmailLeadImportJobSnapshot()
    _task: asyncio.Task | None = None

    @classmethod
    async def get_status(cls) -> EmailLeadImportJobSnapshot:
        async with cls._lock:
            return replace(cls._snapshot)

    @classmethod
    async def start_manual_import(
        cls,
        *,
        dry_run: bool = False,
        lookback_days: int | None = None,
    ) -> EmailLeadImportJobSnapshot:
        async with cls._lock:
            if cls._snapshot.status == "running":
                return replace(
                    cls._snapshot,
                    already_running=True,
                    message="Импорт email-лидов уже выполняется.",
                )
            cls._snapshot = cls._running_snapshot(
                source="manual",
                dry_run=dry_run,
                lookback_days=lookback_days,
            )
            cls._task = asyncio.create_task(
                cls._execute_import(
                    source="manual",
                    dry_run=dry_run,
                    lookback_days=lookback_days,
                )
            )
            return replace(cls._snapshot, message="Импорт email-лидов запущен в фоне.")

    @classmethod
    async def run_scheduled_import(cls) -> EmailLeadImportJobSnapshot:
        async with cls._lock:
            if cls._snapshot.status == "running":
                return replace(
                    cls._snapshot,
                    already_running=True,
                    message="Плановый импорт пропущен: предыдущий импорт еще выполняется.",
                )
            cls._snapshot = cls._running_snapshot(source="scheduler", dry_run=False, lookback_days=None)
        await cls._execute_import(source="scheduler", dry_run=False, lookback_days=None)
        return await cls.get_status()

    @classmethod
    def _running_snapshot(
        cls,
        *,
        source: str,
        dry_run: bool,
        lookback_days: int | None,
    ) -> EmailLeadImportJobSnapshot:
        return EmailLeadImportJobSnapshot(
            status="running",
            source=source,
            dry_run=dry_run,
            lookback_days=lookback_days,
            started_at=datetime.now(),
            message="Импорт email-лидов выполняется.",
        )

    @classmethod
    async def _execute_import(
        cls,
        *,
        source: str,
        dry_run: bool,
        lookback_days: int | None,
    ) -> None:
        from core.database import async_session_maker
        from services.notification_service import NotificationService

        notified_admins = 0
        try:
            async with async_session_maker() as session:
                result = await MailImapService.import_email_leads(
                    session,
                    dry_run=dry_run,
                    lookback_days=lookback_days,
                )
                if not dry_run and result.created_order_ids:
                    try:
                        notified_admins = await NotificationService.notify_admins_email_leads_imported(
                            session,
                            result.created_order_ids,
                        )
                    except Exception:
                        logger.exception(
                            "EMAIL_LEAD_IMPORT_NOTIFY_FAILED source=%s order_ids=%s",
                            source,
                            result.created_order_ids,
                        )

            async with cls._lock:
                cls._snapshot = EmailLeadImportJobSnapshot(
                    status="completed",
                    source=source,
                    dry_run=dry_run,
                    lookback_days=lookback_days,
                    started_at=cls._snapshot.started_at,
                    finished_at=datetime.now(),
                    last_import_at=result.last_import_at,
                    notified_admins=notified_admins,
                    result=result,
                    message="Импорт email-лидов завершен.",
                )
        except Exception as exc:
            logger.exception("EMAIL_LEAD_IMPORT_JOB_FAILED source=%s dry_run=%s", source, dry_run)
            async with cls._lock:
                cls._snapshot = EmailLeadImportJobSnapshot(
                    status="failed",
                    source=source,
                    dry_run=dry_run,
                    lookback_days=lookback_days,
                    started_at=cls._snapshot.started_at,
                    finished_at=datetime.now(),
                    error=str(exc),
                    message="Импорт email-лидов завершился ошибкой.",
                )

