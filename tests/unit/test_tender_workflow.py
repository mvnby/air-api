from datetime import datetime, timedelta, timezone
import copy
import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from models import GlobalConfig, LeadSource, Order, OrderStatus
from models.leads_inbox import InboxEvent, InboxTriageState
from models.tenancy import Storefront, Tenant, TenantScope
from models.tender_workflow import TenderWorkflowLink
from schemas_leads_inbox import TenderWorkflowPayload
from services.leads_inbox_expiry_service import LeadsInboxExpiryService as Expiry
from services.leads_inbox_command_service import LeadsInboxCommandService as Commands
from services.leads_inbox_service import InboxError, LeadsInboxService as Inbox
from services.tender_workflow_service import TenderWorkflowService as Workflow
from services.unified_inbox_service import UnifiedInboxService

SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
NOW = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)


async def tender(db, identity, deadline=None, **kwargs):
    order = Order(tenant_id=1, storefront_id=1, lead_source=LeadSource.BELZAKUPKI,
        status=OrderStatus.NEW_LEAD, source_fingerprint=f"tender:{identity}",
        title=f"Закупка {identity}", technical_meta={"belzakupki": {"last_synced_at": NOW.isoformat(),
            "tender": {"source": "goszakupki", "external_id": identity,
                "deadline_at": deadline.isoformat() if deadline else None, "url": f"https://example.test/{identity}"}}}, **kwargs)
    db.add(order)
    await db.commit()
    return order


async def update(db, order, stage, deadline=None):
    return await Workflow.update(db, order_id=order.id, tenant_scope=SCOPE, username="alice",
        payload=TenderWorkflowPayload(stage=stage, deadline_at=deadline))


@pytest.mark.asyncio
async def test_archived_price_and_publication_keep_independent_identity_context_and_history(db):
    price = await tender(db, "price-101", NOW - timedelta(days=10))
    publication = await tender(db, "publication-202", NOW + timedelta(days=5))
    db.add(InboxTriageState(entity_kind="order", entity_id=price.id, order_id=price.id,
        tenant_id=1, storefront_id=1, outcome="deadline_expired", archived_at=NOW - timedelta(days=1)))
    await db.commit()
    originals = copy.deepcopy([price.technical_meta, publication.technical_meta])
    await update(db, price, "price_sent", NOW - timedelta(days=10))
    linked = await Workflow.associate(db, order_id=publication.id, price_order_id=price.id, tenant_scope=SCOPE, username="bob")
    assert linked.stage == "announced" and linked.price_enquiry.order_id == price.id
    assert linked.price_enquiry.external_id == "price-101" and linked.price_enquiry.archived
    assert linked.deadline_at == NOW + timedelta(days=5)
    assert (await Workflow.read(db, order_id=price.id, tenant_scope=SCOPE)).publications[0].external_id == "publication-202"
    assert [price.technical_meta, publication.technical_meta] == originals
    assert price.status == publication.status == OrderStatus.NEW_LEAD
    await Workflow.dissociate(db, order_id=publication.id, tenant_scope=SCOPE, username="alice")
    unlinked = await Workflow.dissociate(db, order_id=publication.id, tenant_scope=SCOPE, username="alice")
    assert unlinked.price_enquiry is None and unlinked.stage == "announced"
    assert [event.kind for event in unlinked.history] == ["tender_unlink", "tender_link"]
    assert (await db.execute(select(InboxTriageState).where(InboxTriageState.entity_id == price.id))).scalar_one().archived_at


@pytest.mark.asyncio
async def test_qualified_price_stays_searchable_and_reachable_from_publication(db):
    price = await tender(db, "old")
    price.status = OrderStatus.NEGOTIATION
    db.add(price)
    await db.commit()
    publication = await tender(db, "new")
    candidates = await Workflow.candidates(db, order_id=publication.id, tenant_scope=SCOPE, search=str(price.id))
    assert [candidate.order_id for candidate in candidates] == [price.id]
    await update(db, price, "price_request")
    await Workflow.associate(db, order_id=publication.id, price_order_id=price.id, tenant_scope=SCOPE, username="alice")
    assert (await Workflow.read(db, order_id=price.id, tenant_scope=SCOPE)).stage == "price_request"
    assert (await Inbox.detail(db, order_id=publication.id, username="alice", tenant_scope=SCOPE)).tender_workflow.price_enquiry.order_id == price.id


@pytest.mark.asyncio
async def test_effective_stage_deadline_controls_sort_projection_and_expiry(db):
    db.add(GlobalConfig(key="inbox_tender_archive_mode", value="execute"))
    await db.commit()
    first = await tender(db, "first", NOW - timedelta(days=8))
    second = await tender(db, "second", NOW + timedelta(days=1))
    await update(db, first, "announced", NOW + timedelta(days=5))
    page = await Inbox.get_leads_inbox(db, tenant_scope=SCOPE, username="alice", sort="deadline", limit=1)
    assert page.items[0].id == second.id
    unified = await UnifiedInboxService.get_leads_inbox(db, tenant_scope=SCOPE, username="alice", sort="deadline", limit=1)
    assert unified.items[0].id == second.id
    assert (await Expiry.run(db, execute=True, now=NOW, tenant_scope=SCOPE))["archived"] == 0
    await update(db, first, "submitted", NOW - timedelta(days=3))
    page = await Inbox.get_leads_inbox(db, tenant_scope=SCOPE, username="alice", sort="deadline", limit=1)
    assert page.items[0].id == first.id and page.items[0].deadline_at == NOW - timedelta(days=3)
    assert page.items[0].auto_archive_at is None
    assert (await Expiry.run(db, execute=True, now=NOW, tenant_scope=SCOPE))["archived"] == 0
    await update(db, first, "completed")
    assert (await Expiry.run(db, execute=True, now=NOW, tenant_scope=SCOPE))["archived"] == 0
    assert (await Inbox.detail(db, order_id=first.id, username="alice", tenant_scope=SCOPE)).deadline_at is None


@pytest.mark.asyncio
async def test_manual_current_deadline_expires_and_restore_suppresses_that_exact_deadline(db):
    order = await tender(db, "manual-expiry", NOW + timedelta(days=10))
    old = NOW - timedelta(days=3)
    await update(db, order, "announced", old)
    assert (await Expiry.run(db, execute=True, now=NOW, tenant_scope=SCOPE))["archived"] == 1
    await Commands.restore(db, order_id=order.id, username="alice", tenant_scope=SCOPE)
    assert (await Expiry.run(db, execute=True, now=NOW, tenant_scope=SCOPE))["archived"] == 0
    await update(db, order, "announced", NOW - timedelta(days=2))
    assert (await Expiry.run(db, execute=True, now=NOW, tenant_scope=SCOPE))["archived"] == 1


@pytest.mark.asyncio
async def test_concurrent_same_link_and_unlink_audit_once_under_order_locks(db_engine, monkeypatch):
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as seed:
        price = await tender(seed, "concurrent-price")
        publication = await tender(seed, "concurrent-publication")
        price_id, publication_id = price.id, publication.id
        await update(seed, price, "price_request")

    async def associate():
        async with sessions() as session:
            return await Workflow.associate(session, order_id=publication_id, price_order_id=price_id,
                tenant_scope=SCOPE, username="alice")
    linked = await asyncio.wait_for(asyncio.gather(associate(), associate()), 10)
    assert all(result.price_enquiry.order_id == price_id for result in linked)
    original_order = Workflow.order
    ready = asyncio.Event()
    calls = 0
    async def synchronize(session, order_id, scope, *, lock=False):
        nonlocal calls
        if not lock and order_id == publication_id:
            calls += 1
            if calls == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), 5)
        return await original_order(session, order_id, scope, lock=lock)
    monkeypatch.setattr(Workflow, "order", synchronize)
    async def dissociate():
        async with sessions() as session:
            return await Workflow.dissociate(session, order_id=publication_id, tenant_scope=SCOPE, username="alice")
    removed = await asyncio.wait_for(asyncio.gather(dissociate(), dissociate()), 10)
    assert all(result.price_enquiry is None for result in removed)
    async with sessions() as verify:
        events = (await verify.execute(select(InboxEvent).where(InboxEvent.entity_id == publication_id))).scalars().all()
        assert [event.kind for event in events].count("tender_link") == 1
        assert [event.kind for event in events].count("tender_unlink") == 1


@pytest.mark.asyncio
async def test_old_price_deadline_cannot_archive_associated_new_publication(db):
    price = await tender(db, "price", NOW - timedelta(days=8))
    publication = await tender(db, "publication", NOW + timedelta(days=2))
    await update(db, price, "price_sent", NOW - timedelta(days=8))
    await Workflow.associate(db, order_id=publication.id, price_order_id=price.id, tenant_scope=SCOPE, username="alice")
    report = await Expiry.run(db, execute=True, now=NOW, tenant_scope=SCOPE)
    assert report["archived"] == 0
    assert (await Inbox.detail(db, order_id=price.id, username="alice", tenant_scope=SCOPE)).auto_archive_at is None


@pytest.mark.asyncio
async def test_imported_source_replacement_does_not_overwrite_manual_stage_or_deadline(db):
    order = await tender(db, "publication", NOW - timedelta(days=5))
    manual = NOW + timedelta(days=10)
    await update(db, order, "submitted", manual)
    order.technical_meta = {"belzakupki": {"last_synced_at": NOW.isoformat(), "tender": {
        "external_id": "publication", "source": "goszakupki", "deadline_at": (NOW - timedelta(days=1)).isoformat()}}}
    db.add(order)
    await db.commit()
    current = await Workflow.read(db, order_id=order.id, tenant_scope=SCOPE)
    assert current.stage == "submitted" and current.deadline_at == manual and current.deadline_manual
    assert (await Expiry.run(db, execute=True, now=NOW, tenant_scope=SCOPE))["archived"] == 0


@pytest.mark.asyncio
async def test_missing_foreign_scope_demo_cycles_and_stage_role_conflicts_are_rejected(db):
    price = await tender(db, "price")
    publication = await tender(db, "publication")
    await update(db, price, "price_request")
    foreign = TenantScope(tenant_id=1, storefront_id=2, is_system=False)
    with pytest.raises(InboxError) as missing:
        await Workflow.associate(db, order_id=publication.id, price_order_id=price.id, tenant_scope=foreign, username="alice")
    assert missing.value.status_code == 404
    with pytest.raises(InboxError):
        await Workflow.associate(db, order_id=price.id, price_order_id=price.id, tenant_scope=SCOPE, username="alice")
    with pytest.raises(InboxError) as demo:
        await Workflow.update(db, order_id=price.id, tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True, demo_read_only=True),
            username="alice", payload=TenderWorkflowPayload(stage="price_sent"))
    assert demo.value.status_code == 403
    await Workflow.associate(db, order_id=publication.id, price_order_id=price.id, tenant_scope=SCOPE, username="alice")
    with pytest.raises(InboxError):
        await update(db, publication, "price_request")
    with pytest.raises(InboxError):
        await update(db, price, "announced")
    third = await tender(db, "third")
    with pytest.raises(InboxError):
        await Workflow.associate(db, order_id=third.id, price_order_id=publication.id, tenant_scope=SCOPE, username="alice")


@pytest.mark.asyncio
async def test_foreign_tenant_and_storefront_candidates_and_links_are_fenced_by_database(db):
    db.add(Tenant(id=2, slug="foreign-tender", display_name="Foreign"))
    await db.flush()
    db.add(Storefront(id=2, tenant_id=1, slug="other-tender", display_name="Other"))
    db.add(Storefront(id=3, tenant_id=2, slug="foreign", display_name="Foreign"))
    await db.commit()
    publication = await tender(db, "publication")
    publication_id = publication.id
    for tenant_id, storefront_id in [(1, 2), (2, 3)]:
        price = Order(tenant_id=tenant_id, storefront_id=storefront_id, lead_source=LeadSource.EMAIL,
            status=OrderStatus.NEGOTIATION, title="Foreign price")
        db.add(price)
        await db.commit()
        price_id = price.id
        with pytest.raises(InboxError) as blocked:
            await Workflow.associate(db, order_id=publication_id, price_order_id=price_id,
                tenant_scope=SCOPE, username="alice")
        assert blocked.value.status_code == 404
        assert not await Workflow.candidates(db, order_id=publication_id, tenant_scope=SCOPE, search="Foreign")
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(TenderWorkflowLink(publication_order_id=publication_id, price_order_id=price_id,
                    tenant_id=1, storefront_id=1))
                await db.flush()
    assert not (await db.execute(select(InboxEvent).where(InboxEvent.kind == "tender_link"))).scalars().all()


@pytest.mark.parametrize("payload", [{"stage": "unknown"}, {"stage": "price_request", "deadline_at": "2026-10-09T12:00:00"}])
def test_stage_and_deadline_validate(payload):
    with pytest.raises(ValidationError):
        TenderWorkflowPayload(**payload)
