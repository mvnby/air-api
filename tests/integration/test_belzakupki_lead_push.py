"""PostgreSQL/API proof of isolated native push and the shared importer lock."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from core.config import settings
from models import BelzakupkiImportCheckpoint, Order, OrderStatus, Tenant, Storefront
from schemas_belzakupki_intake import NativeOpportunity
from services.belzakupki_import_service import BelzakupkiImportService
from services.belzakupki_lead_push_service import BelzakupkiLeadPushService, LeadPushScopeDenied, LeadPushUnavailable
from services.tenant_scope_service import TenantScope


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True, is_canonical_storefront=True)


def item():
    return {"id": 11, "profile": {"id": 7, "name": "HVAC"}, "score": 0.91,
        "relevance_status": "confirmed", "eligible": True, "reason": "HVAC relevance",
        "updated_at": "2026-10-09T10:00:00+00:00", "tender": {"source": "native-source",
        "external_id": "tender-42", "title": "Native tender", "url": "https://example.test/tender/42",
        "deadline_at": "2099-10-01T10:00:00+00:00"}}


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "BELZAKUPKI_LEAD_PUSH_ENABLED", True)
    monkeypatch.setattr(settings, "BELZAKUPKI_LEAD_PUSH_API_KEY", "dedicated-test-key")
    monkeypatch.setattr(settings, "BELZAKUPKI_IMPORT_TENANT_SLUG", "mvn")
    monkeypatch.setattr(settings, "BELZAKUPKI_IMPORT_STOREFRONT_SLUG", "main")
    monkeypatch.setattr(settings, "APP_ROLE", "primary")
    monkeypatch.setattr(settings, "API_READY_ENABLED", True)


@pytest.mark.asyncio
async def test_api_auth_activation_payload_and_no_write(async_client, db, enabled, monkeypatch):
    for headers in ({}, {"Authorization": "Bearer wrong"}):
        response = await async_client.post("/api/integrations/tenders/leads", json=item(), headers=headers)
        assert response.status_code == 401
    headers = {"Authorization": "Bearer dedicated-test-key"}
    bad = item() | {"tenant_id": 999}
    assert (await async_client.post("/api/integrations/tenders/leads", json=bad, headers=headers)).status_code == 422
    monkeypatch.setattr(settings, "BELZAKUPKI_LEAD_PUSH_ENABLED", False)
    assert (await async_client.post("/api/integrations/tenders/leads", json=item(), headers=headers)).status_code == 503
    assert not list((await db.execute(select(Order))).scalars())
    assert not list((await db.execute(select(BelzakupkiImportCheckpoint))).scalars())


@pytest.mark.asyncio
async def test_api_create_replay_and_staff_stale_checkpoint_preservation(async_client, db, enabled):
    headers = {"Authorization": "Bearer dedicated-test-key"}
    await BelzakupkiImportService.import_page(db, tenant_scope=SCOPE,
        page={"items": [], "next_cursor": "pull-only-cursor", "has_more": True}, cursor_before=None)
    checkpoint = (await db.execute(select(BelzakupkiImportCheckpoint))).scalar_one()
    checkpoint_before = (checkpoint.cursor, checkpoint.updated_at)
    await db.rollback()
    response = await async_client.post("/api/integrations/tenders/leads", json=item(), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "created"
    replay = await async_client.post("/api/integrations/tenders/leads", json=item(), headers=headers)
    assert replay.json()["outcome"] == "unchanged"
    order = (await db.execute(select(Order))).scalar_one()
    from services.leads_inbox_service import LeadsInboxService
    inbox = await LeadsInboxService.get_leads_inbox(db, tenant_scope=SCOPE, username="push-test")
    assert len(inbox.items) == 1
    assert inbox.items[0].source_kind == "tender"
    assert inbox.items[0].tender.reason == "HVAC relevance"
    assert inbox.items[0].tender.profile_name == "HVAC"
    assert inbox.items[0].tender.url == "https://example.test/tender/42"
    assert order.customer_id is None and order.status == OrderStatus.NEW_LEAD
    assert order.tenant_id == 1 and order.storefront_id == 1
    assert order.technical_meta["belzakupki"]["matches"]["11"]["reason"] == "HVAC relevance"
    order.title, order.comment, order.status = "Staff title", "Staff comment", OrderStatus.NEGOTIATION
    await db.commit()
    fresh = item()
    fresh["updated_at"] = "2026-10-09T11:00:00+00:00"
    fresh["tender"]["title"] = "New source title"
    assert (await async_client.post("/api/integrations/tenders/leads", json=fresh, headers=headers)).json()["outcome"] == "updated"
    assert (await async_client.post("/api/integrations/tenders/leads", json=item(), headers=headers)).json()["outcome"] == "unchanged"
    db.expire_all()
    order = (await db.execute(select(Order))).scalar_one()
    checkpoint = (await db.execute(select(BelzakupkiImportCheckpoint))).scalar_one()
    assert (order.title, order.comment, order.status) == ("Staff title", "Staff comment", OrderStatus.NEGOTIATION)
    assert order.technical_meta["belzakupki"]["tender"]["title"] == "New source title"
    assert (checkpoint.cursor, checkpoint.updated_at) == checkpoint_before


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["demo", "tenant", "storefront", "standby", "missing-config"])
async def test_destination_and_write_gates_do_not_write(db, enabled, monkeypatch, kind):
    if kind in {"demo", "tenant", "storefront"}:
        model = Storefront if kind == "storefront" else Tenant
        row = (await db.execute(select(model).where(model.id == 1))).scalar_one()
        if kind == "demo":
            row.demo_read_only = True
        else:
            row.status = "disabled"
        await db.commit()
    elif kind == "standby":
        monkeypatch.setattr(settings, "APP_ROLE", "standby")
    else:
        monkeypatch.setattr(settings, "BELZAKUPKI_IMPORT_TENANT_SLUG", "")
    with pytest.raises((LeadPushScopeDenied, LeadPushUnavailable)):
        await BelzakupkiLeadPushService.push(db, NativeOpportunity.model_validate(item()))
    assert not list((await db.execute(select(Order))).scalars())
    assert not list((await db.execute(select(BelzakupkiImportCheckpoint))).scalars())


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["rejected", "expired", "unknown"])
async def test_nonactionable_cannot_create(db, enabled, state):
    payload = item()
    if state == "expired":
        payload["tender"]["deadline_at"] = "2000-01-01T00:00:00+00:00"
    else:
        payload["relevance_status"] = state
    result = await BelzakupkiLeadPushService.push(db, NativeOpportunity.model_validate(payload))
    assert result.outcome == "skipped" and result.order_id is None
    assert not list((await db.execute(select(Order))).scalars())


@pytest.mark.asyncio
async def test_concurrent_push_pull_profiles_share_one_order(db_engine, enabled):
    sessions = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async def push(match_id):
        payload = item()
        payload["id"] = match_id
        async with sessions() as session:
            return await BelzakupkiLeadPushService.push(session, NativeOpportunity.model_validate(payload))
    async def pull():
        payload = item()
        payload["id"] = 13
        async with sessions() as session:
            return await BelzakupkiImportService.import_page(session, tenant_scope=SCOPE,
                page={"items": [payload], "next_cursor": None, "has_more": False}, cursor_before=None)
    await asyncio.gather(push(11), push(12), pull())
    async with sessions() as session:
        orders = list((await session.execute(select(Order))).scalars())
        assert len(orders) == 1
        assert set(orders[0].technical_meta["belzakupki"]["matches"]) == {"11", "12", "13"}


@pytest.mark.asyncio
async def test_readonly_database_fails_before_checkpoint_write(db_engine, enabled):
    async with db_engine.connect() as connection:
        connection = await connection.execution_options(postgresql_readonly=True)
        async with AsyncSession(bind=connection) as session:
            with pytest.raises(LeadPushUnavailable):
                await BelzakupkiLeadPushService.push(session, NativeOpportunity.model_validate(item()))
            assert not list((await session.execute(select(Order))).scalars())
            assert not list((await session.execute(select(BelzakupkiImportCheckpoint))).scalars())


@pytest.mark.asyncio
@pytest.mark.parametrize("staff_state", ["archived", "linked"])
async def test_source_rejection_preserves_staff_archive_or_link(db, enabled, staff_state):
    from datetime import datetime, timezone
    from models.leads_inbox import InboxTriageState
    created = await BelzakupkiLeadPushService.push(db, NativeOpportunity.model_validate(item()))
    order = (await db.execute(select(Order).where(Order.id == created.order_id))).scalar_one()
    if staff_state == "archived":
        db.add(InboxTriageState(entity_kind="order", entity_id=order.id, order_id=order.id,
            tenant_id=1, storefront_id=1, archived_at=datetime.now(timezone.utc), outcome="spam"))
    else:
        target = Order(tenant_id=1, storefront_id=1, title="Existing business order", status=OrderStatus.NEGOTIATION)
        db.add(target)
        await db.flush()
        order.linked_order_id = target.id
    await db.commit()
    rejected = item()
    rejected.update(updated_at="2026-10-09T12:00:00+00:00", relevance_status="rejected", eligible=False)
    refreshed = await BelzakupkiLeadPushService.push(db, NativeOpportunity.model_validate(rejected))
    assert refreshed.outcome == "updated" and refreshed.order_id == created.order_id
    db.expire_all()
    order = (await db.execute(select(Order).where(Order.id == created.order_id))).scalar_one()
    assert order.status == OrderStatus.NEW_LEAD
    if staff_state == "archived":
        assert (await db.execute(select(InboxTriageState))).scalar_one().archived_at is not None
    else:
        assert order.linked_order_id is not None
    from services.leads_inbox_service import LeadsInboxService
    active = await LeadsInboxService.get_leads_inbox(db, tenant_scope=SCOPE, username="push-test")
    assert not active.items
