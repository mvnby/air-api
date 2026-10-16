from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient, ASGITransport
from sqlmodel import select

from api_contracts.manager_invitations import StaffInvitationAcceptNew, StaffInvitationAcceptCredentials, StaffInvitationAcceptExisting
from core.database import get_session
from core.security import AuthenticatedUser, AuthenticatedIdentity, get_current_identity
from models import StaffUser, Tenant, TenantMembership, TenantAuditEvent
from models.staff_invitation import StaffInvitation
from routers.manager_staff_invitations import public_router
from services.credential_service import CredentialService
from services.staff_invitation_service import StaffInvitationService as Service, StaffInvitationError, digest
from services.staff_access_policy import StaffAccessPolicyError
from tests.unit.test_manager_multicompany import multi_db, request, token


def owner(tenant=2):
    return AuthenticatedUser(username="owner", auth_source="staff_password", staff_user_id=4,
                             auth_version=1, tenant_id=tenant, storefront_id=tenant,
                             role="owner", is_platform_owner=True, access_kind="platform_support")


async def invite(session, *, tenant=2, role="manager"):
    result = await Service.create(session, auth=owner(tenant), role=role)
    return result["invite_url"].split("#token=")[1], result


@pytest.mark.asyncio
async def test_installer_invitation_creates_account_only_without_crm_or_work_grant(multi_db):
    from core.security import get_current_auth_context, get_current_installer_context
    from fastapi import HTTPException
    from models.installer_workspace import TenantWorkerProfile, OrderWorkAssignment
    from api_contracts.manager_invitations import ManagerStaffInvitationCreate

    session = multi_db
    assert ManagerStaffInvitationCreate(role="installer").role == "installer"
    # A company administrator may onboard an ordinary installer.
    member = await session.get(TenantMembership, 20)
    member.role = "admin"
    await session.commit()
    actor = replace(owner(), staff_user_id=10, is_platform_owner=False)
    created = await Service.create(session, auth=actor, role="installer")
    raw = created["invite_url"].split("#token=")[1]
    assert (await Service.preview(session, token=raw))["role"] == "installer"
    accepted, snapshot = await Service.accept(session, payload=StaffInvitationAcceptNew(
        token=raw, mode="new", username="newinstaller", password="installer-password-123", display_name="Installer",
    ))
    assert accepted["tenant_id"] == 2
    user = await session.get(StaffUser, snapshot.id)
    membership = await session.scalar(select(TenantMembership).where(TenantMembership.staff_user_id == snapshot.id))
    assert user.primary_role == "installer" and user.roles == ["installer"]
    assert user.legacy_installer_id is None
    assert membership.role == "installer" and membership.permissions == []
    assert await session.scalar(select(TenantWorkerProfile.id).where(TenantWorkerProfile.staff_user_id == snapshot.id)) is None
    assert list((await session.execute(select(OrderWorkAssignment))).scalars()) == []
    identity = await get_current_identity(request(), token(snapshot.id, "newinstaller"), session)
    installer = await get_current_installer_context(request(2), identity, session)
    assert installer.role == "installer" and installer.tenant_id == 2
    with pytest.raises(HTTPException) as denied:
        await get_current_auth_context(request(2), token(snapshot.id, "newinstaller"), session)
    assert denied.value.status_code == 403
    with pytest.raises(StaffInvitationError):
        await Service.accept(session, payload=StaffInvitationAcceptExisting(token=raw, mode="existing"), identity=identity)


@pytest.mark.asyncio
async def test_installer_invitation_revoke_and_inviter_demotion_remain_effective(multi_db):
    session = multi_db
    raw, result = await invite(session, role="installer")
    await Service.revoke(session, auth=owner(), invitation_id=result["id"])
    with pytest.raises(StaffInvitationError):
        await Service.preview(session, token=raw)
    with pytest.raises(StaffInvitationError):
        await Service.accept(session, payload=StaffInvitationAcceptNew(
            token=raw, mode="new", username="revokedinstaller", password="installer-password-123", display_name="Installer",
        ))
    await session.rollback()
    member = await session.get(TenantMembership, 20)
    member.role = "admin"
    await session.commit()
    actor = replace(owner(), staff_user_id=10, is_platform_owner=False)
    result = await Service.create(session, auth=actor, role="installer")
    member.role = "manager"
    await session.commit()
    with pytest.raises(StaffAccessPolicyError):
        await Service.accept(session, payload=StaffInvitationAcceptNew(
            token=result["invite_url"].split("#token=")[1], mode="new", username="demotedinstaller",
            password="installer-password-123", display_name="Installer",
        ))
    await session.rollback()
    assert await session.scalar(select(StaffUser.id).where(StaffUser.username.in_(["revokedinstaller", "demotedinstaller"]))) is None


@pytest.mark.asyncio
async def test_invitation_service_rejects_unknown_role_even_for_platform_owner(multi_db):
    with pytest.raises(StaffInvitationError) as denied:
        await invite(multi_db, role="supplier")
    assert denied.value.code == "invitation_role_invalid"


@pytest.mark.asyncio
async def test_new_person_token_single_use_no_grants_and_safe_listing(multi_db):
    session = multi_db
    raw, created = await invite(session)
    stored = await session.get(StaffInvitation, created["id"])
    assert stored.token_hash == digest(raw) and raw not in repr(stored)
    listing = await Service.list(session, auth=owner(), page=1, limit=50)
    assert raw not in str(listing) and "token_hash" not in str(listing)
    assert created["invite_url"].startswith("/manager/invite#token=")
    preview = await Service.preview(session, token=raw)
    assert set(preview) == {"company_name", "role", "expires_at"}
    payload = StaffInvitationAcceptNew(token=raw, mode="new", username="newperson", password="new-password-123", display_name="New Person")
    accepted, snapshot = await Service.accept(session, payload=payload)
    assert accepted == {"tenant_id": 2, "default_storefront_slug": "main"}
    user = await session.get(StaffUser, snapshot.id)
    assert CredentialService.verify_password("new-password-123", user.password_hash)
    membership = await session.scalar(select(TenantMembership).where(TenantMembership.staff_user_id == snapshot.id))
    assert membership.role == "manager" and membership.permissions == []
    assert (await get_current_identity(request(), token(snapshot.id, "newperson"), session)).staff_user_id == snapshot.id
    with pytest.raises(StaffInvitationError, match="недоступно"):
        await Service.accept(session, payload=payload)
    actions = list((await session.execute(select(TenantAuditEvent.action).where(TenantAuditEvent.entity_type == "staff_invitation"))).scalars())
    assert actions == ["staff_invitation.created", "staff_invitation.accepted"]


@pytest.mark.asyncio
async def test_existing_membership_never_upgrades_and_no_password_reset(multi_db):
    session = multi_db
    raw, _ = await invite(session, role="owner")
    identity = AuthenticatedIdentity(username="person", auth_source="staff_password", staff_user_id=10, auth_version=1)
    with pytest.raises(StaffInvitationError) as exc:
        await Service.accept(session, payload=StaffInvitationAcceptExisting(token=raw, mode="existing"), identity=identity)
    assert exc.value.code == "membership_exists"
    await session.rollback()
    assert (await session.get(TenantMembership, 20)).role == "catalog_editor"
    with pytest.raises(StaffInvitationError) as exc:
        await Service.accept(session, payload=StaffInvitationAcceptNew(token=raw, mode="new", username="person", password="replacement-password", display_name="Another"))
    assert exc.value.code == "account_exists"
    await session.rollback()
    assert (await session.get(StaffUser, 10)).password_hash == "existing-hash"


@pytest.mark.asyncio
async def test_returning_person_reactivates_only_new_membership_and_revokes_old_tokens(multi_db):
    session = multi_db
    tenant = await session.get(Tenant, 3)
    tenant.demo_read_only = False
    user = await session.get(StaffUser, 10)
    user.status = "inactive"
    user.password_hash = CredentialService.hash_password("returning-password")
    original_hash = user.password_hash
    for row in (await session.execute(select(TenantMembership).where(TenantMembership.staff_user_id == 10))).scalars():
        row.status = "disabled"
    await session.commit()
    raw, _ = await invite(session, tenant=3)
    with pytest.raises(StaffInvitationError) as bad:
        await Service.accept(session, payload=StaffInvitationAcceptCredentials(token=raw, mode="existing_credentials", username="person", password="wrong-password"), source="127.0.0.1")
    assert bad.value.code == "invalid_credentials"
    accepted, snapshot = await Service.accept(session, payload=StaffInvitationAcceptCredentials(token=raw, mode="existing_credentials", username="person", password="returning-password"), source="127.0.0.1")
    assert snapshot.auth_version == 2 and snapshot.id == 10 and accepted["tenant_id"] == 3
    user = await session.get(StaffUser, 10)
    assert user.status == "active" and user.password_hash == original_hash
    rows = list((await session.execute(select(TenantMembership).where(TenantMembership.staff_user_id == 10).order_by(TenantMembership.tenant_id))).scalars())
    assert [row.status for row in rows] == ["disabled", "disabled", "active"]
    assert rows[-1].permissions == []
    with pytest.raises(HTTPException):
        await get_current_identity(request(), token(), session)
    assert (await get_current_identity(request(), token(version=2), session)).staff_user_id == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["blocked", "merged", "suspended", "worker"])
async def test_returning_person_proof_does_not_override_identity_fences(multi_db, changed):
    session = multi_db
    tenant = await session.get(Tenant, 3)
    tenant.demo_read_only = False
    user = await session.get(StaffUser, 10)
    user.status = "inactive"
    user.password_hash = CredentialService.hash_password("returning-password")
    for row in (await session.execute(select(TenantMembership).where(TenantMembership.staff_user_id == 10))).scalars():
        row.status = "disabled"
    if changed == "blocked":
        user.status = "blocked"
    elif changed == "merged":
        user.merged_into_staff_user_id = 4
    elif changed == "worker":
        user.default_rate = 0
    else:
        (await session.get(TenantMembership, 10)).status = "suspended"
    await session.commit()
    raw, _ = await invite(session, tenant=3)
    with pytest.raises(StaffInvitationError):
        await Service.accept(session, payload=StaffInvitationAcceptCredentials(token=raw, mode="existing_credentials", username="person", password="returning-password"), source="127.0.0.1")
    await session.rollback()
    assert await session.scalar(select(TenantMembership).where(TenantMembership.staff_user_id == 10, TenantMembership.tenant_id == 3)) is None


@pytest.mark.asyncio
async def test_accept_rechecks_inviter_role_and_preserves_bound_owner_membership(multi_db):
    session = multi_db
    # A company owner may issue an owner invitation, then lose that authority.
    member = await session.get(TenantMembership, 20)
    member.role = "owner"
    await session.commit()
    actor = replace(owner(), staff_user_id=10, is_platform_owner=False)
    created = await Service.create(session, auth=actor, role="owner")
    raw = created["invite_url"].split("#token=")[1]
    member.role = "admin"
    await session.commit()
    with pytest.raises(StaffAccessPolicyError):
        await Service.accept(session, payload=StaffInvitationAcceptNew(token=raw, mode="new", username="wouldbeowner", password="new-password-123", display_name="New"))
    await session.rollback()
    raw, _ = await invite(session)
    with pytest.raises(StaffInvitationError) as exc:
        await Service.accept(session, payload=StaffInvitationAcceptExisting(token=raw, mode="existing"),
                             identity=AuthenticatedIdentity(username="root", auth_source="staff_password", staff_user_id=4, auth_version=1))
    assert exc.value.code == "platform_owner_membership_fixed"


@pytest.mark.asyncio
async def test_credentials_verified_before_locks_cannot_upgrade_to_changed_password(multi_db, monkeypatch):
    session = multi_db
    tenant = await session.get(Tenant, 3)
    tenant.demo_read_only = False
    user = await session.get(StaffUser, 10)
    user.password_hash = CredentialService.hash_password("returning-password")
    await session.commit()
    raw, _ = await invite(session, tenant=3)
    original = Service.credentials
    async def changed(*args, **kwargs):
        proof = await original(*args, **kwargs)
        user.auth_version += 1
        user.password_hash = "changed-hash"
        await session.commit()
        return proof
    monkeypatch.setattr(Service, "credentials", changed)
    with pytest.raises(StaffInvitationError) as exc:
        await Service.accept(session, payload=StaffInvitationAcceptCredentials(token=raw, mode="existing_credentials", username="person", password="returning-password"))
    assert exc.value.code == "identity_changed"


@pytest.mark.asyncio
async def test_public_accept_requires_team_origin_and_sets_cookie_only_after_accept(multi_db):
    session = multi_db
    raw, _ = await invite(session)
    app = FastAPI()
    app.include_router(public_router)
    app.dependency_overrides[get_session] = lambda: session
    payload = {"token": raw, "mode": "new", "username": "browsernew", "password": "new-password-123", "display_name": "Person"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for headers in ({}, {"X-Kitlane-Team": "1", "Origin": "https://foreign.test"}):
            response = await client.post("/api/account/invitations/accept", json=payload, headers=headers)
            assert response.status_code == 403 and "set-cookie" not in response.headers
        accepted = await client.post("/api/account/invitations/accept", json=payload, headers={"X-Kitlane-Team": "1"})
        assert accepted.status_code == 200, accepted.text
        assert set(accepted.json()) == {"tenant_id", "default_storefront_slug"}
        assert "HttpOnly" in accepted.headers["set-cookie"]
