import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from core.config import settings
from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context
from models import PlatformAIConnection
from routers.manager_platform_ai import router
from core.security import require_system_owner_access
from services.analytics_connection_contracts import AnalyticsCredentialCipher
from services.platform_ai_connection_service import PlatformAIConnectionService, PlatformAICredentialCipher
from services.integration_credential_health import integration_credential_health
from services.integration_credential_rotation_service import IntegrationCredentialRotationService
from services.zaprosu_provider_service import ZaprosuError


def _keyring(mode="active"):
    return json.dumps({
        "active_key_id": "test", "write_mode": mode,
        "keys": {"test": "active-integration-master-key-00000001"},
        "legacy_secret_keys": ["test-only-secret-key-at-least-32-bytes-long"],
    })


@pytest.fixture
async def session(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", _keyring())
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'platform-ai.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_save_keep_replace_disable_delete_and_no_public_secret(session):
    key = "private-zaprosu-key"
    public = await PlatformAIConnectionService.save(session, key=key, enabled=False, model="model-a")
    assert public == {"configured": True, "enabled": False, "selected_model": "model-a"}
    row = await session.get(PlatformAIConnection, 1)
    assert key not in row.encrypted_credentials
    first_ciphertext = row.encrypted_credentials
    await PlatformAIConnectionService.save(session, key="", enabled=True, model=None)
    assert row.encrypted_credentials == first_ciphertext
    assert PlatformAIConnectionService.key(row) == key
    await PlatformAIConnectionService.save(session, key="replacement-key", enabled=None, model="model-b")
    assert PlatformAIConnectionService.key(row) == "replacement-key"
    await PlatformAIConnectionService.save(session, key=None, enabled=False, model=None)
    with pytest.raises(ZaprosuError, match="not_configured"):
        PlatformAIConnectionService.key(row, require_enabled=True)
    await PlatformAIConnectionService.delete(session)
    assert await session.get(PlatformAIConnection, 1) is None


@pytest.mark.asyncio
async def test_routes_reject_partner_owner_and_keep_secret_out_of_reads(session, monkeypatch):
    app = FastAPI()
    app.include_router(router)
    auth = {"system": False}
    app.dependency_overrides[get_current_auth_context] = lambda: AuthenticatedUser(
        username="owner", auth_source="staff_password", role="owner",
        tenant_id=1 if auth["system"] else 21, storefront_id=1,
        is_system_tenant=auth["system"],
    )
    async def database():
        yield session
    app.dependency_overrides[get_session] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/manager/platform-ai")).status_code == 403
        assert (await client.put("/api/manager/platform-ai", json={"key": "private-key"})).status_code == 403
        assert (await client.get("/api/manager/platform-ai/models")).status_code == 403
        auth["system"] = True
        saved = await client.put("/api/manager/platform-ai", json={"key": "private-key", "selected_model": "cheap-cn"})
        assert saved.status_code == 200
        assert "private-key" not in saved.text
        status = await client.get("/api/manager/platform-ai")
        assert status.status_code == 200
        assert "private-key" not in status.text
        assert status.json()["selected_model"] == "cheap-cn"
        async def rejected(_session):
            raise ZaprosuError("authentication_rejected", status=401)
        monkeypatch.setattr(PlatformAIConnectionService, "models", rejected)
        failure = await client.get("/api/manager/platform-ai/models")
        assert failure.status_code == 502
        assert failure.json() == {"detail": {"code": "authentication_rejected"}}
        assert "private-key" not in failure.text


@pytest.mark.asyncio
async def test_disabled_connection_never_invokes_provider(session, monkeypatch):
    await PlatformAIConnectionService.save(session, key="private-key", enabled=False, model="cheap-cn")
    async def forbidden(**_):
        raise AssertionError("provider must not be called")
    monkeypatch.setattr("services.platform_ai_connection_service.chat_completion", forbidden)
    with pytest.raises(ZaprosuError, match="not_configured"):
        await PlatformAIConnectionService.complete(session, prompt="internal request")


@pytest.mark.asyncio
async def test_keyring_context_health_and_rotation_plan(session, monkeypatch):
    await PlatformAIConnectionService.save(session, key="private-key", enabled=False, model=None)
    row = await session.get(PlatformAIConnection, 1)
    assert (await integration_credential_health(session))["checked"] == 1
    assert (await integration_credential_health(session))["unreadable"] == 0
    with pytest.raises(Exception):
        AnalyticsCredentialCipher.decrypt(row.encrypted_credentials, tenant_id=21, storefront_id=71, provider="yandex_metrika")
    plan = await IntegrationCredentialRotationService.plan(session)
    assert plan["rows"][0]["domain"] == "platform_ai"
    assert plan["complete"] is True
    assert "private-key" not in json.dumps(plan)
    monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", _keyring("legacy"))
    row.encrypted_credentials = PlatformAICredentialCipher.encrypt("private-key")
    row.credentials_fingerprint = PlatformAICredentialCipher.fingerprint("private-key")
    assert not row.encrypted_credentials.startswith("mvn-integrations-v1")
    session.add(row)
    await session.commit()
    monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", _keyring())
    plan = await IntegrationCredentialRotationService.plan(session)
    assert plan["counts"]["legacy"] == 1
    assert plan["rows"][0]["needs_rewrap"] is True
    IntegrationCredentialRotationService._rewrap_record((await IntegrationCredentialRotationService._read_records(session, for_update=False))[0])
    await session.commit()
    assert (await IntegrationCredentialRotationService.plan(session))["complete"] is True


def test_routes_use_system_owner_guard():
    for route in router.routes:
        assert require_system_owner_access in [item.call for item in route.dependant.dependencies]
