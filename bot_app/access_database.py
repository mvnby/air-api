"""Temporary database adapter kept only for explicit rollback during extraction."""

from core.database import async_session_maker
from services.bot_access_service import BotAccessService

from .access import BotAccessContext


class DatabaseBotAccessProvider:
    async def health(self) -> None:
        return None

    async def get_context(self, telegram_id: int | str | None) -> BotAccessContext:
        async with async_session_maker() as session:
            context = await BotAccessService.get_context(session, telegram_id)
        return BotAccessContext(
            telegram_id=context.telegram_id,
            is_staff=context.is_staff,
            display_name=context.display_name,
            primary_role=context.primary_role,
            roles=list(context.roles),
            legacy_installer_id=context.legacy_installer_id,
            is_manager=context.is_manager,
            is_executor=context.is_executor,
        )

    async def aclose(self) -> None:
        return None
