"""Freeze the verified Telegram actor for the shared explicit work ACL."""

from core.security import AuthenticatedUser
from services.bot_access_service import BotAccessService


class BotWorkerAccessDeniedError(PermissionError):
    pass


async def bot_worker_context(session, telegram_id, tenant_scope):
    context = await BotAccessService.get_context(session, telegram_id)
    selection = session.info.get("bot_selection") or context.selection
    if (not context.is_staff or not context.staff_user_id or selection is None
            or context.primary_role not in {"owner", "admin", "manager", "installer"}
            or selection.staff_user_id != context.staff_user_id
            or (selection.tenant_id, selection.storefront_id) != (tenant_scope.tenant_id, tenant_scope.storefront_id)):
        raise BotWorkerAccessDeniedError("An active real work membership is required")
    # Use the proof version captured by the request guard. A later credential
    # rotation must invalidate this actor rather than upgrade an in-flight call.
    auth = AuthenticatedUser(
        username=str(telegram_id), auth_source="telegram", staff_user_id=selection.staff_user_id,
        auth_version=selection.auth_version, display_name=context.display_name,
        role=selection.role, tenant_id=selection.tenant_id, storefront_id=selection.storefront_id,
        is_system_tenant=selection.is_system, demo_read_only=selection.demo_read_only,
        access_kind="membership",
    )
    return auth, selection


async def bot_worker_auth(session, telegram_id, tenant_scope):
    auth, _ = await bot_worker_context(session, telegram_id, tenant_scope)
    return auth
