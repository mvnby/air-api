"""Compatibility entry point for verified Telegram work reads and time filters."""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.config import settings
from models.tenancy import TenantScope


class BotTaskService:
    @staticmethod
    async def list_my_tasks(session, telegram_id, *, limit=10, date_from=None, date_to=None,
                            statuses=None, tenant_scope: TenantScope):
        from services.bot_task_read_service import BotTaskAccessDeniedError, BotTaskReadService
        try:
            telegram_id = int(telegram_id or 0)
        except (TypeError, ValueError):
            return []
        if not telegram_id:
            return []
        try:
            return await BotTaskReadService.list_for_staff(session, telegram_id=telegram_id, limit=limit,
                date_from=date_from, date_to=date_to, statuses=statuses, tenant_scope=tenant_scope)
        except BotTaskAccessDeniedError:
            return []

    @staticmethod
    def _normalize_filter_datetime(value: datetime | None) -> datetime | None:
        if value is None or value.tzinfo is None:
            return value
        try:
            local_timezone = ZoneInfo(settings.BOT_TASK_TIMEZONE)
        except ZoneInfoNotFoundError:
            local_timezone = ZoneInfo("Europe/Minsk")
        return value.astimezone(local_timezone).replace(tzinfo=None)
