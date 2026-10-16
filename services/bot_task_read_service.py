"""Staff-authorized task reads exposed to the Telegram bot API."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from services.bot_access_service import BotAccessService
from services.bot_task_service import BotTaskService
from models.tenancy import TenantScope


class BotTaskAccessDeniedError(PermissionError):
    """The Telegram identity cannot use staff task scenarios."""


class BotTaskReadService:
    @staticmethod
    async def list_for_staff(
        session: AsyncSession,
        *,
        telegram_id: int,
        limit: int,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        statuses: list[str] | None = None,
        tenant_scope: TenantScope,
    ) -> list[dict]:
        context = await BotAccessService.get_context(session, telegram_id)
        if not context.is_staff or not (context.is_manager or context.is_executor):
            raise BotTaskAccessDeniedError("Staff task access is required")
        if not context.legacy_installer_id:
            return []
        tasks = await BotTaskService.list_installer_tasks(
            session,
            int(context.legacy_installer_id),
            limit=limit,
            date_from=date_from,
            date_to=date_to,
            statuses=statuses,
            tenant_scope=tenant_scope,
        )
        if context.selection is not None:
            for task in tasks:
                task['manager_url'] = BotTaskService._manager_url(task['order_id'], tenant_scope=tenant_scope,
                                                                 storefront_slug=context.selection.storefront_slug)
        return tasks
