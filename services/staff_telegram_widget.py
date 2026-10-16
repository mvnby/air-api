"""Replay receipt for the compatible legacy signed Telegram widget."""

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from models import StaffUser, TenantAuditEvent
from core.request_context import current_request_id
from models.staff_telegram import StaffTelegramWidgetReceipt
from services.staff_telegram_security import StaffTelegramError, digest
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
from services.account_access_service import AccountAccessResolver
from services.manager_tenant_access_service import ManagerTenantAccessResolutionError
from services.staff_tenant_membership_service import StaffTenantMembershipService
from services.staff_user_service import StaffUserService


@dataclass(frozen=True)
class TelegramWidgetAuthentication:
    staff_user_id: int
    username: str
    role: str
    auth_version: int

    def token_data(self):
        return {"sub": self.username, "staff_user_id": self.staff_user_id, "role": self.role,
                "auth_source": "telegram", "auth_version": self.auth_version}


async def consume_widget_proof(session, payload, *, commit=True):
    now = datetime.now(timezone.utc)
    await session.execute(delete(StaffTelegramWidgetReceipt).where(StaffTelegramWidgetReceipt.expires_at < now))
    session.add(StaffTelegramWidgetReceipt(
        signature_hash=digest(str(payload["hash"])), expires_at=now + timedelta(minutes=11),
    ))
    try:
        if commit:
            await session.commit()
        else:
            await session.flush()
    except IntegrityError:
        await session.rollback()
        raise StaffTelegramError("telegram_proof_used", "Подтверждение Telegram уже использовано. Повторите вход", 409) from None


async def authenticate_widget(session, payload):
    """Finalize proof and freeze its credential version under identity locks.

    Disconnect/replacement follows the same state -> tenant -> staff order.
    A concurrent credential change can only invalidate this frozen version;
    no post-commit refresh can upgrade an old Telegram proof to a new version.
    """
    if not StaffUserService.verify_telegram_login_payload(payload):
        raise StaffTelegramError("telegram_login_unavailable", "Telegram login is not allowed", 401)
    telegram_id = int(payload["id"])
    state = await LegacyOwnerAuthGuard.state(session, for_update=True)
    staff_id = await session.scalar(select(StaffUser.id).where(StaffUser.telegram_id == telegram_id))
    if staff_id is None:
        raise StaffTelegramError("telegram_login_unavailable", "Telegram login is not allowed", 401)
    try:
        access = await AccountAccessResolver.personal(session, staff_user_id=staff_id)
    except ManagerTenantAccessResolutionError:
        raise StaffTelegramError("telegram_login_unavailable", "Telegram login is not allowed", 401) from None
    await StaffTenantMembershipService.lock_tenant(session, tenant_id=access.tenant_scope.tenant_id)
    user = (await session.execute(select(StaffUser).where(
        StaffUser.id == staff_id, StaffUser.telegram_id == telegram_id,
    ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if user is None or not StaffUserService.is_active(user):
        raise StaffTelegramError("telegram_login_unavailable", "Telegram login is not allowed", 401)
    try:
        await AccountAccessResolver.personal(session, staff_user_id=staff_id)
    except ManagerTenantAccessResolutionError:
        raise StaffTelegramError("telegram_login_unavailable", "Telegram login is not allowed", 401) from None
    if not LegacyOwnerAuthGuard.allows_staff_identity(state, staff_user_id=staff_id, username=user.username or ""):
        raise StaffTelegramError("telegram_login_unavailable", "Telegram login is not allowed", 401)
    if LegacyOwnerManagedIdentityService.is_bound(state, staff_user_id=staff_id):
        if not await LegacyOwnerManagedIdentityService.exact_bound_staff_identity_allowed(session, state=state, user=user):
            raise StaffTelegramError("telegram_login_unavailable", "Telegram login is not allowed", 401)
    await consume_widget_proof(session, payload, commit=False)
    username = str(payload.get("username") or "").strip() or None
    if username:
        user.telegram_username = username
    user.telegram_verified_at = datetime.now(timezone.utc)
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    snapshot = TelegramWidgetAuthentication(staff_user_id=int(user.id), username=user.username or str(telegram_id),
                                            role=StaffUserService.primary_role(user), auth_version=int(user.auth_version))
    session.add(TenantAuditEvent(
        tenant_id=access.tenant_scope.tenant_id, storefront_id=access.tenant_scope.storefront_id,
        actor_staff_user_id=snapshot.staff_user_id, actor_username=snapshot.username,
        action="staff.telegram_login", entity_type="staff_user", entity_id=snapshot.staff_user_id,
        request_id=current_request_id(), change_set={"method": "telegram_widget", "auth_version": snapshot.auth_version},
    ))
    await session.commit()
    return snapshot
