from datetime import datetime, timedelta, timezone
import asyncio

import pytest
from pydantic import ValidationError
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models import Customer, GlobalConfig, LeadSource, Order, OrderStatus
from models.leads_inbox import InboxEvent, InboxReadState, InboxTriageState
from models.tenancy import Storefront, Tenant, TenantScope
from schemas_leads_inbox import InboxArchivePayload, InboxNoAnswerPayload, InboxTenderPayload
from services.leads_inbox_command_service import LeadsInboxCommandService as Commands
from services.leads_inbox_expiry_service import LeadsInboxExpiryService as Expiry
from services.leads_inbox_service import InboxError, LeadsInboxService as Inbox

SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)


async def incoming(db, **fields):
    order = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD, **fields)
    db.add(order)
    await db.commit()
    return order


def tender_meta(deadline):
    return {"belzakupki": {"last_synced_at": NOW.isoformat(), "tender": {
        "source": "goszakupki", "external_id": "123", "deadline_at": deadline.isoformat(),
        "title": "Закупка оборудования", "estimated_value": "10000.50"}}}


@pytest.mark.asyncio
async def test_read_is_personal_persisted_and_separate_from_pending(db):
    first = await incoming(db, title="Первое")
    second = await incoming(db, title="Второе")
    result = await Inbox.counts(db, username="alice", tenant_scope=SCOPE)
    assert result.pending_count == result.unread_count == 2
    await Commands.read(db, order_id=first.id, username="alice", tenant_scope=SCOPE, is_read=True)
    result = await Inbox.counts(db, username="alice", tenant_scope=SCOPE)
    assert (result.pending_count, result.unread_count, result.count, result.has_new) == (2, 1, 1, True)
    assert (await Inbox.counts(db, username="bob", tenant_scope=SCOPE)).unread_count == 2
    marker = (await db.execute(select(InboxReadState).where(InboxReadState.username == "alice"))).scalar_one()
    assert marker.is_read and marker.read_at
    unread = await Inbox.get_leads_inbox(db, username="alice", tenant_scope=SCOPE, unread_only=True)
    assert [item.id for item in unread.items] == [second.id]
    await Commands.read(db, order_id=first.id, username="alice", tenant_scope=SCOPE, is_read=False)
    assert (await Inbox.counts(db, username="alice", tenant_scope=SCOPE)).unread_count == 2


@pytest.mark.parametrize("payload", [
    {"outcome": "refusal"}, {"outcome": "refusal", "reason": "other", "note": "   "},
    {"outcome": "spam", "reason": "profile"}, {"outcome": "deadline_expired"},
])
def test_archive_validates_domain_choices(payload):
    with pytest.raises(ValidationError):
        InboxArchivePayload(**payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,reason", [("refusal", "profile"), ("spam", None), ("duplicate", None)])
async def test_archive_restore_never_loses_order_or_customer(db, outcome, reason):
    customer = Customer(tenant_id=1, name="Клиент", phone="")
    db.add(customer)
    await db.flush()
    order = await incoming(db, customer_id=customer.id)
    archived = await Commands.archive(db, order_id=order.id, username="alice", tenant_scope=SCOPE,
        payload=InboxArchivePayload(outcome=outcome, reason=reason))
    assert archived.archive.outcome == outcome
    assert archived.history[0].kind == "archive"
    assert (await Inbox.counts(db, username="alice", tenant_scope=SCOPE)).pending_count == 0
    await db.refresh(order)
    assert order.status == OrderStatus.NEW_LEAD and order.closing_result is None
    assert (await db.get(Customer, customer.id)).name == "Клиент"
    restored = await Commands.restore(db, order_id=order.id, username="alice", tenant_scope=SCOPE)
    assert restored.archive is None and restored.status == "new_lead"
    assert restored.history[0].kind == "restore"
    assert (await Inbox.counts(db, username="alice", tenant_scope=SCOPE)).pending_count == 1


@pytest.mark.asyncio
async def test_no_answer_keeps_history_and_optional_reminder(db):
    order = await incoming(db)
    reminder = NOW + timedelta(days=1)
    await Commands.no_answer(db, order_id=order.id, username="alice", tenant_scope=SCOPE,
        payload=InboxNoAnswerPayload(note="Нет ответа", next_followup_at=reminder))
    result = await Commands.no_answer(db, order_id=order.id, username="bob", tenant_scope=SCOPE,
        payload=InboxNoAnswerPayload(note="Повторный звонок"))
    assert result.no_answer_count == 2 and result.no_answer_at
    assert result.next_followup_at == reminder
    assert [(e.actor, e.note) for e in result.history] == [("bob", "Повторный звонок"), ("alice", "Нет ответа")]
    assert result.archive is None and result.status == "new_lead"


@pytest.mark.asyncio
async def test_legacy_archive_stays_visible_and_restores(db):
    order = Order(tenant_id=1, storefront_id=1, status=OrderStatus.CLOSED,
        closing_result="lost", reject_reason="Ранее отказались")
    db.add(order)
    await db.commit()
    archive = await Inbox.get_leads_inbox(db, username="alice", tenant_scope=SCOPE, scope="archive")
    assert archive.items[0].archive.outcome == "legacy_lost"
    restored = await Commands.restore(db, order_id=order.id, username="alice", tenant_scope=SCOPE)
    assert restored.status == "new_lead" and restored.archive is None
    assert restored.history[0].note == "Ранее отказались"


@pytest.mark.asyncio
async def test_deadline_sort_parses_offsets_before_pagination_and_null_last(db):
    second = await incoming(db, lead_source=LeadSource.BELZAKUPKI, technical_meta=tender_meta(NOW))
    first = await incoming(db, lead_source=LeadSource.BELZAKUPKI,
        technical_meta=tender_meta(datetime(2026, 10, 3, 13, tzinfo=timezone(timedelta(hours=3)))))
    await incoming(db, technical_meta={"belzakupki": {"tender": {"deadline_at": "invalid"}}})
    page = await Inbox.get_leads_inbox(db, username="alice", tenant_scope=SCOPE, sort="deadline", limit=1)
    assert page.total == 3 and page.items[0].id == first.id
    page = await Inbox.get_leads_inbox(db, username="alice", tenant_scope=SCOPE, sort="deadline", limit=1, page=2)
    assert page.items[0].id == second.id


@pytest.mark.asyncio
async def test_expiry_report_then_execute_and_restore_suppresses_same_deadline(db):
    order = await incoming(db, lead_source=LeadSource.BELZAKUPKI, source_fingerprint="a" * 64,
        technical_meta=tender_meta(NOW - timedelta(hours=24)))
    report = await Expiry.run(db, now=NOW, tenant_scope=SCOPE)
    assert report["mode"] == "report_only" and report["archived"] == 0
    assert [c["order_id"] for c in report["candidates"]] == [order.id]
    assert (await Inbox.counts(db, username="alice", tenant_scope=SCOPE)).pending_count == 1
    await Commands.read(db, order_id=order.id, username="alice", tenant_scope=SCOPE, is_read=True)
    assert (await Inbox.counts(db, username="alice", tenant_scope=SCOPE)).unread_count == 0
    result = await Expiry.run(db, now=NOW, tenant_scope=SCOPE, execute=True)
    assert result["archived"] == 1
    await db.refresh(order)
    assert order.status == OrderStatus.NEW_LEAD and order.closing_result is None
    item = await Inbox.detail(db, order_id=order.id, username="alice", tenant_scope=SCOPE)
    assert item.archive.outcome == "deadline_expired"
    await Commands.restore(db, order_id=order.id, username="alice", tenant_scope=SCOPE)
    assert (await Expiry.run(db, now=NOW + timedelta(days=10), tenant_scope=SCOPE, execute=True))["archived"] == 0
    # A changed trusted deadline is independently eligible after its grace.
    order.technical_meta = tender_meta(NOW - timedelta(hours=25))
    db.add(order)
    await db.commit()
    assert (await Expiry.run(db, now=NOW, tenant_scope=SCOPE, execute=True))["archived"] == 1


@pytest.mark.asyncio
async def test_auto_archive_projection_respects_rollout_mode_and_restore(db):
    deadline = NOW + timedelta(days=1)
    order = await incoming(db, lead_source=LeadSource.BELZAKUPKI, source_fingerprint="g" * 64,
        technical_meta=tender_meta(deadline))
    item = await Inbox.detail(db, order_id=order.id, username="alice", tenant_scope=SCOPE)
    assert item.auto_archive_at is None
    db.add(GlobalConfig(key="inbox_tender_archive_mode", value="execute"))
    await db.commit()
    item = await Inbox.detail(db, order_id=order.id, username="alice", tenant_scope=SCOPE)
    assert item.auto_archive_at == deadline + timedelta(hours=24)
    await Commands.archive(db, order_id=order.id, username="alice", tenant_scope=SCOPE,
        payload=InboxArchivePayload(outcome="refusal", reason="terms"))
    item = await Commands.restore(db, order_id=order.id, username="alice", tenant_scope=SCOPE)
    assert item.auto_archive_at is None


@pytest.mark.asyncio
async def test_expiry_excludes_untrusted_linked_qualified_and_grace_period(db):
    qualified = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEGOTIATION)
    db.add(qualified)
    await db.flush()
    cases = [
        {"source_fingerprint": None},
        {"lead_source": LeadSource.EMAIL},
        {"linked_order_id": qualified.id},
        {"status": OrderStatus.NEGOTIATION},
        {"technical_meta": tender_meta(NOW - timedelta(hours=23, minutes=59))},
        {"technical_meta": {"belzakupki": {"last_synced_at": NOW.isoformat(), "tender": {
            "source": "a", "external_id": "123", "deadline_at": "2026-09-01", "deadline_kind": "delivery"}}}},
    ]
    for index, overrides in enumerate(cases):
        fields = dict(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD,
            lead_source=LeadSource.BELZAKUPKI, source_fingerprint=str(index) * 64,
            technical_meta=tender_meta(NOW - timedelta(days=2)))
        fields.update(overrides)
        db.add(Order(**fields))
    await db.commit()
    assert (await Expiry.run(db, now=NOW, tenant_scope=SCOPE, execute=True))["archived"] == 0


@pytest.mark.asyncio
async def test_tenant_scope_blocks_all_inbox_commands(db):
    tenant = Tenant(slug="triage-foreign", display_name="Foreign")
    db.add(tenant)
    await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug="main", display_name="Foreign")
    db.add(storefront)
    await db.flush()
    order = Order(tenant_id=tenant.id, storefront_id=storefront.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    calls = [
        (Inbox.detail, {}), (Commands.read, {"is_read": True}),
        (Commands.archive, {"payload": InboxArchivePayload(outcome="spam")}),
        (Commands.restore, {}), (Commands.no_answer, {"payload": InboxNoAnswerPayload()}),
    ]
    for method, args in calls:
        with pytest.raises(InboxError) as err:
            await method(db, order_id=order.id, username="alice", tenant_scope=SCOPE, **args)
        assert err.value.status_code == 404
    assert (await Inbox.get_leads_inbox(db, username="alice", tenant_scope=SCOPE)).total == 0


@pytest.mark.asyncio
async def test_archived_order_cannot_be_qualified_through_generic_patch(db):
    from schemas import ManagerOrderUpdatePayload
    from services.order_service import OrderService

    order = await incoming(db)
    await Commands.archive(db, order_id=order.id, username="alice", tenant_scope=SCOPE,
        payload=InboxArchivePayload(outcome="spam"))
    with pytest.raises(ValueError, match="архив|[Aa]rchiv"):
        await OrderService.update_order_for_manager(db, order.id,
            ManagerOrderUpdatePayload(status=OrderStatus.NEGOTIATION), tenant_scope=SCOPE)
    await db.refresh(order)
    assert order.status == OrderStatus.NEW_LEAD


@pytest.mark.asyncio
async def test_commands_compose_without_committing_caller_transaction(db):
    order = await incoming(db)
    async with db.begin_nested() as outer:
        await Commands.archive(db, order_id=order.id, username="alice", tenant_scope=SCOPE,
            payload=InboxArchivePayload(outcome="duplicate"))
        assert (await Inbox.counts(db, username="alice", tenant_scope=SCOPE)).pending_count == 0
        await outer.rollback()
    assert (await Inbox.counts(db, username="alice", tenant_scope=SCOPE)).pending_count == 1
    assert not (await db.execute(select(InboxEvent))).scalars().all()


@pytest.mark.asyncio
async def test_demo_scope_cannot_mutate_personal_or_shared_state(db):
    order = await incoming(db)
    demo = TenantScope(tenant_id=1, storefront_id=1, is_system=True, demo_read_only=True)
    with pytest.raises(InboxError) as err:
        await Commands.read(db, order_id=order.id, username="demo", tenant_scope=demo, is_read=True)
    assert err.value.status_code == 403
    assert (await Inbox.counts(db, username="demo", tenant_scope=SCOPE)).unread_count == 1


@pytest.mark.asyncio
async def test_expiry_rechecks_updated_deadline_after_selecting_candidate(db_engine, monkeypatch):
    from services.tenant_entity_access_service import TenantEntityAccessService

    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as seed:
        order = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD,
            lead_source=LeadSource.BELZAKUPKI, source_fingerprint="z" * 64,
            technical_meta=tender_meta(NOW - timedelta(days=2)))
        seed.add(order)
        await seed.commit()
        order_id = order.id

    selected, updated = asyncio.Event(), asyncio.Event()
    get_order = TenantEntityAccessService.get_order

    async def after_selection(session, entity_id, **kwargs):
        assert kwargs["for_update"] is True and kwargs["populate_existing"] is True
        selected.set()
        await asyncio.wait_for(updated.wait(), 5)
        return await get_order(session, entity_id, **kwargs)

    monkeypatch.setattr(TenantEntityAccessService, "get_order", after_selection)
    async with sessions() as expiry:
        job = asyncio.create_task(Expiry.run(expiry, now=NOW, tenant_scope=SCOPE, execute=True))
        await asyncio.wait_for(selected.wait(), 5)
        async with sessions() as importer:
            fresh = (await importer.execute(select(Order).where(Order.id == order_id).with_for_update())).scalar_one()
            fresh.technical_meta = tender_meta(NOW + timedelta(days=1))
            importer.add(fresh)
            await importer.commit()
        updated.set()
        result = await asyncio.wait_for(job, 5)
    assert result["archived"] == 0


@pytest.mark.parametrize("fields", [
    {"is_tender": True, "deadline_at": "2026-10-01T12:00:00"},
    {"is_tender": True, "source_url": "javascript:alert(1)"},
])
def test_manual_email_tender_requires_aware_date_and_http_source(fields):
    with pytest.raises(ValidationError):
        InboxTenderPayload(**fields)


@pytest.mark.asyncio
async def test_email_tender_expiry_requires_explicit_manager_confirmation_and_is_reversible(db):
    order = await incoming(db, lead_source=LeadSource.EMAIL,
        technical_meta={"email_subject": "Запрос по закупке", "deadline_at": (NOW - timedelta(days=2)).isoformat()},
        comment="AI предполагает закупку и истечение срока")
    db.add(GlobalConfig(key="inbox_tender_archive_mode", value="execute"))
    await db.commit()
    assert (await Expiry.run(db, tenant_scope=SCOPE, now=NOW, execute=True))["archived"] == 0
    deadline = NOW - timedelta(days=2)
    item = await Commands.tender_context(db, order_id=order.id, username="alice", tenant_scope=SCOPE,
        payload=InboxTenderPayload(is_tender=True, deadline_at=deadline, source_url="https://goszakupki.by/tenders/123"))
    assert item.source == "email" and item.source_kind == "tender"
    assert item.deadline_at == deadline and item.auto_archive_at == deadline + timedelta(hours=24)
    assert item.history[0].kind == "tender_context"
    assert (await Expiry.run(db, tenant_scope=SCOPE, now=NOW, execute=True))["archived"] == 1
    restored = await Commands.restore(db, order_id=order.id, username="alice", tenant_scope=SCOPE)
    assert restored.auto_archive_at is None
    assert (await Expiry.run(db, tenant_scope=SCOPE, now=NOW, execute=True))["archived"] == 0
    # A manager's correction disables expiry without changing the source channel.
    corrected = await Commands.tender_context(db, order_id=order.id, username="alice", tenant_scope=SCOPE,
        payload=InboxTenderPayload(is_tender=False))
    assert corrected.source_kind == "customer_request" and corrected.tender is None
    assert (await Expiry.run(db, tenant_scope=SCOPE, now=NOW, execute=True))["archived"] == 0


@pytest.mark.asyncio
async def test_email_tender_context_preserves_unspecified_deadline_and_cannot_override_import(db):
    email = await incoming(db, lead_source=LeadSource.EMAIL)
    deadline = NOW + timedelta(days=1)
    await Commands.tender_context(db, order_id=email.id, username="alice", tenant_scope=SCOPE,
        payload=InboxTenderPayload(is_tender=True, deadline_at=deadline))
    item = await Commands.tender_context(db, order_id=email.id, username="alice", tenant_scope=SCOPE,
        payload=InboxTenderPayload(is_tender=True, source_url="https://example.test/tender/123"))
    assert item.deadline_at == deadline
    imported = await incoming(db, lead_source=LeadSource.BELZAKUPKI, technical_meta=tender_meta(deadline))
    with pytest.raises(InboxError, match="писем"):
        await Commands.tender_context(db, order_id=imported.id, username="alice", tenant_scope=SCOPE,
            payload=InboxTenderPayload(is_tender=False))
