from __future__ import annotations

import secrets
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.security import OWNER_ACCESS_ROLES, AuthenticatedUser
from models import Storefront, Tenant, TenantMembership
from models.tenancy import TenantScope
from services.legacy_owner_auth_guard import LegacyOwnerAuthGuard
from services.staff_user_service import StaffUserService


ANALYTICS_GOOGLE_OAUTH_SESSION_KEY = "manager_analytics_google_oauth_pending"
ANALYTICS_OAUTH_STATE_TTL_SECONDS = 10 * 60


def start_google_oauth_state(
    request,
    *,
    auth: AuthenticatedUser,
    provider: str,
    public_config: dict[str, str],
    redirect_uri: str,
) -> str:
    state = secrets.token_urlsafe(32)
    scope = auth.tenant_scope()
    request.session[ANALYTICS_GOOGLE_OAUTH_SESSION_KEY] = {
        "state": state,
        "issued_at": time.time(),
        "redirect_uri": redirect_uri,
        "provider": provider,
        "public_config": dict(public_config),
        "auth_source": auth.auth_source,
        "auth_version": auth.auth_version,
        "staff_user_id": auth.staff_user_id,
        "username": auth.username,
        "tenant_membership_id": auth.tenant_membership_id,
        "tenant_id": scope.tenant_id,
        "storefront_id": scope.storefront_id,
    }
    return state


def consume_google_oauth_state(request, received_state: str) -> dict[str, Any] | None:
    pending = request.session.get(ANALYTICS_GOOGLE_OAUTH_SESSION_KEY)
    if not isinstance(pending, dict):
        return None
    expected = str(pending.get("state") or "")
    try:
        age = time.time() - float(pending.get("issued_at"))
    except (TypeError, ValueError):
        request.session.pop(ANALYTICS_GOOGLE_OAUTH_SESSION_KEY, None)
        return None
    received = str(received_state or "")
    if not expected or not received or not secrets.compare_digest(expected, received):
        return None
    if age < 0 or age > ANALYTICS_OAUTH_STATE_TTL_SECONDS:
        request.session.pop(ANALYTICS_GOOGLE_OAUTH_SESSION_KEY, None)
        return None
    request.session.pop(ANALYTICS_GOOGLE_OAUTH_SESSION_KEY, None)
    return dict(pending)


async def pending_actor_scope(
    session: AsyncSession,
    pending: dict[str, Any],
) -> TenantScope | None:
    try:
        tenant_id = int(pending.get("tenant_id"))
        storefront_id = int(pending.get("storefront_id"))
    except (TypeError, ValueError):
        return None
    if tenant_id <= 0 or storefront_id <= 0:
        return None

    storefront = (
        await session.execute(
            select(Storefront).where(
                Storefront.id == storefront_id,
                Storefront.tenant_id == tenant_id,
                Storefront.status == "active",
            )
        )
    ).scalar_one_or_none()
    tenant = await session.get(Tenant, tenant_id)
    if storefront is None or tenant is None or str(tenant.status) != "active":
        return None

    username = str(pending.get("username") or "")
    if str(pending.get("auth_source") or "") == "legacy":
        if not LegacyOwnerAuthGuard.configured_username_matches(username):
            return None
        state = await LegacyOwnerAuthGuard.state(session)
        if not LegacyOwnerAuthGuard.allows_legacy_token(
            state,
            token_version=pending.get("auth_version"),
        ):
            return None
        return TenantScope(
            tenant_id=tenant_id,
            storefront_id=storefront_id,
            is_system=bool(tenant.is_system),
            is_canonical_storefront=bool(storefront.is_default),
        )

    try:
        staff_user_id = int(pending.get("staff_user_id"))
        membership_id = int(pending.get("tenant_membership_id"))
        auth_version = int(pending.get("auth_version"))
    except (TypeError, ValueError):
        return None
    staff_user = await StaffUserService.get_by_id(session, staff_user_id)
    if (
        staff_user is None
        or not StaffUserService.is_active(staff_user)
        or int(staff_user.auth_version) != auth_version
    ):
        return None
    membership = (
        await session.execute(
            select(TenantMembership).where(
                TenantMembership.id == membership_id,
                TenantMembership.staff_user_id == staff_user_id,
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.status == "active",
            )
        )
    ).scalar_one_or_none()
    if membership is None or str(membership.role).lower() not in OWNER_ACCESS_ROLES:
        return None
    return TenantScope(
        tenant_id=tenant_id,
        storefront_id=storefront_id,
        is_system=bool(tenant.is_system),
        is_canonical_storefront=bool(storefront.is_default),
    )
