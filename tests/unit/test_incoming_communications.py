from datetime import datetime, timezone

import pytest
from sqlmodel import select

from models import IntegrationOutboxEvent, Lead, LeadSource, Order, OrderStatus
from schemas import LeadCreatePayload
from services.belzakupki_import_service import BelzakupkiImportService
from services.communications.incoming_contracts import (
    TENANT_INCOMING_CREATED_EVENT, TENANT_INCOMING_TEMPLATE_KEY,
    TenantIncomingCreatedPayloadV1,
)
from services.communications.incoming_events import IncomingEventService
from services.communications.processing_scope import ALL_EVENT_TYPES, ALL_TEMPLATE_KEYS
from services.communications.template_registry import WebsiteTemplateRegistry
from services.lead_command_service import LeadCommandService
from services.order_service import OrderService
from services.tenant_scope_service import TenantScope
from tests.unit.test_belzakupki_import_service import NOW, _item
from tests.unit.test_communications_dispatcher import communications_session_factory
from tests.unit.tenant_website_test_support import add_tenant_members


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


async def _events(db):
    return list((await db.execute(select(IntegrationOutboxEvent).where(
        IntegrationOutboxEvent.event_type == TENANT_INCOMING_CREATED_EVENT))).scalars())


@pytest.mark.parametrize("source", ["phone", "bot", "email", "manager", "other", "site"])
async def test_raw_lead_creation_snapshots_original_and_replay_is_deduplicated(db, source):
    result = await LeadCommandService.create_lead(db, LeadCreatePayload(
        source=source, request_text="Оригинальный <текст> & детали", name="Имя",
        phone="+375291234567", email="customer@example.test"), tenant_scope=SCOPE)
    lead = await db.get(Lead, result["id"])
    await IncomingEventService.enqueue_lead(db, lead)
    await db.commit()
    events = await _events(db)
    assert len(events) == 1
    assert events[0].aggregate_id == str(lead.id)
    assert events[0].payload["request_text"] == lead.request_text
    assert events[0].payload["source"] == source
    plan = WebsiteTemplateRegistry.plan(events[0])
    assert plan.audience == "tenant_website_management"
    text = WebsiteTemplateRegistry.render(plan)
    assert "&lt;текст&gt; &amp; детали" in text
    assert f"leads?incomingId={lead.id}" in text


async def test_dedicated_website_lead_suppresses_generic_event(db):
    await LeadCommandService.create_lead(db, LeadCreatePayload(
        source="site", request_text="С сайта"), tenant_scope=SCOPE, notify_incoming=False)
    assert await _events(db) == []


async def test_enqueue_failure_rolls_back_raw_lead(db, monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("outbox unavailable")
    monkeypatch.setattr(IncomingEventService, "enqueue_lead", fail)
    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await LeadCommandService.create_lead(db, LeadCreatePayload(
            source="phone", request_text="Новый звонок"), tenant_scope=SCOPE)
    assert list((await db.execute(select(Lead))).scalars()) == []
    assert await _events(db) == []


@pytest.mark.parametrize("source,status,expected", [
    (LeadSource.EMAIL, OrderStatus.NEW_LEAD, 1),
    (LeadSource.BOT, OrderStatus.NEW_LEAD, 1),
    (LeadSource.SITE, OrderStatus.NEW_LEAD, 1),
    (LeadSource.PHONE, OrderStatus.NEGOTIATION, 0),
])
async def test_order_creation_only_new_incoming(db, source, status, expected):
    order = await OrderService.create_from_website(
        db, tenant_scope=SCOPE, customer_name="Имя", customer_phone="+375291234567",
        customer_email="customer@example.test", customer_address=None, items=[],
        lead_source=source, initial_status=status, comment="Резюме",
        order_technical_meta={"email_source_text": "Оригинал письма"}, commit=False)
    events = await _events(db)
    assert len(events) == expected
    if expected:
        assert events[0].payload["request_text"] == "Оригинал письма"
        assert events[0].payload["entity_id"] == order.id
    await db.rollback()
    assert list((await db.execute(select(Order))).scalars()) == []
    assert await _events(db) == []


async def test_belzakupki_only_creation_not_reimport_or_update_notifies(db):
    first = await BelzakupkiImportService.import_page(db, tenant_scope=SCOPE,
        page={"items": [_item()], "next_cursor": "next", "has_more": True},
        cursor_before=None, now=NOW)
    second = await BelzakupkiImportService.import_page(db, tenant_scope=SCOPE,
        page={"items": [_item(match_id=11)], "next_cursor": None, "has_more": False},
        cursor_before="next", now=NOW)
    assert first.created == 1 and second.created == 0
    events = await _events(db)
    assert len(events) == 1
    assert events[0].payload["source"] == "belzakupki"
    assert events[0].payload["name"] == "ОАО Заказчик"
    assert events[0].payload["email"] == "contact@example.test"


def test_scope_requires_generic_backlog_and_bounded_rendering():
    assert TENANT_INCOMING_CREATED_EVENT in ALL_EVENT_TYPES
    assert TENANT_INCOMING_TEMPLATE_KEY in ALL_TEMPLATE_KEYS
    payload = TenantIncomingCreatedPayloadV1(tenant_id=1, storefront_id=1,
        entity_type="order", entity_id=42, source="email", name="<" * 240,
        phone="&" * 100, email="<" * 254, request_text="<&😀" * 4000)
    plan = WebsiteTemplateRegistry.plan_delivery(channel="telegram",
        template_key=TENANT_INCOMING_TEMPLATE_KEY, template_version=1,
        render_context=payload.model_dump(mode="json"))
    text = WebsiteTemplateRegistry.render(plan)
    assert len(text) <= 4096
    assert "orders/kanban?orderId=42" in text


def test_website_template_preserves_old_snapshot_and_optional_context():
    from services.communications.contracts import TenantWebsiteContactLeadCreatedPayloadV1
    from services.communications.tenant_website_events import TENANT_WEBSITE_CONTACT_TEMPLATE_KEY
    old = TenantWebsiteContactLeadCreatedPayloadV1(tenant_id=1, storefront_id=1,
        lead_id=42, status="new", name="Иван", phone="+375291234567").model_dump(mode="json")
    old.pop("submission_context", None)
    plan = WebsiteTemplateRegistry.plan_delivery(channel="telegram",
        template_key=TENANT_WEBSITE_CONTACT_TEMPLATE_KEY, template_version=1,
        render_context=old)
    assert plan.render_context == old
    new = {**old, "submission_context": {"page_path": "/services", "form_id": "contact"}}
    plan = WebsiteTemplateRegistry.plan_delivery(channel="telegram",
        template_key=TENANT_WEBSITE_CONTACT_TEMPLATE_KEY, template_version=1,
        render_context=new)
    assert plan.render_context["submission_context"]["page_path"] == "/services"


@pytest.mark.parametrize("changed", [None, "membership", "role", "opt_out", "tenant", "storefront", "destination"])
async def test_generic_final_boundary_revalidates_all_mode_recipient(
    communications_session_factory, changed,
):
    from models import CommunicationDelivery, StaffUser, Tenant, Storefront, TenantMembership
    from services.communications.delivery_service import CommunicationDeliveryService
    from services.communications.dispatcher import CommunicationOutboxDispatcher
    from services.communications.processing_scope import CommunicationProcessingScope
    from services.communications.provider_boundary_authorization import (
        prepare_website_provider_boundary, WebsiteCanaryProviderBoundaryRejected,
    )

    scope = CommunicationProcessingScope.all(control_revision=1,
        event_created_at_watermark=datetime(2000, 1, 1, tzinfo=timezone.utc))
    async with communications_session_factory() as session:
        owner = StaffUser(display_name="Owner", status="active", roles=["owner"],
                          primary_role="owner", telegram_id=10001)
        await add_tenant_members(session, owner)
        await session.commit()
        await LeadCommandService.create_lead(session, LeadCreatePayload(
            source="phone", request_text="Новый звонок"), tenant_scope=SCOPE)
        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session, dispatcher_id="test-dispatcher", scope=scope)
        assert outcome is not None and outcome.delivery_count == 1
        await session.commit()
        claim = await CommunicationDeliveryService.claim_next(
            session, scope=scope, worker_id="test-worker", lease_seconds=60)
        assert claim is not None
        await session.commit()
        authorize = await prepare_website_provider_boundary(session, scope=scope, claim=claim)
        if changed == "membership":
            membership = (await session.execute(select(TenantMembership))).scalar_one()
            membership.status = "disabled"
            session.add(membership)
        elif changed == "role":
            membership = (await session.execute(select(TenantMembership))).scalar_one()
            membership.role = "manager"
            session.add(membership)
        elif changed == "opt_out":
            owner.telegram_notifications_enabled = False
            session.add(owner)
        elif changed == "tenant":
            tenant = await session.get(Tenant, 1)
            tenant.status = "disabled"
            session.add(tenant)
        elif changed == "storefront":
            storefront = await session.get(Storefront, 1)
            storefront.status = "disabled"
            session.add(storefront)
        elif changed == "destination":
            owner.telegram_id = 10002
            session.add(owner)
        await session.flush()
        delivery = await session.get(CommunicationDelivery, claim.delivery_id)
        if changed:
            with pytest.raises(WebsiteCanaryProviderBoundaryRejected):
                await authorize(delivery)
        else:
            await authorize(delivery)
