"""Shared authorization helpers for versioned Telegram bot use-case APIs."""

from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from services.bot_worker_access import BotWorkerAccessDeniedError, bot_worker_context
from services.staff_user_service import StaffUserService
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


async def require_bot_catalog_editor(
    session: AsyncSession, telegram_id: int, *, deleting: bool = False,
) -> BotAccessContext:
    context = await require_bot_staff(session, telegram_id)
    if context.is_platform_owner:
        return context
    required = {"catalog.master.edit"}
    if deleting:
        required.add("catalog.master.delete")
    if not required.issubset(context.permissions):
        raise BotUseCaseAccessDeniedError("Explicit catalog permission is required")
    return context


async def require_bot_crm_staff(session: AsyncSession, telegram_id: int) -> BotAccessContext:
    context = await require_bot_staff(session, telegram_id)
    if not (context.is_manager or context.is_executor):
        raise BotUseCaseAccessDeniedError('CRM staff access is required')
    return context


async def require_bot_manager_actor(session, telegram_id):
    selection = session.info.get("bot_selection")
    if selection is None:
        raise BotUseCaseAccessDeniedError("Выберите компанию и витрину")
    try:
        auth, selection = await bot_worker_context(session, telegram_id, selection.scope)
    except BotWorkerAccessDeniedError as exc:
        raise BotUseCaseAccessDeniedError("Нужна учётная запись менеджера") from exc
    staff = await StaffUserService.get_by_id(session, selection.staff_user_id)
    if staff is None or staff.telegram_id != telegram_id or staff.auth_version != selection.auth_version:
        raise BotUseCaseAccessDeniedError("Учётная запись менеджера недоступна")
    # Personal read flags are shared with Manager login; task visibility is keyed by staff ID.
    auth = replace(auth, username=staff.username or str(telegram_id), must_change_password=staff.must_change_password)
    return CommandActor.from_auth(auth, channel="telegram"), selection
