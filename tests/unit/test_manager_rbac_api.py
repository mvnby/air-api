from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from core.config import settings
from core.database import get_session
from core.security import (
    AuthenticatedUser,
    require_manager_access,
)
from models import StaffUser
from routers.auth import router as auth_router
from routers.manager_auth import router as manager_auth_router
from routers.manager_backups import router as manager_backups_router
from routers.manager_crm import router as manager_crm_router
from routers.manager_google_auth import router as manager_google_auth_router
from routers.manager_settings import router as manager_settings_router
from routers.manager_staff import router as manager_staff_router
from services.staff_user_service import StaffUserService


TEST_PASSWORD = "secret123"


class _GoogleServiceStub:
    @staticmethod
    def get_token_status():
        return {
            "exists": True,
            "valid": True,
            "expired": False,
            "expiry": None,
            "scopes": ["drive"],
        }


@pytest.fixture()
async def rbac_client(tmp_path: Path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'manager-rbac.db'}", echo=False)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(
            [
                StaffUser(
                    display_name="Installer",
                    status="active",
                    primary_role="installer",
                    roles=["installer"],
                    username="installer-rbac",
                    password_hash=StaffUserService.hash_password(TEST_PASSWORD),
                ),
                StaffUser(
                    display_name="Manager",
                    status="active",
                    primary_role="manager",
                    roles=["manager"],
                    username="manager-rbac",
                    password_hash=StaffUserService.hash_password(TEST_PASSWORD),
                ),
                StaffUser(
                    display_name="Owner",
                    status="active",
                    primary_role="owner",
                    roles=["owner"],
                    username="owner-rbac",
                    password_hash=StaffUserService.hash_password(TEST_PASSWORD),
                ),
            ]
        )
        await session.commit()

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(manager_auth_router)
    app.include_router(manager_crm_router)
    app.include_router(manager_staff_router)
    app.include_router(manager_backups_router)
    app.include_router(manager_google_auth_router)
    app.include_router(manager_settings_router)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    monkeypatch.setattr("routers.manager_backups.backup_service.list_backups", lambda limit=100: [])
    monkeypatch.setattr("routers.manager_google_auth.get_google_service", lambda: _GoogleServiceStub())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


async def _login(client: AsyncClient, username: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/login/access-token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.parametrize("role", ["installer", "maintenance", "repair", "measurer"])
@pytest.mark.asyncio
async def test_executor_roles_are_denied_manager_access(role: str):
    auth = AuthenticatedUser(
        username=f"{role}-user",
        auth_source="staff_password",
        staff_user_id=1,
        role=role,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_manager_access(auth)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_installer_can_login_but_cannot_open_manager_api(rbac_client: AsyncClient):
    headers = await _login(rbac_client, "installer-rbac", TEST_PASSWORD)

    me_response = await rbac_client.get("/api/manager/me", headers=headers)
    manager_response = await rbac_client.get("/api/manager/crm/health-report", headers=headers)

    assert me_response.status_code == 403
    assert manager_response.status_code == 403


@pytest.mark.asyncio
async def test_manager_can_use_manager_api_but_not_owner_endpoints(rbac_client: AsyncClient):
    headers = await _login(rbac_client, "manager-rbac", TEST_PASSWORD)

    me_response = await rbac_client.get("/api/manager/me", headers=headers)
    manager_response = await rbac_client.get("/api/manager/crm/health-report", headers=headers)
    staff_response = await rbac_client.get("/api/manager/staff", headers=headers)
    backups_response = await rbac_client.get("/api/manager/backups", headers=headers)
    google_response = await rbac_client.get("/api/manager/google-auth/status", headers=headers)
    settings_response = await rbac_client.get("/api/manager/settings", headers=headers)
    settings_create_response = await rbac_client.post(
        "/api/manager/settings",
        headers=headers,
        json={"key": "restricted", "value": "secret"},
    )
    settings_update_response = await rbac_client.put(
        "/api/manager/settings/restricted",
        headers=headers,
        json={"value": "changed"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["role"] == "manager"
    assert manager_response.status_code == 200
    assert staff_response.status_code == 403
    assert backups_response.status_code == 403
    assert google_response.status_code == 403
    assert settings_response.status_code == 403
    assert settings_create_response.status_code == 403
    assert settings_update_response.status_code == 403


@pytest.mark.asyncio
async def test_owner_and_legacy_admin_can_use_owner_endpoints(rbac_client: AsyncClient):
    owner_headers = await _login(rbac_client, "owner-rbac", TEST_PASSWORD)
    legacy_headers = await _login(rbac_client, settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD)

    for headers in (owner_headers, legacy_headers):
        me_response = await rbac_client.get("/api/manager/me", headers=headers)
        manager_response = await rbac_client.get("/api/manager/crm/health-report", headers=headers)
        staff_response = await rbac_client.get("/api/manager/staff", headers=headers)
        backups_response = await rbac_client.get("/api/manager/backups", headers=headers)
        google_response = await rbac_client.get("/api/manager/google-auth/status", headers=headers)
        settings_response = await rbac_client.get("/api/manager/settings", headers=headers)

        assert me_response.status_code == 200
        assert me_response.json()["role"] == "owner"
        assert manager_response.status_code == 200
        assert staff_response.status_code == 200
        assert backups_response.status_code == 200
        assert google_response.status_code == 200
        assert settings_response.status_code == 200
