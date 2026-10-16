from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from starlette.requests import Request

from core.config import settings
from core.database import get_session
from core.security import (create_access_token, get_current_auth_context, get_current_identity,
                           require_personal_workspace_access, get_current_platform_identity)
from models import StaffUser, Tenant, Storefront, TenantMembership, LegacyOwnerAuthState, StaffAvatar
from routers.manager_account_companies import router as companies_router
from routers.manager_profile import router as profile_router
from services.connector_auth_service import ConnectorAuthService
from services.manager_tenant_access_service import ManagerTenantAccessResolver


def request(tenant=None, site=None, method="GET"):
    headers = []
    if tenant is not None:
        headers.append((b"x-mvn-manager-tenant", str(tenant).encode()))
    if site is not None:
        headers.append((b"x-mvn-manager-storefront", site.encode()))
    return Request({"type": "http", "method": method, "headers": headers})


def token(user_id=10, username="person", version=1):
    return create_access_token({"sub": username, "staff_user_id": user_id, "auth_version": version})


@pytest.fixture
async def multi_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'multi.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([Tenant(id=1, slug="mvn", display_name="MVN", is_system=True),
                         Tenant(id=2, slug="partner", display_name="Partner"),
                         Tenant(id=3, slug="other", display_name="Other", demo_read_only=True)])
        await session.flush()
        session.add_all([Storefront(id=i, tenant_id=i, slug="main", display_name="Main", status="active", is_default=True) for i in (1, 2, 3)])
        session.add_all([StaffUser(id=4, username=settings.ADMIN_USERNAME, display_name="Root", roles=["owner"], primary_role="owner"),
                         StaffUser(id=10, username="person", display_name="Person", roles=["manager"], primary_role="manager", password_hash="existing-hash")])
        await session.flush()
        session.add_all([TenantMembership(id=4, tenant_id=1, staff_user_id=4, role="owner"),
                         TenantMembership(id=10, tenant_id=1, staff_user_id=10, role="manager", permissions=["catalog.master.edit"]),
                         TenantMembership(id=20, tenant_id=2, staff_user_id=10, role="catalog_editor")])
        session.add(LegacyOwnerAuthState(id=1, mode="staff_shadow", owner_staff_user_id=4))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_base_bootstrap_ignores_selection_but_business_requires_explicit_choice(multi_db):
    session = multi_db
    identity = await get_current_identity(request("not-a-company", "foreign"), token(), session)
    assert identity.staff_user_id == 10 and not hasattr(identity, "tenant_id")
    with pytest.raises(HTTPException) as exc:
        await get_current_auth_context(request(), token(), session)
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "company_selection_required"
    first = await get_current_auth_context(request(1), token(), session)
    second = await get_current_auth_context(request(2), token(), session)
    assert first.permissions == ("catalog.master.edit",) and first.role == "manager"
    assert second.permissions == () and second.role == "catalog_editor"
    assert await ManagerTenantAccessResolver.personal(session, staff_user_id=10)
    for invalid in ("0", "-1", "1x", "3", "999999999999999999999"):
        with pytest.raises(HTTPException) as denied:
            await get_current_auth_context(request(invalid), token(), session)
        assert denied.value.status_code == 403
    app = FastAPI()
    app.include_router(companies_router)
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/manager/account/companies", headers={"Authorization": f"Bearer {token()}", "X-MVN-Manager-Tenant": "bad"})
        assert response.status_code == 200
        assert response.json()["total"] == 2 and response.json()["default_tenant_id"] is None
        for membership in (await session.execute(select(TenantMembership).where(TenantMembership.staff_user_id == 10))).scalars():
            membership.status = "disabled"
        await session.commit()
        empty = await client.get("/api/manager/account/companies", headers={"Authorization": f"Bearer {token()}"})
        assert empty.status_code == 200 and empty.json()["items"] == []


@pytest.mark.asyncio
async def test_owner_virtual_support_and_personal_profile_do_not_create_memberships(multi_db):
    session = multi_db
    owner_token = token(4, settings.ADMIN_USERNAME)
    identity = await get_current_identity(request(3), owner_token, session)
    assert await get_current_platform_identity(identity) == identity
    support = await get_current_auth_context(request(3), owner_token, session)
    assert support.access_kind == "platform_support" and support.tenant_membership_id is None and support.demo_read_only
    own = await require_personal_workspace_access(request(3, method="PATCH"), identity, session)
    assert own.tenant_id == 1 and not own.demo_read_only and own.tenant_membership_id == 4
    assert len(list((await session.execute(select(TenantMembership).where(TenantMembership.staff_user_id == 4))).scalars())) == 1
    user = await session.get(StaffUser, 4)
    user.auth_version += 1
    await session.commit()
    with pytest.raises(HTTPException) as denied:
        await get_current_identity(request(), owner_token, session)
    assert denied.value.status_code == 401


@pytest.mark.asyncio
async def test_connector_uses_granted_company_and_live_membership(multi_db):
    session = multi_db
    snapshot = SimpleNamespace(staff_user_id=10, auth_version=1, membership_id=10, tenant_id=1, storefront_id=1, role="manager", scopes=[])
    assert (await ConnectorAuthService._live_actor(session, snapshot)).tenant_scope.tenant_id == 1
    member = await session.get(TenantMembership, 10)
    member.status = "disabled"
    await session.commit()
    from services.connector_auth_policy import ConnectorAuthError
    with pytest.raises(ConnectorAuthError):
        await ConnectorAuthService._live_actor(session, snapshot)


@pytest.mark.asyncio
async def test_photo_company_query_is_authoritative_even_with_other_headers(multi_db):
    session = multi_db
    session.add(StaffAvatar(staff_user_id=4, content=b"safe-webp", content_hash="a" * 64))
    await session.commit()
    app = FastAPI()
    app.include_router(profile_router)
    app.dependency_overrides[get_session] = lambda: session
    headers = {"Authorization": f"Bearer {token()}", "X-MVN-Manager-Tenant": "2"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        image = await client.get("/api/manager/staff/4/avatar?tenant_id=1", headers=headers)
        assert image.status_code == 200
        assert (await client.get("/api/manager/staff/4/avatar?tenant_id=2", headers={**headers, "If-None-Match": image.headers["etag"]})).status_code == 404
        assert (await client.get("/api/manager/staff/4/avatar", headers=headers)).status_code == 422
        member = await session.get(TenantMembership, 10)
        member.status = "disabled"
        await session.commit()
        assert (await client.get("/api/manager/staff/4/avatar?tenant_id=1", headers={**headers, "If-None-Match": image.headers["etag"]})).status_code == 403


@pytest.mark.asyncio
async def test_password_and_telegram_login_need_any_real_workspace_not_singleton(multi_db):
    from routers.auth import router as login_router
    from services.credential_service import CredentialService
    from services.staff_telegram_service import StaffTelegramService
    from services.staff_telegram_security import StaffTelegramError
    session = multi_db
    user = await session.get(StaffUser, 10)
    user.password_hash = CredentialService.hash_password("workspace-password")
    user.telegram_id = 1010
    await session.commit()
    assert (await StaffTelegramService._login_user(session, 1010)).id == 10
    app = FastAPI()
    app.include_router(login_router)
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/login/access-token", data={"username": "person", "password": "workspace-password"})
        assert response.status_code == 200
        for membership in (await session.execute(select(TenantMembership).where(TenantMembership.staff_user_id == 10))).scalars():
            membership.role = "installer"
        await session.commit()
        denied = await client.post("/login/access-token", data={"username": "person", "password": "workspace-password"})
        assert denied.status_code == 400
        with pytest.raises(StaffTelegramError):
            await StaffTelegramService._login_user(session, 1010)


@pytest.mark.asyncio
@pytest.mark.parametrize("membership_state", ["disabled", "installer"])
async def test_signed_widget_rejects_no_workspace_and_accepts_multiple(multi_db, monkeypatch, membership_state):
    import hashlib
    import hmac
    import time
    from routers.auth import router as login_router

    session = multi_db
    monkeypatch.setattr(settings, "BOT_TOKEN", "unit-test-widget-token")
    user = await session.get(StaffUser, 10)
    user.telegram_id = 1010
    await session.commit()
    app = FastAPI()
    app.include_router(login_router)
    app.dependency_overrides[get_session] = lambda: session

    def signed_payload(first_name):
        payload = {"id": 1010, "auth_date": int(time.time()), "first_name": first_name}
        data = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
        secret = hashlib.sha256(settings.BOT_TOKEN.encode()).digest()
        payload["hash"] = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
        return payload

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        success = await client.post("/login/telegram", json=signed_payload("Before"))
        assert success.status_code == 200
        for membership in (await session.execute(select(TenantMembership).where(TenantMembership.staff_user_id == 10))).scalars():
            if membership_state == "disabled":
                membership.status = "disabled"
            else:
                membership.role = "installer"
        await session.commit()
        denied = await client.post("/login/telegram", json=signed_payload("After"))
        assert denied.status_code == 401
        assert denied.json()["detail"]["code"] == "telegram_login_unavailable"
