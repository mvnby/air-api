"""Durable capture -> read suggestions -> versioned correction -> qualification."""
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func
from sqlmodel import select

from core.database import get_session
from models import Lead, Order, OrderWorkStage, OrderInstaller, PublicWriteIdempotency
from routers.manager_incoming import router, actor as route_actor
from schemas_incoming import IncomingUpdatePayload
from schemas_manager_leads import LeadQualifyPayload
from services.incoming_command_service import IncomingCommandService, IncomingVersionConflict
from services.lead_command_service import LeadCommandService
from services.raw_lead_inbox_service import RawLeadInboxService
from core.command_actor import CommandActor
from models import StaffUser, TenantMembership
from models.tenancy import TenantScope


async def actor(db):
    staff = StaffUser(display_name="Preview", username="incoming-preview", roles=["manager"], primary_role="manager")
    db.add(staff)
    await db.flush()
    db.add(TenantMembership(tenant_id=1, staff_user_id=staff.id, role="manager", status="active"))
    await db.commit()
    return CommandActor(staff.id, staff.username, TenantScope(1, 1), "manager")


@pytest.mark.asyncio
async def test_capture_commits_before_failed_preview_and_retry_is_read_only(db, monkeypatch):
    caller = await actor(db)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[route_actor] = lambda: caller
    async def session():
        yield db
    app.dependency_overrides[get_session] = session
    calls = []
    def fail(text):
        calls.append(text)
        raise RuntimeError("Parser offline")
    monkeypatch.setattr("services.incoming_command_service.incoming_preview", fail)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        source = "ТО квартиры, район Билево; адрес уточнить"
        body = {"request_text": source}
        headers = {"Idempotency-Key": "incoming-preview-http-0001"}
        saved = await client.post("/api/manager/incoming", json=body, headers=headers)
        assert saved.status_code == 201 and saved.json()["preview"] is None and calls == []
        assert not db.in_transaction()
        lead_id = saved.json()["lead_id"]
        for _ in range(2):
            read = await client.get(f"/api/manager/incoming/{lead_id}?include_preview=true")
            assert read.status_code == 200 and read.json()["preview"]["state"] == "unavailable"
            assert read.json()["original_text"] == source and read.json()["version"] == 1
        replay = await client.post("/api/manager/incoming", json=body, headers=headers)
        assert replay.json() == saved.json() and replay.headers["Idempotency-Replayed"] == "true"
        await db.rollback()
        ordinary = await client.get(f"/api/manager/incoming/{lead_id}")
        assert ordinary.json()["preview"] is None
    assert len(calls) == 2
    assert (await db.execute(select(func.count()).select_from(PublicWriteIdempotency))).scalar_one() == 2  # intake + linked task


@pytest.mark.asyncio
async def test_preview_correction_retains_manual_details_and_qualifies_selected_scenario(db):
    from schemas_incoming import IncomingCreatePayload
    caller = await actor(db)
    text = "ТО квартиры, +375291234567, район Билево, завтра 09:00; адрес уточнить; созвониться перед выездом"
    saved = await IncomingCommandService.create(db, actor=caller, payload=IncomingCreatePayload(
        request_text=text, phone="+375299999999", address_text="Указанный вручную адрес",
        source_occurred_at=datetime(2026, 10, 6, 21, 30, tzinfo=timezone.utc)), idempotency_key="incoming-preview-flow-0001")
    read = await IncomingCommandService.get(db, actor=caller, lead_id=saved.value.lead_id, include_preview=True)
    assert read.preview.region_text == "Билево" and read.preview.service_type == "maintenance"
    assert read.phone == "+375299999999" and read.address_text == "Указанный вручную адрес"
    assert read.region_text is None and read.service_type is None
    payload = IncomingUpdatePayload(request_text=text, expected_version=read.version,
        region_text="Центр", workflow_type="repair", service_type="repair")
    corrected = await IncomingCommandService.update(db, actor=caller, lead_id=read.lead_id,
        payload=payload, idempotency_key="incoming-preview-flow-0002")
    retry = await IncomingCommandService.update(db, actor=caller, lead_id=read.lead_id,
        payload=payload, idempotency_key="incoming-preview-flow-0002")
    assert retry.replayed and retry.value == corrected.value
    assert corrected.value.phone == read.phone and corrected.value.address_text == read.address_text
    assert corrected.value.requested_at == read.requested_at
    assert corrected.value.source_occurred_at == read.source_occurred_at
    assert corrected.value.clarification_task_id == read.clarification_task_id
    assert corrected.value.field_sources["region_text"] == corrected.value.field_sources["service_type"] == "provided"
    # An old parse/correction result cannot replace the manager's newer choice.
    with pytest.raises(IncomingVersionConflict):
        await IncomingCommandService.update(db, actor=caller, lead_id=read.lead_id,
            payload=IncomingUpdatePayload(request_text=text, expected_version=read.version, service_type="maintenance"),
            idempotency_key="incoming-preview-flow-stale")
    detail = RawLeadInboxService.project(await db.get(Lead, read.lead_id), None, None)
    assert detail.service_type == detail.workflow_type == "repair" and detail.location == "Указанный вручную адрес"
    qualified = await LeadCommandService.qualify_lead(db, read.lead_id, LeadQualifyPayload(
        expected_version=corrected.value.version, customer_type="individual", name="Иван", phone=corrected.value.phone,
        workflow_type=detail.workflow_type, service_type=detail.service_type), tenant_scope=caller.tenant_scope)
    order = await db.get(Order, qualified["order_id"])
    assert order.workflow_type == "repair" and order.technical_meta["service_type"] == "repair"
    context = order.technical_meta["incoming_intake"]
    assert context["region_text"] == "Центр" and context["original_text"] == text
    assert context["requested_at"] == read.requested_at.isoformat()
    assert context["source_timezone"] == "Europe/Minsk" and context["call_before_visit"]
    assert context["clarification_task_id"] == read.clarification_task_id
    assert order.installation_date is None
    for model in (OrderWorkStage, OrderInstaller):
        assert (await db.execute(select(func.count()).select_from(model))).scalar_one() == 0
    fresh = await IncomingCommandService.get(db, actor=caller, lead_id=read.lead_id, include_preview=True)
    assert fresh.service_type == "repair" and fresh.region_text == "Центр"  # read never persists suggestions


@pytest.mark.asyncio
async def test_preview_enforces_tenant_scope_before_parsing(db, monkeypatch):
    from dataclasses import replace
    from schemas_incoming import IncomingCreatePayload
    caller = await actor(db)
    saved = await IncomingCommandService.create(db, actor=caller,
        payload=IncomingCreatePayload(request_text="ТО квартиры, район Билево"),
        idempotency_key="incoming-preview-scope-0001")
    def unexpected_parse(*args):
        pytest.fail("Foreign source must never be parsed or exposed")
    monkeypatch.setattr("services.incoming_command_service.incoming_preview", unexpected_parse)
    with pytest.raises(LookupError):
        await IncomingCommandService.get(db, actor=replace(caller, tenant_scope=TenantScope(2, 2)),
            lead_id=saved.value.lead_id, include_preview=True)


@pytest.mark.asyncio
async def test_http_partial_scenario_update_retains_dismantling_through_qualification(db):
    caller = await actor(db)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[route_actor] = lambda: caller
    async def session():
        yield db
    app.dependency_overrides[get_session] = session
    text = "Демонтаж, +375291234567, завтра 09:00; адрес уточнить; созвониться перед выездом"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        saved = await client.post("/api/manager/incoming", json={
            "request_text": text, "workflow_type": "service_work", "service_type": "dismantling",
            "source_occurred_at": "2026-10-06T21:30:00Z",
        }, headers={"Idempotency-Key": "review1105-http-create"})
        assert saved.status_code == 201
        original = saved.json()
        lead_id = original["lead_id"]
        patch = {"request_text": text, "expected_version": 1, "workflow_type": "service_work"}
        headers = {"Idempotency-Key": "review1105-http-repeat"}
        corrected = await client.patch(f"/api/manager/incoming/{lead_id}", json=patch, headers=headers)
        assert corrected.status_code == 200
        value = corrected.json()
        assert value["service_type"] == "dismantling"
        assert value["workflow_type"] == "service_work"
        assert value["field_sources"] == original["field_sources"]
        for field in ("original_text", "source_occurred_at", "source_timezone", "phone", "requested_at", "date_precision", "clarification_task_id"):
            assert value[field] == original[field]
        replay = await client.patch(f"/api/manager/incoming/{lead_id}", json=patch, headers=headers)
        assert replay.json() == value and replay.headers["Idempotency-Replayed"] == "true"
        for field in ("workflow_type", "service_type"):
            incompatible = await client.patch(f"/api/manager/incoming/{lead_id}", json={
                "request_text": text, "expected_version": 2, field: "repair",
            }, headers={"Idempotency-Key": f"review1105-http-incompatible-{field}"})
            assert incompatible.status_code == 400
            assert incompatible.json()["detail"]["error_code"] == "invalid_input"
            current = await client.get(f"/api/manager/incoming/{lead_id}")
            assert current.json() == value
    detail = RawLeadInboxService.project(await db.get(Lead, lead_id), None, None)
    qualified = await LeadCommandService.qualify_lead(db, lead_id, LeadQualifyPayload(
        expected_version=2, customer_type="individual", name="Иван", phone=value["phone"],
        workflow_type=detail.workflow_type, service_type=detail.service_type), tenant_scope=caller.tenant_scope)
    order = await db.get(Order, qualified["order_id"])
    assert order.workflow_type == "service_work" and order.technical_meta["service_type"] == "dismantling"
    context = order.technical_meta["incoming_intake"]
    assert context["service_type"] == "dismantling" and context["field_sources"] == original["field_sources"]
    assert context["original_text"] == text and context["clarification_task_id"] == original["clarification_task_id"]
    assert context["requested_at"] == original["requested_at"]
    assert order.installation_date is None
    for model in (OrderWorkStage, OrderInstaller):
        assert (await db.execute(select(func.count()).select_from(model))).scalar_one() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("fields,workflow", [
    ({"service_type": None}, "service_work"),
    ({"workflow_type": None}, None),
    ({"workflow_type": None, "service_type": None}, None),
])
async def test_http_explicit_clear_retains_only_compatible_omitted_fields(db, fields, workflow):
    caller = await actor(db)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[route_actor] = lambda: caller
    async def session():
        yield db
    app.dependency_overrides[get_session] = session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        saved = await client.post("/api/manager/incoming", json={
            "request_text": "Демонтаж", "workflow_type": "service_work", "service_type": "dismantling",
        }, headers={"Idempotency-Key": "review1105-http-clear-create"})
        assert saved.status_code == 201
        lead_id = saved.json()["lead_id"]
        cleared = await client.patch(f"/api/manager/incoming/{lead_id}", json={
            "request_text": "Демонтаж", "expected_version": 1, **fields,
        }, headers={"Idempotency-Key": "review1105-http-clear-patch"})
        assert cleared.status_code == 200
        value = cleared.json()
        assert value["workflow_type"] == workflow and value["service_type"] is None
        assert "service_type" not in value["field_sources"]
        if workflow is None:
            assert "workflow_type" not in value["field_sources"]
        else:
            assert value["field_sources"]["workflow_type"] == saved.json()["field_sources"]["workflow_type"]
