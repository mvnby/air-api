"""Staff-authorized task reads exposed to the Telegram bot API."""

from sqlalchemy.ext.asyncio import AsyncSession

from services.bot_access_service import BotAccessService
from services.bot_task_service import BotTaskService


class BotTaskAccessDeniedError(PermissionError):
    """The Telegram identity cannot use staff task scenarios."""


class BotTaskReadService:
    @staticmethod
    async def list_for_staff(
        session: AsyncSession,
        *,
        telegram_id: int,
        limit: int,
    ) -> list[dict]:
        context = await BotAccessService.get_context(session, telegram_id)
        if not context.is_staff:
            raise BotTaskAccessDeniedError("Staff task access is required")
        if not context.legacy_installer_id:
            return []
        return await BotTaskService.list_installer_tasks(
            session,
            int(context.legacy_installer_id),
            limit=limit,
        )
