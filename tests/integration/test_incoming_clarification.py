"""Linked clarification and qualification preserve wishes without booking work."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.command_actor import CommandActor
from models import Lead, Order, OrderStatus, OrderWorkStage, OrderInstaller, StaffUser, TenantMembership, Tenant, Storefront
from models.personal_task import PersonalTask
from models.tenancy import TenantScope
from schemas_incoming import IncomingCreatePayload, IncomingUpdatePayload, IncomingClarificationPayload, IncomingOrderContext
from schemas_manager_leads import LeadQualifyPayload
from services.incoming_command_service import IncomingCommandService, IncomingVersionConflict
from services.lead_command_service import LeadCommandService
from services.lead_service import LeadVersionConflict
from services.order_projection_service import OrderProjectionService
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict
from services.raw_lead_inbox_service import RawLeadInboxService


async def actor(db):
    staff = StaffUser(display_name="Clarification", username="clarification", roles=["manager"], primary_role="manager")
    db.add(staff)
    await db.flush()
    db.add(TenantMembership(tenant_id=1, staff_user_id=staff.id, role="manager", status="active"))
    await db.commit()
    return CommandActor(staff.id, staff.username, TenantScope(1, 1), "manager")


async def create(db, caller, **kwargs):
    return await IncomingCommandService.create(db, actor=caller,
        payload=IncomingCreatePayload(**kwargs), idempotency_key="clarification-intake-0001")


async def count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.mark.asyncio
@pytest.mark.parametrize("text,expected", [
    ("ТО квартиры; адрес уточнить", True),
    ("ТО квартиры; уточнить точный адрес", True),
    ("ТО квартиры; созвониться перед выездом", True),
    ("ТО квартиры, адрес неизвестен", False),
    ("ТО квартиры; адрес уточнить?", False),
    ("ТО квартиры; не нужно уточнить адрес", False),
    ("ТО квартиры; возможно созвониться перед выездом", False),
])
async def test_only_explicit_positive_instruction_creates_task(db, text, expected):
    caller = await actor(db)
    result = await create(db, caller, request_text=text)
    assert bool(result.value.clarification_task_id) == expected
    assert await count(db, PersonalTask) == int(expected)
    assert await count(db, Order) == 0


@pytest.mark.asyncio
async def test_explicit_intake_task_is_atomic_and_source_event_replays_once(db):
    caller = await actor(db)
    payload = IncomingCreatePayload(request_text="ТО квартиры +375291234567, Билево, завтра 09:00; адрес уточнить",
        name="Анна", email="anna@example.test",
        region_text="Билево", source_event_id="message-clarification-1",
        source_occurred_at=datetime(2026, 10, 6, 20, 59, tzinfo=timezone.utc))
    first = await IncomingCommandService.create(db, actor=caller, payload=payload, idempotency_key="clarification-save-0001")
    replay = await IncomingCommandService.create(db, actor=caller, payload=payload, idempotency_key="clarification-save-0001")
    redelivery = await IncomingCommandService.create(db, actor=caller, payload=payload, idempotency_key="clarification-save-0002")
    assert replay.replayed and replay.value == first.value
    assert redelivery.value.clarification_task_id == first.value.clarification_task_id
    assert await count(db, Lead) == await count(db, PersonalTask) == 1
    task = await db.get(PersonalTask, first.value.clarification_task_id)
    assert task.lead_id == first.value.lead_id
    assert task.assignee_staff_user_id == caller.staff_user_id
    assert task.due_at is task.reminder_at is None
    assert "+375291234567" in task.description and "Билево" in task.description
    assert "Анна" in task.description and "anna@example.test" in task.description
    assert "2026-10-07T09:00:00+03:00" in task.description
    with pytest.raises(PublicWriteIdempotencyConflict):
        await IncomingCommandService.create(db, actor=caller,
            payload=payload.model_copy(update={"region_text": "Другой район"}), idempotency_key="clarification-save-0001")
    assert await count(db, PersonalTask) == 1


@pytest.mark.asyncio
async def test_explicit_link_action_retries_versions_and_scope(db):
    caller = await actor(db)
    saved = await create(db, caller, request_text="ТО квартиры, Билево", region_text="Билево")
    assert saved.value.clarification_task_id is None
    kwargs = dict(actor=caller, lead_id=saved.value.lead_id,
        payload=IncomingClarificationPayload(expected_version=1), idempotency_key="clarification-action-0001")
    first = await IncomingCommandService.create_clarification(db, **kwargs)
    replay = await IncomingCommandService.create_clarification(db, **kwargs)
    assert replay.replayed and replay.value == first.value
    assert first.value.version == 2
    with pytest.raises(PublicWriteIdempotencyConflict):
        await IncomingCommandService.create_clarification(db, **{**kwargs, "payload": IncomingClarificationPayload(expected_version=2)})
    with pytest.raises(IncomingVersionConflict):
        await IncomingCommandService.create_clarification(db, **{**kwargs, "idempotency_key": "clarification-action-0002"})
    existing = await IncomingCommandService.create_clarification(db, **{**kwargs,
        "payload": IncomingClarificationPayload(expected_version=2), "idempotency_key": "clarification-action-0003"})
    assert existing.value.clarification_task_id == first.value.clarification_task_id
    db.add(Tenant(id=2, slug="clarification-foreign", display_name="Foreign"))
    await db.flush()
    db.add(Storefront(id=2, tenant_id=2, slug="main", display_name="Foreign"))
    await db.commit()
    foreign = replace(caller, tenant_scope=TenantScope(2, 2))
    with pytest.raises(LookupError):
        await IncomingCommandService.create_clarification(db, **{**kwargs, "actor": foreign})
    assert await count(db, PersonalTask) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("source,expected", [
    (datetime(2025, 12, 31, 20, 59, tzinfo=timezone.utc), "2026-01-01T09:00:00+03:00"),
    (datetime(2025, 12, 31, 21, 1, tzinfo=timezone.utc), "2026-01-02T09:00:00+03:00"),
])
async def test_correction_and_qualification_preserve_original_agreements(db, source, expected):
    caller = await actor(db)
    original = "ТО квартиры +375291234567, район Билево, завтра 09:00; адрес уточнить; созвониться перед выездом"
    saved = await create(db, caller, request_text=original, region_text="Билево", source_occurred_at=source)
    corrected = await IncomingCommandService.update(db, actor=caller, lead_id=saved.value.lead_id,
        payload=IncomingUpdatePayload(request_text="Обслуживание квартиры, адрес уточняется", expected_version=1),
        idempotency_key="clarification-correct-0001")
    assert corrected.value.original_text == original
    assert corrected.value.requested_at.isoformat() == expected
    assert corrected.value.call_before_visit is True
    assert corrected.value.clarification_task_id == saved.value.clarification_task_id
    lead = await db.get(Lead, saved.value.lead_id)
    inbox = RawLeadInboxService.project(lead, None, None)
    assert inbox.location == "Билево" and inbox.customer_delivery_address is None
    for stale_version in (None, 1):
        with pytest.raises(LeadVersionConflict):
            await LeadCommandService.qualify_lead(db, lead.id,
                LeadQualifyPayload(expected_version=stale_version, workflow_type="maintenance", service_type="maintenance"),
                tenant_scope=caller.tenant_scope)
    assert await count(db, Order) == 0
    qualification = LeadQualifyPayload(expected_version=2, workflow_type="maintenance", service_type="maintenance",
        order_comment="Комментарий менеджера")
    result = await LeadCommandService.qualify_lead(db, lead.id, qualification, tenant_scope=caller.tenant_scope)
    repeated = await LeadCommandService.qualify_lead(db, lead.id, qualification, tenant_scope=caller.tenant_scope)
    assert repeated["order_id"] == result["order_id"] and not repeated["order_created"]
    order = await db.get(Order, result["order_id"])
    assert order.status == OrderStatus.NEGOTIATION
    assert order.workflow_type == "maintenance"
    assert order.comment == "Комментарий менеджера" and order.delivery_address is None
    assert order.installation_date is None
    assert await count(db, OrderInstaller) == 0
    assert await count(db, OrderWorkStage) == 0
    snapshot = order.technical_meta["incoming_intake"]
    context = IncomingOrderContext.model_validate(snapshot)
    assert context.original_text == original and context.request_text == corrected.value.request_text
    assert context.region_text == "Билево" and context.requested_at.isoformat() == expected
    assert context.source_occurred_at == source and context.source_timezone == "Europe/Minsk"
    assert context.field_sources["requested_at"] == context.field_sources["call_before_visit"] == "text"
    assert context.lead_id == lead.id and context.lead_version == 2
    assert context.agreement_status == "customer_wish" and context.call_before_visit
    detail = await OrderProjectionService.get_order_detail_for_manager(db, order.id, tenant_scope=caller.tenant_scope)
    assert detail["incoming_context"] == snapshot
    assert await count(db, Order) == 1


@pytest.mark.asyncio
async def test_parallel_clarification_commands_create_one_task(db, db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as setup:
        caller = await actor(setup)
        saved = await create(setup, caller, request_text="Обслуживание")
    async def delivery():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            return await IncomingCommandService.create_clarification(session, actor=caller,
                lead_id=saved.value.lead_id, payload=IncomingClarificationPayload(expected_version=1),
                idempotency_key="clarification-concurrent-0001")
    first, second = await asyncio.gather(delivery(), delivery())
    assert first.value.clarification_task_id == second.value.clarification_task_id
    assert first.replayed != second.replayed
    assert await count(db, PersonalTask) == 1


@pytest.mark.asyncio
async def test_structured_instruction_correction_and_failure_are_atomic(db, monkeypatch):
    from services.personal_task_service import PersonalTaskService
    caller = await actor(db)
    saved = await create(db, caller, request_text="Нет адреса", clarification_requested=False)
    payload = IncomingUpdatePayload(request_text="Уточнить детали объекта", expected_version=1, clarification_requested=True)
    original_create = PersonalTaskService.create
    async def fail(*args, **kwargs):
        raise ValueError("Task unavailable")
    monkeypatch.setattr(PersonalTaskService, "create", fail)
    with pytest.raises(ValueError, match="Task unavailable"):
        await IncomingCommandService.update(db, actor=caller, lead_id=saved.value.lead_id,
            payload=payload, idempotency_key="clarification-update-task1")
    read = await IncomingCommandService.get(db, actor=caller, lead_id=saved.value.lead_id)
    assert read.version == 1 and read.request_text == "Нет адреса" and read.clarification_task_id is None
    monkeypatch.setattr(PersonalTaskService, "create", original_create)
    updated = await IncomingCommandService.update(db, actor=caller, lead_id=saved.value.lead_id,
        payload=payload, idempotency_key="clarification-update-task1")
    assert updated.value.clarification_task_id
    cleared = await IncomingCommandService.update(db, actor=caller, lead_id=saved.value.lead_id,
        payload=IncomingUpdatePayload(request_text="Адрес уточнили", expected_version=2, clarification_requested=False),
        idempotency_key="clarification-update-task2")
    assert cleared.value.clarification_task_id == updated.value.clarification_task_id
    assert await count(db, PersonalTask) == 1


@pytest.mark.asyncio
async def test_manager_clarification_http_status_and_receipt(db):
    import httpx
    from fastapi import FastAPI
    from core.database import get_session
    from routers.manager_incoming import router, actor as route_actor
    caller = await actor(db)
    saved = await create(db, caller, request_text="Нужно обслуживание")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[route_actor] = lambda: caller
    async def session():
        yield db
    app.dependency_overrides[get_session] = session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        url = f"/api/manager/incoming/{saved.value.lead_id}/clarification"
        headers = {"Idempotency-Key": "clarification-http-0001"}
        first = await client.post(url, json={"expected_version": 1}, headers=headers)
        assert first.status_code == 200 and first.json()["clarification_task_id"]
        replay = await client.post(url, json={"expected_version": 1}, headers=headers)
        assert replay.json() == first.json() and replay.headers["Idempotency-Replayed"] == "true"
        conflict = await client.post(url, json={"expected_version": 2}, headers=headers)
        assert conflict.status_code == 409
        stale = await client.post(url, json={"expected_version": 1}, headers={"Idempotency-Key": "clarification-http-0002"})
        assert stale.status_code == 409
        invalid = await client.post(url, json={"expected_version": 0}, headers=headers)
        assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_unchanged_date_only_correction_retains_precision_and_provenance(db):
    caller = await actor(db)
    saved = await create(db, caller, request_text="ТО завтра", requested_time_text="завтра",
        source_occurred_at=datetime(2025, 12, 31, 21, 1, tzinfo=timezone.utc))
    corrected = await IncomingCommandService.update(db, actor=caller, lead_id=saved.value.lead_id,
        payload=IncomingUpdatePayload(request_text="ТО квартиры завтра", expected_version=1,
            requested_time_text="завтра", requested_at=saved.value.requested_at), idempotency_key="date-only-correct-0001")
    assert corrected.value.date_precision == "date"
    assert corrected.value.field_sources["requested_at"] == "text"


@pytest.mark.asyncio
@pytest.mark.parametrize("keep_date", [True, False])
async def test_explicit_date_override_wins_over_changed_time_text(db, keep_date):
    caller = await actor(db)
    saved = await create(db, caller, request_text="ТО завтра", requested_time_text="завтра",
        source_occurred_at=datetime(2025, 12, 31, 21, 1, tzinfo=timezone.utc))
    expected_date = saved.value.requested_at if keep_date else None
    corrected = await IncomingCommandService.update(db, actor=caller, lead_id=saved.value.lead_id,
        payload=IncomingUpdatePayload(request_text="Исправление времени", expected_version=1,
            requested_time_text="послезавтра 09:00", requested_at=expected_date), idempotency_key="explicit-date-override1")
    assert corrected.value.requested_at == expected_date
    assert corrected.value.date_precision == ("date" if keep_date else None)


@pytest.mark.asyncio
async def test_qualification_refreshes_a_lead_previously_loaded_in_the_session(db, db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as setup:
        caller = await actor(setup)
        saved = await create(setup, caller, request_text="Обслуживание", region_text="Билево")
    async with AsyncSession(db_engine, expire_on_commit=False) as stale_session:
        cached = await stale_session.get(Lead, saved.value.lead_id)
        assert cached.version == 1
        async with AsyncSession(db_engine, expire_on_commit=False) as correction_session:
            await IncomingCommandService.update(correction_session, actor=caller, lead_id=saved.value.lead_id,
                payload=IncomingUpdatePayload(request_text="Обслуживание завтра", expected_version=1, region_text="Другой район"),
                idempotency_key="qualification-stale-edit1")
        with pytest.raises(LeadVersionConflict):
            await LeadCommandService.qualify_lead(stale_session, saved.value.lead_id,
                LeadQualifyPayload(expected_version=1, workflow_type="maintenance", service_type="maintenance"),
                tenant_scope=caller.tenant_scope)
        result = await LeadCommandService.qualify_lead(stale_session, saved.value.lead_id,
            LeadQualifyPayload(expected_version=2, workflow_type="maintenance", service_type="maintenance"),
            tenant_scope=caller.tenant_scope)
    order = await db.get(Order, result["order_id"])
    assert order.technical_meta["incoming_intake"]["region_text"] == "Другой район"


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["qualified", "spam", "lost", "archived"])
async def test_terminal_incoming_cannot_create_a_clarification(db, terminal):
    from models import LeadStatus
    caller = await actor(db)
    saved = await create(db, caller, request_text="Обслуживание")
    lead = await db.get(Lead, saved.value.lead_id)
    if terminal == "archived":
        lead.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        lead.status = LeadStatus(terminal)
    db.add(lead)
    await db.commit()
    with pytest.raises(IncomingVersionConflict):
        await IncomingCommandService.create_clarification(db, actor=caller, lead_id=lead.id,
            payload=IncomingClarificationPayload(expected_version=1), idempotency_key="clarification-terminal-1")
    assert await count(db, PersonalTask) == 0
