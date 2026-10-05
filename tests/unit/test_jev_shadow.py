import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from core.app_http import manager_validation_exception_handler
from core.config import settings
from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context
from crud import jev_shadow as dao
from models import JevConnection, JevShadowSample, Order, Storefront, Tenant
from models.tenancy import TenantScope
from routers.manager_jev import router
from services.jev_connection_service import JevConnectionService as Connection, JevCredentialCipher, JevCredentialError
from services.jev_provider_service import JevResult, JevProviderError
from services.jev_shadow_service import JevShadowService as Shadow
from services.integration_credential_health import integration_credential_health
from services.integration_credential_rotation_service import IntegrationCredentialRotationService as Rotation

SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def factory(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", json.dumps({
        "active_key_id": "test", "write_mode": "active", "keys": {"test": "shared-integration-master-key-000000001"},
        "legacy_secret_keys": [settings.SECRET_KEY]}))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'jev.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    make = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("services.jev_shadow_service.async_session_maker", make)
    async with make() as session:
        session.add_all([Tenant(id=1, slug="mvn", display_name="MVN", is_system=True),
            Tenant(id=21, slug="partner", display_name="Partner"),
            Storefront(id=1, tenant_id=1, slug="main", display_name="Main"),
            Storefront(id=21, tenant_id=21, slug="main", display_name="Partner")])
        await session.commit()
    yield make
    await engine.dispose()


async def enable(factory, **kwargs):
    async with factory() as session:
        return await Connection.save(session, key="jev-secret-key", enabled=True, **kwargs)


async def enqueue(**kwargs):
    await Shadow.enqueue(tenant_scope=kwargs.pop("tenant_scope", SCOPE), source="email", identity=kwargs.pop("identity", "mail-1"),
        subject=kwargs.pop("subject", "Кондиционер"), body=kwargs.pop("body", "Нужен монтаж кондиционера"),
        primary_provider="deepseek", primary_model_requested="deepseek-v4-flash", primary_is_relevant=kwargs.pop("primary", False), **kwargs)


def result(**kwargs):
    data = dict(model="jev-1.13.0", kind="customer_request", kind_confidence=.95, hvac_probability=.9,
                input_tokens=1000, output_tokens=12, duration_ms=120)
    return JevResult(**{**data, **kwargs})


@pytest.mark.asyncio
async def test_credentials_rotation_disable_and_delete(factory, monkeypatch):
    async with factory() as session:
        assert not Connection.public(None)["configured"]
        saved = await Connection.save(session, key="jev-secret-key")
        assert saved["configured"] and not saved["enabled"]
        row = await Connection.get(session)
        assert "jev-secret-key" not in row.encrypted_credentials
        ciphertext = row.encrypted_credentials
        await Connection.save(session, key="", enabled=True)
        assert row.encrypted_credentials == ciphertext
        assert (await integration_credential_health(session))["checked"] == 1
        plan = await Rotation.plan(session)
        assert plan["complete"] and plan["rows"][0]["domain"] == "jev"
        assert "jev-secret-key" not in json.dumps(plan)
        ring = settings.INTEGRATION_CREDENTIAL_KEYRING_JSON
        cfg = json.loads(ring); cfg["write_mode"] = "legacy"
        monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", json.dumps(cfg))
        row.encrypted_credentials = JevCredentialCipher.encrypt("jev-secret-key")
        session.add(row); await session.commit()
        monkeypatch.setattr(settings, "INTEGRATION_CREDENTIAL_KEYRING_JSON", ring)
        record = (await Rotation._read_records(session, for_update=False))[0]
        assert record.needs_rewrap
        Rotation._rewrap_record(record); await session.commit()
        assert (await Rotation.plan(session))["complete"]
        await Connection.delete(session)
        assert not Connection.public(row)["configured"] and not row.enabled
        assert (await integration_credential_health(session))["checked"] == 0
        with pytest.raises(JevCredentialError, match="not_configured"):
            await Connection.save(session, enabled=True)


@pytest.mark.asyncio
async def test_dedupe_changed_input_and_system_tenant_boundary(factory):
    await enqueue()
    async with factory() as session:
        assert await dao.pending_count(session) == 0
    await enable(factory)
    await enqueue(); await enqueue()
    await enqueue(body="Нужно обслуживание вентиляции")
    await enqueue(tenant_scope=TenantScope(tenant_id=21, storefront_id=21, is_system=True))
    await enqueue(tenant_scope=TenantScope(tenant_id=21, storefront_id=21, is_system=False))
    async with factory() as session:
        rows = (await session.execute(select(JevShadowSample))).scalars().all()
        assert len(rows) == 2 and all(row.tenant_id == 1 for row in rows)
        assert all(len(row.state) <= 6000 and row.prompt_version == "intake-v1" for row in rows)


@pytest.mark.asyncio
async def test_observation_is_non_authoritative_and_report_retains_disagreement(factory, monkeypatch):
    await enable(factory)
    await enqueue(primary=False)
    provider = AsyncMock(return_value=result())
    monkeypatch.setattr("services.jev_shadow_service.classify_jev", provider)
    assert await Shadow.process_one()
    assert not await Shadow.process_one()
    provider.assert_awaited_once()
    async with factory() as session:
        assert (await session.execute(select(Order))).scalars().all() == []
        row = (await session.execute(select(JevShadowSample))).scalar_one()
        assert row.status == "completed" and row.jev_is_relevant and not row.primary_is_relevant
        assert row.estimated_usd == Decimal("0.00004200")
        conn = await Connection.get(session)
        assert conn.daily_requests == 1 and conn.budget_used_usd == row.estimated_usd
        report = await Shadow.report(session, tenant_id=1, disagreements_only=True)
        assert (report["completed"], report["comparable"], report["agreements"], report["disagreements"]) == (1, 1, 0, 1)
        assert report["median_duration_ms"] == 120
        assert "jev-secret-key" not in str(report)
        assert report["items"][0]["state"] == row.state
        assert (await Shadow.report(session, tenant_id=21))["items"] == []


@pytest.mark.asyncio
async def test_errors_are_retained_without_retry_and_reserve_unknown_cost(factory, monkeypatch):
    await enable(factory)
    await enqueue()
    provider = AsyncMock(side_effect=JevProviderError("rate_limited", status=429))
    monkeypatch.setattr("services.jev_shadow_service.classify_jev", provider)
    assert await Shadow.process_one() and not await Shadow.process_one()
    async with factory() as session:
        row = (await session.execute(select(JevShadowSample))).scalar_one()
        assert row.status == "failed" and row.error_code == "rate_limited" and row.estimated_usd is None
        assert (await Connection.get(session)).budget_used_usd == dao.RESERVATION_USD
        assert (await Shadow.report(session, tenant_id=1))["failed"] == 1
    provider.assert_awaited_once()


@pytest.mark.asyncio
async def test_disable_daily_budget_request_limit_and_utc_reset(factory, monkeypatch):
    await enable(factory, daily_budget_usd=.002)
    await enqueue()
    provider = AsyncMock(return_value=result())
    monkeypatch.setattr("services.jev_shadow_service.classify_jev", provider)
    assert not await Shadow.process_one()
    async with factory() as session:
        await Connection.save(session, daily_budget_usd=.05, enabled=False)
    assert not await Shadow.process_one()
    async with factory() as session:
        await Connection.save(session, enabled=True)
        row = await Connection.get(session)
        row.budget_day = datetime.now(timezone.utc).date(); row.daily_requests = 500
        session.add(row); await session.commit()
    assert not await Shadow.process_one()
    async with factory() as session:
        row = await Connection.get(session)
        row.budget_day -= timedelta(days=1)
        session.add(row); await session.commit()
    assert await Shadow.process_one()
    provider.assert_awaited_once()


@pytest.mark.asyncio
async def test_crashed_call_is_not_repeated(factory, monkeypatch):
    await enable(factory)
    await enqueue()
    async with factory() as session:
        async with session.begin():
            _, row = await dao.claim_next(session, max_daily_requests=500)
            row.started_at -= timedelta(minutes=3)
            session.add(row)
    provider = AsyncMock(return_value=result())
    monkeypatch.setattr("services.jev_shadow_service.classify_jev", provider)
    assert not await Shadow.process_one()
    async with factory() as session:
        row = (await session.execute(select(JevShadowSample))).scalar_one()
        assert row.status == "failed" and row.error_code == "worker_interrupted"
    provider.assert_not_called()


@pytest.mark.asyncio
async def test_tender_sends_raw_evidence_and_keeps_rejected_unknown_cases(factory):
    await enable(factory)
    items = [{"profile": {"id": i}, "relevance_status": status, "eligible": False,
        "ai_analysis": {"text": "ANSWER LEAK"}, "tender": {"source": "belzakupki", "external_id": str(i),
        "title": "Поставка", "summary": "Кондиционеры", "ai_analysis": {"text": "ANSWER LEAK"}}}
        for i, status in enumerate(["confirmed", "rejected", "rules_only"])]
    await Shadow.enqueue_tenders(tenant_scope=SCOPE, items=items)
    await Shadow.enqueue_tenders(tenant_scope=SCOPE, items=items)
    async with factory() as session:
        rows = (await session.execute(select(JevShadowSample).order_by(JevShadowSample.id))).scalars().all()
        assert [row.primary_is_relevant for row in rows] == [True, False, None]
        assert all("ANSWER LEAK" not in row.state and "Кондиционеры" in row.state for row in rows)


@pytest.mark.asyncio
async def test_system_only_routes_never_disclose_or_spend_for_partners(factory, monkeypatch, caplog):
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, manager_validation_exception_handler)
    app.include_router(router)
    auth = {"role": "owner", "system": False}
    app.dependency_overrides[get_current_auth_context] = lambda: AuthenticatedUser(username="owner", auth_source="staff_password",
        role=auth["role"], tenant_id=1 if auth["system"] else 21, storefront_id=1, is_system_tenant=auth["system"])
    async def database():
        async with factory() as session:
            yield session
    app.dependency_overrides[get_session] = database
    provider = AsyncMock(return_value=result())
    monkeypatch.setattr("services.jev_provider_service.classify_jev", provider)
    caplog.set_level("INFO", logger="routers.manager_jev")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for role, system in [("owner", False), ("admin", False), ("manager", True)]:
            auth.update(role=role, system=system)
            for method, path, data in [("GET", "", None), ("PUT", "", {"key": "secret"}), ("DELETE", "", None),
                                       ("POST", "/test", None), ("GET", "/shadow", None)]:
                response = await client.request(method, "/api/manager/platform-ai/jev" + path, json=data)
                assert response.status_code == 403
        provider.assert_not_called()
        auth.update(role="owner", system=True)
        response = await client.put("/api/manager/platform-ai/jev", json={"key": "jev-secret-key", "enabled": True})
        assert response.status_code == 200 and "jev-secret-key" not in response.text
        assert (await client.post("/api/manager/platform-ai/jev/test")).json() == {"ok": True, "model": "jev-1.13.0"}
        response = await client.get("/api/manager/platform-ai/jev/shadow?limit=101")
        assert response.status_code == 422
        response = await client.put("/api/manager/platform-ai/jev", json={"key": "private-key-" * 500})
        assert response.status_code == 422 and "private-key-" not in response.text
        assert "jev-secret-key" not in caplog.text


@pytest.mark.asyncio
async def test_connection_probe_counts_budget_and_validated_response_is_success(factory, monkeypatch):
    await enable(factory)
    provider = AsyncMock(return_value=result(hvac_probability=.1))
    monkeypatch.setattr("services.jev_provider_service.classify_jev", provider)
    async with factory() as session:
        assert (await Connection.test(session))["ok"] is True
        row = await Connection.get(session)
        assert row.daily_requests == 1 and row.budget_used_usd == Decimal("0.000042")
        row.daily_requests = 500
        session.add(row); await session.commit()
        with pytest.raises(JevCredentialError, match="budget_exhausted"):
            await Connection.test(session)
    provider.assert_awaited_once()
