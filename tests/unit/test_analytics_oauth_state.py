from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.config import settings
from core.security import AuthenticatedUser
from models.tenancy import TenantScope
from services.analytics_oauth_state import (
    ANALYTICS_GOOGLE_OAUTH_SESSION_KEY,
    consume_google_oauth_state,
    pending_actor_scope,
    start_google_oauth_state,
)
from services.manager_tenant_access_service import (
    ManagerTenantAccess,
    ManagerTenantAccessResolutionError,
)


def test_analytics_google_oauth_state_is_scope_bound_and_single_use():
    request = SimpleNamespace(session={})
    auth = AuthenticatedUser(
        username="owner",
        auth_source="staff",
        staff_user_id=5,
        role="owner",
        tenant_id=21,
        storefront_id=71,
        tenant_membership_id=31,
        auth_version=4,
    )

    state = start_google_oauth_state(
        request,
        auth=auth,
        provider="google_analytics",
        public_config={"property_id": "123456"},
        redirect_uri="https://api.mvn.by/api/manager/google-auth/callback",
    )

    assert consume_google_oauth_state(request, "wrong-state") is None
    pending = consume_google_oauth_state(request, state)
    assert pending is not None
    assert pending["tenant_id"] == 21
    assert pending["storefront_id"] == 71
    assert pending["staff_user_id"] == 5
    assert pending["public_config"] == {"property_id": "123456"}
    assert ANALYTICS_GOOGLE_OAUTH_SESSION_KEY not in request.session
    assert consume_google_oauth_state(request, state) is None


@pytest.fixture
def pending_support(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "platform-owner")
    tenant = SimpleNamespace(id=21, status="active", is_system=False, demo_read_only=False)
    storefront = SimpleNamespace(id=71, tenant_id=21, status="active", is_default=False)
    user = SimpleNamespace(id=5, username="platform-owner", status="active", auth_version=4)
    state = SimpleNamespace(mode="staff", owner_staff_user_id=5)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: storefront)),
        get=AsyncMock(return_value=tenant),
    )
    monkeypatch.setattr("services.analytics_oauth_state.StaffUserService.get_by_id", AsyncMock(return_value=user))
    monkeypatch.setattr("services.analytics_oauth_state.LegacyOwnerAuthGuard.state", AsyncMock(return_value=state))
    # Prove that pending consent must pass the same exact bound-profile fence as login.
    from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
    profile_allowed = AsyncMock(return_value=True)
    monkeypatch.setattr(LegacyOwnerManagedIdentityService, "exact_bound_staff_identity_allowed", profile_allowed)
    from services.manager_tenant_access_service import ManagerTenantAccessResolver
    support = AsyncMock(return_value=ManagerTenantAccess(
        None, "owner", TenantScope(21, 70), access_kind="platform_support",
    ))
    monkeypatch.setattr(ManagerTenantAccessResolver, "platform_support", support)
    pending = {
        "staff_user_id": 5, "username": "platform-owner", "auth_source": "staff_password",
        "auth_version": 4, "tenant_membership_id": None, "access_kind": "platform_support",
        "tenant_id": 21, "storefront_id": 71,
    }
    return SimpleNamespace(session=session, tenant=tenant, storefront=storefront, user=user,
                           state=state, pending=pending, support=support, profile_allowed=profile_allowed)


@pytest.mark.asyncio
async def test_pending_support_rechecks_owner_and_preserves_selected_storefront(pending_support):
    case = pending_support
    scope = await pending_actor_scope(case.session, case.pending)
    assert scope == TenantScope(21, 71, is_canonical_storefront=False)
    case.profile_allowed.assert_awaited_once_with(case.session, state=case.state, user=case.user)
    case.support.assert_awaited_once_with(case.session, tenant_id=21)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["credential", "inactive", "owner_binding", "legacy_mode", "profile", "tenant", "username"])
async def test_pending_support_rejects_revoked_authority(pending_support, change):
    case = pending_support
    if change == "credential":
        case.user.auth_version += 1
    elif change == "inactive":
        case.user.status = "blocked"
    elif change == "owner_binding":
        case.state.owner_staff_user_id = 6
    elif change == "legacy_mode":
        case.state.mode = "legacy"
    elif change == "profile":
        case.profile_allowed.return_value = False
    elif change == "username":
        case.user.username = "renamed-owner"
    else:
        case.tenant.status = "disabled"
    assert await pending_actor_scope(case.session, case.pending) is None
    case.support.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_support_rejects_unavailable_storefront(pending_support):
    case = pending_support
    case.session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)
    assert await pending_actor_scope(case.session, case.pending) is None
    case.support.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["membership_id", "missing_kind", "unknown_kind"])
async def test_support_requires_an_explicit_membership_free_snapshot(pending_support, change):
    case = pending_support
    if change == "membership_id":
        case.pending["tenant_membership_id"] = 31
    elif change == "missing_kind":
        case.pending.pop("access_kind")
    else:
        case.pending["access_kind"] = "unknown"
    assert await pending_actor_scope(case.session, case.pending) is None
    case.support.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["unavailable", "demo"])
async def test_support_requires_a_live_writable_company(pending_support, change):
    case = pending_support
    if change == "unavailable":
        case.support.side_effect = ManagerTenantAccessResolutionError("Company unavailable")
    else:
        case.support.return_value = ManagerTenantAccess(
            None, "owner", TenantScope(21, 70, demo_read_only=True), access_kind="platform_support",
        )
    assert await pending_actor_scope(case.session, case.pending) is None


@pytest.mark.asyncio
async def test_membership_consent_cannot_fall_back_to_platform_support(pending_support):
    case = pending_support
    case.pending.update(access_kind="membership", tenant_membership_id=31)
    case.session.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: case.storefront),
        SimpleNamespace(scalar_one_or_none=lambda: None),
    ]
    assert await pending_actor_scope(case.session, case.pending) is None
    case.support.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_membership_consent_still_resolves(pending_support):
    case = pending_support
    case.pending.pop("access_kind")
    case.pending["tenant_membership_id"] = 31
    case.session.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: case.storefront),
        SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(role="owner")),
    ]
    assert await pending_actor_scope(case.session, case.pending) == TenantScope(
        21, 71, is_canonical_storefront=False,
    )
    case.support.assert_not_awaited()


def test_analytics_state_preserves_explicit_platform_support_kind():
    request = SimpleNamespace(session={})
    auth = AuthenticatedUser(username="platform-owner", auth_source="staff_password",
        staff_user_id=5, role="owner", tenant_id=21, storefront_id=71,
        tenant_membership_id=None, auth_version=4, is_platform_owner=True,
        access_kind="platform_support")
    state = start_google_oauth_state(request, auth=auth, provider="google_analytics",
        public_config={"property_id": "123456"}, redirect_uri="https://example.test/callback")
    pending = consume_google_oauth_state(request, state)
    assert pending["access_kind"] == "platform_support"
    assert pending["tenant_membership_id"] is None
