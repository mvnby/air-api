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


@pytest.mark.parametrize(("title", "location", "decision"), [
    ("Ремонт кондиционеров", "г. Витебск", "recommend"),
    ("Монтаж кондиционеров", "Орша", "recommend"),
    ("Поставка кондиционеров с монтажом", "г. Витебск", "recommend"),
    ("Поставка кондиционеров", "г. Витебск", "review"),
    ("Поставка кондиционеров без монтажа", "г. Витебск", "skip"),
    ("Обслуживание вентиляции", "Орша, Витебская область", "skip"),
    ("Обслуживание вентиляции", "г. Витебск", "review"),
    ("ТО кондиционеров", None, "review"),
])
def test_tender_cards_use_scope_and_work_location(title, location, decision):
    from datetime import timedelta
    from services.communications.tender_cards import native_tender_card

    deadline = datetime.now(timezone.utc) + timedelta(days=7)
    card = native_tender_card({
        "tender": {"title": title, "location": location, "deadline_at": deadline.isoformat()},
        "tender_updated_at": "latest",
        "matches": {"a": {"relevance_status": "confirmed", "eligible": True, "updated_at": "latest"}},
    }, None)
    assert card.status == decision


def test_mail_tender_uses_attachment_and_ignores_buyers_address_and_contract_deadline():
    from datetime import timedelta
    from services.communications.tender_cards import email_tender_card

    deadline = datetime.now(timezone.utc) + timedelta(days=7)
    subject = "Заявка о ценах auc0001234567"
    body = "https://goszakupki.by/marketing/view/1234567"
    assert email_tender_card("Оплата за ремонт кондиционеров", "", ()) is None
    card = email_tender_card(subject, body, (
        "Ремонт кондиционеров\nЮридический адрес заказчика: Минск\n"
        "Место выполнения работ: г. Витебск\nКоличество: 12 кондиционеров\n"
        f"Окончание подачи предложений: {deadline:%d.%m.%Y} 12:00 UTC+03:00\n"
        "Срок выполнения договора: 31.12.2029",
    ))
    assert card.status == "recommend"
    assert card.location == "г. Витебск"
    assert "12 кондиционеров" in card.quantity
    assert card.source_url == body
    assert card.deadline_at.hour == 12


def test_mobile_tender_card_leads_with_work_and_groups_contact_and_terms():
    from services.communications.templates.incoming import render_tenant_incoming_v1

    payload = {
        "tenant_id": 1, "storefront_id": 1, "entity_type": "order", "entity_id": 699,
        "source": "belzakupki", "name": "ГУ «Центр & партнёры»", "request_text": "",
        "email": "office@example.test",
        "tender": {
            "title": "Текущий ремонт помещений в Лепеле (перенос кондиционера)",
            "source_label": "Госзакупки", "reference": "3876716",
            "deadline_at": "2026-11-27T20:59:00Z", "budget_amount": "2450.30", "budget_currency": "BYN",
            "status": "review", "reason": "Часть ТЗ требует сверки с оригиналом",
        },
    }
    result = render_tenant_incoming_v1(payload, text_link=False)
    assert result.split("\n\n") == [
        "📌 <b>Перенос кондиционера</b>",
        "👤 Заказчик: ГУ «Центр &amp; партнёры»\n📧 Почта: office@example.test",
        "⏳ Подать до 27.11.2026, 23:59\n💰 Оценочный бюджет: 2\u202f450,30 BYN",
        "🟡 На проверку · Часть ТЗ требует сверки с оригиналом\nТендер №699 · Госзакупки · 3876716",
    ]

    payload.update(name=None, email=None)
    payload["tender"] = {
        "title": "Монтаж кондиционеров (демонтаж старого оборудования)",
        "source_label": "БЕЛОРУССКАЯ УНИВЕРСАЛЬНАЯ ТОВАРНАЯ БИРЖА",
        "reference": "33445199-067e-491b-b604-5b966d2cd3dc",
        "status": "review", "reason": "Нужно проверить ТЗ",
    }
    result = render_tenant_incoming_v1(payload, text_link=False)
    assert result.split("\n\n") == [
        "📌 <b>Монтаж кондиционеров (демонтаж старого оборудования)</b>",
        "🟡 На проверку · Нужно проверить ТЗ\nТендер №699 · БУТБ",
    ]


async def test_source_attachment_refresh_emits_one_recommendation_and_preserves_original(
    db_engine, monkeypatch,
):
    from datetime import timedelta
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from models import StaffUser
    from schemas_tender_document_reader import TenderDocumentReadResult, TenderDocumentFragment
    from services.communications import tender_document_updates
    from services.communications.delivery_worker import CommunicationDeliveryWorker
    from services.communications.dispatcher import CommunicationOutboxDispatcher
    from services.communications.processing_scope import CommunicationProcessingScope
    from services.communications.provider_boundary_authorization import prepare_website_provider_boundary
    from services.communications.providers.base import ProviderDeliveryResult

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(tender_document_updates, "async_session_maker", session_factory)
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=7)
    url = "https://goszakupki.by/marketing/view/1234567"
    item = _item(deadline_at=deadline.isoformat(), external_id="gias-1")
    item["tender"].update(title="Услуги по закупке", source="gias_by",
                          url="https://gias.by/tenders/gias-1", canonical_url=url)
    mirror = _item(deadline_at=deadline.isoformat(), match_id=11, external_id="1234567")
    mirror["updated_at"] = "2026-09-19T09:00:00Z"
    mirror["tender"].update(title="Услуги по закупке", source="goszakupki_by", url=url)
    seen = []
    complete = False

    async def read_detail(order):
        assert order.technical_meta["belzakupki"]["source"] == "gias_by"
        return {"documents": []}

    async def fetch(source, external_id):
        assert (source, external_id) == ("goszakupki_by", "1234567")
        return httpx.Response(200, json={
            "source": source, "external_id": external_id,
            "documents": [{"id": "pdf", "name": "Смета.pdf", "extracted_text": "я" * 16_606}],
        })

    async def read_original(session, scope, *, order_id, document_id, source_reference):
        assert scope == SCOPE and document_id == "pdf" and source_reference
        seen.append(order_id)
        return TenderDocumentReadResult(
            order_id=order_id, document_id=document_id, status="complete" if complete else "partial",
            fragments=[TenderDocumentFragment(fragment=1, offset=0, method="embedded",
                text="Ремонт кондиционеров\nМесто выполнения работ: г. Витебск\nКоличество: 12 кондиционеров\n"
                + "Примечание к смете.\n" * 900)],
        )

    source_service = tender_document_updates.BelzakupkiEnrichmentService
    monkeypatch.setattr(source_service, "_detail", read_detail)
    monkeypatch.setattr(source_service, "_fetch", fetch)
    monkeypatch.setattr(tender_document_updates, "load_tender_document", read_original)
    async with session_factory() as session:
        await add_tenant_members(session, StaffUser(display_name="Owner", status="active", roles=["owner"],
                                                    primary_role="owner", telegram_id=101))
        await session.commit()
        result = await BelzakupkiImportService.import_page(
            session, tenant_scope=SCOPE, page={"items": [item], "next_cursor": None, "has_more": False},
            cursor_before=None, now=now,
        )
        other = await BelzakupkiImportService.import_page(
            session, tenant_scope=SCOPE, page={"items": [mirror], "next_cursor": None, "has_more": False},
            cursor_before=None, now=now,
        )
        assert other.order_id == result.order_id
        initial, = await _events(session)
        initial_id = initial.event_id
        assert initial.payload["tender"]["status"] == "review"

    await tender_document_updates.refresh_tender_cards(tenant_scope=SCOPE)
    await tender_document_updates.refresh_tender_cards(tenant_scope=SCOPE)
    async with session_factory() as session:
        initial, review = sorted(await _events(session), key=lambda event: event.aggregate_version)
        assert review.payload["tender"]["reason"] == tender_document_updates.PARTIAL_ATTACHMENTS
        assert review.payload["tender"]["status"] == "review"
        assert review.payload["tender"]["prior_event_id"] == initial_id
        order = await session.get(Order, result.order_id)
        order.technical_meta = {key: value for key, value in order.technical_meta.items()
                                if key != tender_document_updates.CHECKED_AT}
        await session.commit()

    complete = True
    await tender_document_updates.refresh_tender_cards(tenant_scope=SCOPE)
    await tender_document_updates.refresh_tender_cards(tenant_scope=SCOPE)
    async with session_factory() as session:
        initial, promotion, review = sorted(await _events(session), key=lambda event: event.aggregate_version)
        assert initial.payload["tender"]["status"] == "review"
        assert promotion.payload["tender"]["status"] == "recommend"
        assert promotion.payload["tender"]["prior_event_id"] == initial_id
        assert promotion.payload["tender"]["location"] == "г. Витебск"
        assert "12 кондиционеров" in promotion.payload["tender"]["quantity"]
        assert seen == [result.order_id, result.order_id]
        assert all(event.payload["name"] == "ОАО Заказчик" for event in (initial, review, promotion))
        assert all(event.payload["email"] == "contact@example.test" for event in (initial, review, promotion))

    scope = CommunicationProcessingScope.all(control_revision=1,
        event_created_at_watermark=now - timedelta(minutes=1))
    for _ in range(3):
        async with session_factory() as session:
            dispatched = await CommunicationOutboxDispatcher.dispatch_next(session, dispatcher_id="tender-cards", scope=scope)
            assert dispatched is not None and dispatched.delivery_count == 1
            await session.commit()

    class RecordingTelegram:
        channel = "telegram"
        messages = []

        async def send(self, *, destination, text, delivery_id, options):
            self.messages.append((destination, text, options))
            return ProviderDeliveryResult.sent(1000 + len(self.messages))

    async def authorize(session, claim):
        return await prepare_website_provider_boundary(session, scope=scope, claim=claim)

    provider = RecordingTelegram()
    worker = CommunicationDeliveryWorker(session_factory=session_factory, provider=provider,
                                         worker_id="tender-cards", scope=scope, provider_boundary_authorizer=authorize)
    assert (await worker.run_once()).outcome == "sent"
    assert (await worker.run_once()).outcome == "sent"
    assert (await worker.run_once()).outcome == "sent"
    assert (await worker.run_once()).outcome == "idle"
    first, edited, updated = provider.messages
    assert first[0] == updated[0] == "101"
    assert first[2].silent and first[2].tender_topic
    assert edited[2].silent and edited[2].edit_only and edited[2].edit_message_id == 1001
    assert "Часть ТЗ требует сверки" in edited[1]
    assert "👤 Заказчик: ОАО Заказчик" in updated[1]
    assert not updated[2].silent and updated[2].edit_message_id == 1001
    assert updated[2].buttons[1] == ("На площадку", url)
