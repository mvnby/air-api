import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from core.config import settings
from core.app_http import manager_validation_exception_handler
from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context, require_system_manager_tenant_scope
from models.deepseek_connection import DeepSeekConnection
from routers import manager_belzakupki_enrichment, manager_customers, manager_leads_contract_review, manager_repair_complaints
from routers.manager_platform_ai import router
from services.deepseek_connection_service import (
    DeepSeekConnectionService as Service, DeepSeekCredentialCipher as Cipher,
    DeepSeekCredentialError, resolve_deepseek_token,
)
from services.integration_credential_health import integration_credential_health
from services.integration_credential_rotation_service import IntegrationCredentialRotationService
from services.platform_ai_connection_service import PlatformAICredentialCipher


@pytest.fixture
async def session(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEEPSEEK_TOKEN", "old-environment-key")
    monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", json.dumps({
        "active_key_id": "test", "write_mode": "active",
        "keys": {"test": "active-integration-master-key-00000001"},
        "legacy_secret_keys": [settings.SECRET_KEY],
    }))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'deepseek.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("services.deepseek_connection_service.async_session_maker", factory)
    async with factory() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_import_replace_keep_disable_delete_never_reactivates_environment(session):
    assert Service.public(None)["source"] == "environment"
    assert await resolve_deepseek_token() == "old-environment-key"
    public = await Service.import_environment(session)
    assert public == {"configured": True, "enabled": True, "source": "settings", "environment_key_available": True}
    row = await Service.get(session)
    assert "old-environment-key" not in row.encrypted_credentials
    with pytest.raises(DeepSeekCredentialError, match="already_configured"):
        await Service.import_environment(session)
    await Service.save(session, key="replacement-key", enabled=None)
    assert await resolve_deepseek_token() == "replacement-key"
    ciphertext = row.encrypted_credentials
    await Service.save(session, key="", enabled=None)
    assert row.encrypted_credentials == ciphertext
    await Service.save(session, key=None, enabled=False)
    assert await resolve_deepseek_token() == ""
    assert await Service.resolve_token(session, require_enabled=False) == "replacement-key"
    await Service.save(session, key=None, enabled=True)
    assert await resolve_deepseek_token() == "replacement-key"
    deleted = await Service.delete(session)
    assert deleted["source"] == "settings"
    assert deleted["enabled"] is False and deleted["configured"] is False
    assert await resolve_deepseek_token() == ""
    assert (await Service.get(session)).encrypted_credentials is None
    # Restoring the old key requires a deliberate admin action.
    await Service.import_environment(session)
    assert await resolve_deepseek_token() == "old-environment-key"


@pytest.mark.asyncio
async def test_disabling_legacy_environment_materializes_a_disabled_credential(session):
    public = await Service.save(session, key=None, enabled=False)
    assert public["source"] == "settings" and public["configured"] is True
    assert await resolve_deepseek_token() == ""
    assert await Service.resolve_token(session, require_enabled=False) == "old-environment-key"


@pytest.mark.asyncio
async def test_unreadable_key_never_falls_back_to_environment(session):
    await Service.import_environment(session)
    row = await Service.get(session)
    row.encrypted_credentials = "corrupt"
    session.add(row)
    await session.commit()
    with pytest.raises(DeepSeekCredentialError, match="credential_unreadable"):
        await resolve_deepseek_token()
    assert (await integration_credential_health(session))["unreadable"] == 1


@pytest.mark.asyncio
async def test_cipher_context_rotation_health_and_empty_tombstone(session, monkeypatch):
    await Service.import_environment(session)
    row = await Service.get(session)
    assert (await integration_credential_health(session))["checked"] == 1
    with pytest.raises(Exception):
        PlatformAICredentialCipher.decrypt_with_source(row.encrypted_credentials)
    plan = await IntegrationCredentialRotationService.plan(session)
    assert plan["complete"] is True
    assert plan["rows"][0]["domain"] == "deepseek"
    assert plan["rows"][0]["provider"] == "deepseek"
    assert "old-environment-key" not in json.dumps(plan)
    active_ring = settings.INTEGRATION_CREDENTIAL_KEYRING_JSON
    ring = json.loads(active_ring)
    ring["write_mode"] = "legacy"
    monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", json.dumps(ring))
    row.encrypted_credentials = Cipher.encrypt("replacement-key")
    row.credentials_fingerprint = Cipher.fingerprint("replacement-key")
    session.add(row)
    await session.commit()
    monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", active_ring)
    assert (await IntegrationCredentialRotationService.plan(session))["counts"]["legacy"] == 1
    records = await IntegrationCredentialRotationService._read_records(session, for_update=False)
    IntegrationCredentialRotationService._rewrap_record(records[0])
    await session.commit()
    assert (await IntegrationCredentialRotationService.plan(session))["complete"] is True
    await Service.delete(session)
    assert (await integration_credential_health(session))["checked"] == 0
    assert (await IntegrationCredentialRotationService.plan(session))["rows"] == []


@pytest.mark.asyncio
async def test_routes_reject_partner_and_system_manager_without_spending_or_exposing_key(session, monkeypatch, caplog):
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, manager_validation_exception_handler)
    app.include_router(router)
    auth = {"role": "owner", "system": False}
    app.dependency_overrides[get_current_auth_context] = lambda: AuthenticatedUser(
        username="owner", auth_source="staff_password", role=auth["role"],
        tenant_id=1 if auth["system"] else 21, storefront_id=1,
        is_system_tenant=auth["system"],
    )
    async def database():
        yield session
    app.dependency_overrides[get_session] = database
    provider = AsyncMock(return_value='{"ok":true}')
    monkeypatch.setattr("services.deepseek_provider_service.request_deepseek_completion", provider)
    caplog.set_level("INFO", logger="routers.manager_platform_ai")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for role, system in (("owner", False), ("admin", False), ("manager", True)):
            auth.update(role=role, system=system)
            for method, path, payload in (
                ("GET", "", None), ("PUT", "", {"key": "attacker-key"}),
                ("DELETE", "", None), ("POST", "/import-environment", None), ("POST", "/test", None),
            ):
                response = await client.request(method, f"/api/manager/platform-ai/deepseek{path}", json=payload)
                assert response.status_code == 403
        provider.assert_not_called()
        assert await Service.get(session) is None
        auth.update(role="owner", system=True)
        imported = await client.post("/api/manager/platform-ai/deepseek/import-environment")
        assert imported.status_code == 200
        assert "old-environment-key" not in imported.text
        saved = await client.put("/api/manager/platform-ai/deepseek", json={"key": "replacement-key", "enabled": False})
        assert saved.status_code == 200
        status = await client.get("/api/manager/platform-ai/deepseek")
        assert "replacement-key" not in status.text
        check = await client.post("/api/manager/platform-ai/deepseek/test")
        assert check.json() == {"ok": True}
        assert provider.call_args.kwargs["token"] == "replacement-key"
        assert provider.call_args.kwargs["max_tokens"] == 16
        assert "replacement-key" not in caplog.text
        assert "old-environment-key" not in caplog.text
        from services.deepseek_provider_service import DefectActAIProviderError
        provider.side_effect = DefectActAIProviderError("replacement-key private response", status=401, retryable=False, code="authentication_rejected")
        error = await client.post("/api/manager/platform-ai/deepseek/test")
        assert error.status_code == 502
        assert error.json() == {"detail": {"code": "authentication_rejected"}}
        assert "replacement-key" not in error.text
        invalid_key = "private-invalid-key-" * 300
        validation_error = await client.put("/api/manager/platform-ai/deepseek", json={"key": invalid_key})
        assert validation_error.status_code == 422
        assert "private-invalid-key" not in validation_error.text


def test_partner_inference_routes_require_system_scope():
    spending_operations = {
        "recognize_manager_customer_requisites", "recognize_manager_customer_requisites_text",
        "review_manager_email_lead_contract", "review_manager_email_lead_original",
        "analyze_manager_order_source", "generate_manager_repair_act_ai_draft",
    }
    routes = [route for module in (manager_customers, manager_leads_contract_review, manager_belzakupki_enrichment, manager_repair_complaints) for route in module.router.routes]
    found = {route.operation_id: route for route in routes if route.operation_id in spending_operations}
    assert found.keys() == spending_operations
    for route in found.values():
        assert require_system_manager_tenant_scope in [item.call for item in route.dependant.dependencies]


class _Stream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()


class _ProviderClient:
    tokens = []

    def __init__(self, **kwargs):
        assert kwargs["trust_env"] is False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def build_request(self, method, url, **kwargs):
        return httpx.Request(method, url, **kwargs)

    async def send(self, request, **kwargs):
        self.tokens.append(request.headers["Authorization"])
        return httpx.Response(200, stream=_Stream(), request=request)

    async def post(self, url, **kwargs):
        self.tokens.append(kwargs["headers"]["Authorization"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}, request=httpx.Request("POST", url))


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow", ["shared", "email", "requisites", "tender", "bot"])
async def test_every_transport_observes_rotation_and_disable_without_restart(session, monkeypatch, workflow):
    from services.deepseek_provider_service import request_deepseek_completion
    from services.email_lead_intake_service import EmailLeadIntakeService
    from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService
    from services.belzakupki_source_analysis import analyze_tender_text
    from services.bot_quick_order_service import BotQuickOrderService
    _ProviderClient.tokens = []
    monkeypatch.setattr(httpx, "AsyncClient", _ProviderClient)
    monkeypatch.setattr(BotQuickOrderService, "enrich_draft", AsyncMock(return_value={}))
    async def call():
        if workflow == "shared":
            return await request_deepseek_completion(prompt="test", system_prompt="test", temperature=0)
        if workflow == "email":
            return await EmailLeadIntakeService._request_completion("test")
        if workflow == "requisites":
            return await CustomerRequisitesRecognitionService.extract_requisites("test")
        if workflow == "tender":
            return await analyze_tender_text("test")
        return await BotQuickOrderService.parse_text("test")
    await Service.import_environment(session)
    await call()
    await Service.save(session, key="replacement-key", enabled=None)
    await call()
    assert _ProviderClient.tokens == ["Bearer old-environment-key", "Bearer replacement-key"]
    await Service.delete(session)
    if workflow == "bot":
        await call()  # Bot keeps its deterministic parser when AI is disabled.
    else:
        with pytest.raises((ValueError, RuntimeError)):
            await call()
    assert len(_ProviderClient.tokens) == 2
