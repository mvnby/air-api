"""Installer account access stays separate from selected Manager CRM authority."""

from dataclasses import replace
from datetime import datetime, timezone

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from core.config import settings
from core.database import get_session
from core.security import create_access_token, get_current_identity, require_personal_workspace_access
from models import LegacyOwnerAuthState, StaffAvatar, StaffUser, Storefront, Tenant, TenantMembership
from routers.auth import router as login_router
from routers.installer_auth import router as installer_router
from routers.manager_account_companies import router as companies_router
from routers.manager_auth import router as manager_router
from routers.manager_profile import router as profile_router
from services.credential_service import CredentialService
from services.staff_telegram_service import StaffTelegramService
from services.staff_telegram_widget import authenticate_widget
from tests.unit.test_manager_multicompany import request


PASSWORD = "installer-test-password-123"


def headers(user_id=10, tenant=1, site="main", *, version=1):
    username = settings.ADMIN_USERNAME if user_id == 4 else f"user-{user_id}"
    result = {"Authorization": "Bearer " + create_access_token({
        "sub": username, "staff_user_id": user_id, "auth_version": version, "auth_source": "staff_password",
    })}
    if tenant is not None:
        result["X-MVN-Manager-Tenant"] = str(tenant)
    if site is not None:
        result["X-MVN-Manager-Storefront"] = site
    return result


@pytest.fixture
async def installer_account(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "kitlane_test_bot")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'installer-account.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all([Tenant(id=i, slug="mvn" if i == 1 else f"company-{i}", display_name=f"Company {i}", is_system=i == 1)
                         for i in (1, 2, 3)])
        await session.flush()
        session.add_all([Storefront(id=i, tenant_id=i, slug="main", display_name=f"Site {i}", status="active", is_default=True)
                         for i in (1, 2, 3)])
        session.add(Storefront(id=4, tenant_id=1, slug="other", display_name="Other site", status="active"))
        for user_id, role in [(4, "owner"), (10, "manager"), (11, "catalog_editor"), (12, "installer")]:
            session.add(StaffUser(
                id=user_id, username=settings.ADMIN_USERNAME if user_id == 4 else f"user-{user_id}",
                display_name=f"User {user_id}", roles=[role], primary_role=role,
                password_hash=CredentialService.hash_password(PASSWORD), telegram_id=1000 + user_id,
                telegram_verified_at=datetime.now(timezone.utc),
            ))
        await session.flush()
        session.add_all([
            TenantMembership(id=4, staff_user_id=4, tenant_id=1, role="owner"),
            TenantMembership(id=10, staff_user_id=10, tenant_id=1, role="installer"),
            TenantMembership(id=20, staff_user_id=10, tenant_id=2, role="manager"),
            TenantMembership(id=11, staff_user_id=11, tenant_id=1, role="catalog_editor"),
            TenantMembership(id=12, staff_user_id=12, tenant_id=1, role="installer"),
            LegacyOwnerAuthState(id=1, mode="staff_shadow", owner_staff_user_id=4),
        ])
        await session.commit()
        app = FastAPI()
        for router in (login_router, installer_router, companies_router, manager_router, profile_router):
            app.include_router(router)
        app.dependency_overrides[get_session] = lambda: session
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            yield session, client
    await engine.dispose()


async def test_selected_installer_never_unions_manager_role_from_another_company(installer_account):
    _, client = installer_account
    own = await client.get("/api/installer/me", headers=headers())
    assert own.status_code == 200, own.text
    assert own.json()["role"] == "installer"
    assert own.json()["capabilities"] == ["installer.works.read"]
    assert own.json()["tenant_membership_id"] == 10
    denied = await client.get("/api/manager/me", headers=headers())
    assert denied.status_code == 403
    crm = await client.get("/api/manager/me", headers=headers(tenant=2))
    assert crm.status_code == 200
    assert crm.json()["role"] == "manager" and "crm.manage" in crm.json()["capabilities"]
    worker = await client.get("/api/installer/me", headers=headers(tenant=2))
    assert worker.status_code == 200 and worker.json()["capabilities"] == ["installer.works.read"]


async def test_installer_requires_explicit_valid_company_site_and_real_membership(installer_account):
    _, client = installer_account
    ambiguous = await client.get("/api/installer/me", headers=headers(tenant=None, site=None))
    assert ambiguous.status_code == 409
    for tenant, site in [(3, "main"), (1, "foreign"), ("bad", "main")]:
        result = await client.get("/api/installer/me", headers=headers(tenant=tenant, site=site))
        assert result.status_code == 403
    # Bound platform authority cannot manufacture an installer company membership.
    assert (await client.get("/api/installer/me", headers=headers(user_id=4, tenant=2))).status_code == 403
    assert (await client.get("/api/installer/me", headers=headers(user_id=11))).status_code == 403


@pytest.mark.parametrize("role", ["owner", "admin", "manager", "installer"])
async def test_actual_selected_roles_can_bootstrap_only_read_capability(installer_account, role):
    session, client = installer_account
    member = await session.get(TenantMembership, 12)
    member.role = role
    await session.commit()
    result = await client.get("/api/installer/me", headers=headers(user_id=12))
    assert result.status_code == 200
    assert result.json()["role"] == role
    assert result.json()["capabilities"] == ["installer.works.read"]


async def test_bootstrap_includes_installer_but_storefronts_stay_in_selected_company(installer_account):
    _, client = installer_account
    companies = await client.get("/api/manager/account/companies", headers=headers(tenant="bad", site="foreign"))
    assert companies.status_code == 200
    assert {(item["tenant_id"], item["role"]) for item in companies.json()["items"]} == {(1, "installer"), (2, "manager")}
    sites = await client.get("/api/installer/storefronts", headers=headers(site="other"))
    assert sites.status_code == 200
    assert {site["id"] for site in sites.json()["items"]} == {1, 4}
    assert next(site for site in sites.json()["items"] if site["is_current"])["id"] == 4


@pytest.mark.parametrize("change", ["membership", "tenant", "site", "identity", "version", "role"])
async def test_installer_bootstrap_rechecks_live_access(installer_account, change):
    session, client = installer_account
    user = await session.get(StaffUser, 12)
    if change == "identity":
        user.status = "inactive"
    elif change == "version":
        user.auth_version += 1
    elif change in {"membership", "role"}:
        member = await session.get(TenantMembership, 12)
        if change == "role":
            member.role = "catalog_editor"
        else:
            member.status = "disabled"
    else:
        row = await session.get(Tenant if change == "tenant" else Storefront, 1)
        row.status = "disabled"
    await session.commit()
    result = await client.get("/api/installer/me", headers=headers(user_id=12))
    assert result.status_code == (401 if change in {"identity", "version"} else 403)


async def test_installer_password_login_profile_and_own_avatar_without_crm(installer_account):
    session, client = installer_account
    logged_in = await client.post("/login/access-token", data={"username": "user-12", "password": PASSWORD})
    assert logged_in.status_code == 200, logged_in.text
    stale = {**headers(user_id=12, tenant="bad", site="foreign"), "X-Kitlane-Profile": "1"}
    profile = await client.get("/api/manager/account/profile", headers=stale)
    assert profile.status_code == 200
    updated = await client.patch("/api/manager/account/profile", headers=stale, json={
        "expected_updated_at": profile.json()["updated_at"], "display_name": "Installer name",
    })
    assert updated.status_code == 200 and updated.json()["display_name"] == "Installer name"
    user = await session.get(StaffUser, 12)
    user.avatar_version = "a" * 64
    session.add(StaffAvatar(staff_user_id=12, content=b"webp-test-content", content_hash=user.avatar_version))
    await session.commit()
    own_avatar = await client.get(updated.json()["avatar_url"] or "/api/manager/staff/12/avatar?tenant_id=1", headers=stale)
    assert own_avatar.status_code == 200
    foreign_avatar = await client.get("/api/manager/staff/10/avatar?tenant_id=1", headers=headers(user_id=12))
    assert foreign_avatar.status_code == 403
    assert (await client.get("/api/manager/me", headers=headers(user_id=12))).status_code == 403
    changed = await client.post("/api/manager/account/change-password", headers=stale, json={
        "current_password": PASSWORD, "new_password": "new-installer-password-456",
    })
    assert changed.status_code == 204, changed.text
    assert (await client.get("/api/installer/me", headers=headers(user_id=12))).status_code == 401


@pytest.mark.parametrize("method", ["widget", "bot"])
async def test_installer_can_login_with_existing_verified_telegram(installer_account, monkeypatch, method):
    session, _ = installer_account
    if method == "widget":
        from services.staff_user_service import StaffUserService
        monkeypatch.setattr(StaffUserService, "verify_telegram_login_payload", classmethod(lambda cls, payload: True))
        result = await authenticate_widget(session, {"id": 1012, "auth_date": 1, "hash": "verified-proof"})
        assert result.staff_user_id == 12 and result.role == "installer"
    else:
        result, secret = await StaffTelegramService.start(session, purpose="login", browser_secret=None)
        token = result["deep_link"].split("?start=login_", 1)[1]
        await StaffTelegramService.claim(session, token=token, telegram_id=1012, telegram_username="installer",
            telegram_display_name="Installer", chat_id=1012, message_id=1, purpose="login")
        await StaffTelegramService.decide(session, challenge_id=result["challenge_id"], telegram_id=1012, approve=True)
        user = await StaffTelegramService.complete_login(session, challenge_id=result["challenge_id"], browser_secret=secret)
        assert user.id == 12


async def test_installer_self_link_and_disconnect_rotate_credentials(installer_account):
    session, _ = installer_account
    token = headers(user_id=12)["Authorization"].removeprefix("Bearer ")
    identity = await get_current_identity(request(), token, session)
    auth = await require_personal_workspace_access(request("bad", "foreign"), identity, session)
    user = await StaffTelegramService.disconnect(session, auth=auth, current_password=PASSWORD)
    auth = replace(auth, auth_version=user.auth_version)
    result, secret = await StaffTelegramService.start(session, purpose="link", browser_secret=None, auth=auth)
    token = result["deep_link"].split("?start=link_", 1)[1]
    await StaffTelegramService.claim(session, token=token, telegram_id=2012, telegram_username="installer_new",
        telegram_display_name="Installer", chat_id=2012, message_id=1, purpose="link")
    linked = await StaffTelegramService.confirm(session, challenge_id=result["challenge_id"], browser_secret=secret,
        auth=auth, telegram_id=2012)
    assert linked.telegram_id == 2012 and linked.auth_version == 3
