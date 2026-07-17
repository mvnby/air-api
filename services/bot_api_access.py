"""Shared authorization helpers for versioned Telegram bot use-case APIs."""

from sqlalchemy.ext.asyncio import AsyncSession

from services.bot_access_service import BotAccessContext, BotAccessService


class BotUseCaseAccessDeniedError(PermissionError):
    pass


async def require_bot_staff(session: AsyncSession, telegram_id: int) -> BotAccessContext:
    context = await BotAccessService.get_context(session, telegram_id)
    if not context.is_staff:
        raise BotUseCaseAccessDeniedError("Active staff access is required")
    return context


async def require_bot_manager(session: AsyncSession, telegram_id: int) -> BotAccessContext:
    context = await require_bot_staff(session, telegram_id)
    if not context.is_manager:
        raise BotUseCaseAccessDeniedError("Manager access is required")
    return context
