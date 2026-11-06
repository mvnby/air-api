"""Consented attention remains optional internal evidence, never business input."""

from datetime import datetime
import json

import pytest
from pydantic import ValidationError
from sqlmodel import select

from api_contracts.multi_split import MultiSplitLeadPayload
from models import Customer, IntegrationOutboxEvent, Lead, Order, Product
from models.tenancy import TenantScope
from routers.api_leads import installation_estimate_form_payload
from schemas import OrderPayload, ProductAvailabilityLeadPayload, PublicContactLeadPayload
from schemas_incoming import IncomingOrderContext
from schemas_installation_estimate import InstallationEstimateLeadPayload
from schemas_manager_leads import LeadQualifyPayload
from schemas_manager_orders import ManagerOrderDetailResponse
from schemas_website_context import (
    WebsiteInterests, WebsiteSubmissionContext, append_submission_context,
    submission_context_meta, website_interests_from_meta,
)
from services.communications.contracts import (
    TenantWebsiteContactLeadCreatedPayloadV1, TenantWebsiteCheckoutCreatedPayloadV1,
)
from services.communications.outbox_service import IntegrationOutboxService, OutboxEventConflictError
from services.communications.template_registry import WebsiteTemplateRegistry
from services.communications.templates.website import (
    _finish_website_message, render_tenant_website_contact_v1, render_tenant_website_checkout_v1,
)
from services.communications.tenant_website_events import TENANT_WEBSITE_CONTACT_TEMPLATE_KEY
from services.lead_service import LeadService
from services.leads_inbox_projection import LeadsInboxProjection
from services.order_projection_service import OrderProjectionService
from services.public_write_fingerprint_service import PublicWriteFingerprintService
from services.raw_lead_inbox_service import RawLeadInboxService
from services.repair_diagnostic_contracts import RepairDiagnosticLeadPayload, parse_repair_diagnostic_payload
from services.website_lead_service import WebsiteLeadService
from tests.unit.test_communications_dispatcher import communications_session_factory


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


def interests(**overrides):
    return {"version": 1, "consent": True, "items": [{
        "kind": "product", "page_path": "/product/daikin-model", "title": "Daikin FTX <модель>",
        "active_seconds": 123, "product_id": 999, "topics": ["Тихая работа", "Тепловой насос"],
    }], **overrides}


def context(form="contact", **overrides):
    return {"page_path": "/services", "form_id": form, "interests": interests(), **overrides}


def request_payload(form):
    contact = {"name": "Анна", "phone": "+375291112233"}
    if form == "contact":
        return PublicContactLeadPayload(**contact, message="Original message", submission_context=context(form))
    if form == "product_availability":
        return ProductAvailabilityLeadPayload(**contact, product_id=7, submission_context=context(form))
    if form == "installation_estimate":
        return InstallationEstimateLeadPayload(**contact, consent=True, submission_context=context(form))
    if form == "repair_diagnostic":
        return RepairDiagnosticLeadPayload(contact=contact, symptom="not_cooling", submission_context=context(form))
    if form == "multi_split":
        return MultiSplitLeadPayload(**contact, consent=True, submission_context=context(form), configuration={
            "outdoor_product_id": 7, "rooms": [{"name": "Кухня", "indoor_product_id": 8}],
        })
    return OrderPayload(customer=contact, items=[{"product_id": 7, "quantity": 1}], submission_context=context(form))


@pytest.mark.parametrize("form", [
    "contact", "checkout", "installation_calculator", "installation_estimate",
    "repair_diagnostic", "product_availability", "multi_split",
])
def test_all_form_business_fingerprints_ignore_only_passive_attention(form):
    payload = request_payload(form)
    encoded = payload.model_dump(mode="json")
    fingerprint = PublicWriteFingerprintService.for_payload(payload)
    multipart = PublicWriteFingerprintService.for_multipart(payload=payload, attachments=[])
    encoded["submission_context"]["interests"]["items"][0]["active_seconds"] = 1700
    assert PublicWriteFingerprintService.for_payload(encoded) == fingerprint
    assert PublicWriteFingerprintService.for_multipart(payload=encoded, attachments=[]) == multipart
    encoded["submission_context"].pop("interests")
    assert PublicWriteFingerprintService.for_payload(encoded) == fingerprint
    encoded["submission_context"]["interests"] = None
    assert PublicWriteFingerprintService.for_payload(encoded) == fingerprint
    encoded["submission_context"]["page_path"] = "/another-source"
    assert PublicWriteFingerprintService.for_payload(encoded) != fingerprint
    # Normalization never mutates the persisted submission snapshot.
    assert payload.submission_context.interests.items[0].active_seconds == 123


@pytest.mark.parametrize("bad", [None, False, "invalid", {},
    interests(consent=False), interests(consent=1), interests(version=True), interests(version=2),
    interests(items=[]), interests(items=interests()["items"] * 9),
    *[interests(items=[{**interests()["items"][0], **patch}]) for patch in [
        {"title": "x" * 161}, {"title": "Name\nsecret"}, {"title": " "},
        {"topics": ["t"] * 6}, {"topics": ["t" * 81]}, {"topics": ["x\x00"]},
        {"page_path": "//evil.example"}, {"page_path": "/foo?q=private"}, {"page_path": "/foo%0a"},
        {"active_seconds": -1}, {"active_seconds": 1801}, {"active_seconds": True},
        {"active_seconds": "12"}, {"active_seconds": 1.5}, {"product_id": 0}, {"kind": "visitor"},
        {"visitor_id": "stable-id"},
    ]],
])
def test_bad_optional_interests_are_dropped_without_rejecting_request(bad):
    payload = PublicContactLeadPayload(
        name="Анна", phone="+375291112233", message="Original",
        submission_context=context(interests=bad),
    )
    assert payload.message == "Original"
    assert payload.submission_context.page_path == "/services"
    assert payload.submission_context.interests is None
    assert "interests" not in payload.model_dump(mode="json")["submission_context"]
    assert "interests" not in submission_context_meta(payload.submission_context)["submission_context"]


def test_valid_bounded_attention_is_sorted_and_does_not_enter_customer_text():
    items = [{**interests()["items"][0], "active_seconds": n, "kind": kind} for kind, n in [
        ("topic", 0), ("article", 5), ("service", 1800), ("product", 60),
    ]]
    ctx = WebsiteSubmissionContext.model_validate(context(interests=interests(items=items)))
    assert [item.active_seconds for item in ctx.interests.items] == [1800, 60, 5, 0]
    text = append_submission_context("Original message", ctx)
    assert "Original message" in text and "Страница: /services" in text
    for private_internal_fact in ["Daikin", "Тихая работа", "Тепловой насос", "999", "1800"]:
        assert private_internal_fact not in text


@pytest.mark.asyncio
async def test_full_cyrillic_escaped_summaries_roundtrip_through_both_multipart_contracts():
    item = {"kind": "product", "page_path": "/" + "п" * 499, "title": "М" * 160,
            "active_seconds": 1800, "topics": ["т" * 80] * 5, "product_id": 123}
    ctx = context("installation_estimate", page_path="/" + "с" * 499,
                  interests=interests(items=[item] * 8))
    encoded = json.dumps(ctx)  # ensure_ascii uses the largest supported Cyrillic JSON representation.
    assert 4000 < len(encoded) < 65536
    parsed = await installation_estimate_form_payload(
        name="Анна", phone="+375291112233", consent=True, submission_context=encoded,
    )
    assert len(parsed.submission_context.interests.items) == 8
    repair = json.dumps({
        "contact": {"name": "А" * 120, "phone": "+375291112233", "address": "а" * 300},
        "symptom": "other", "client_comment": "к" * 2000,
        "submission_context": {**ctx, "form_id": "repair_diagnostic"},
    })
    assert len(repair.encode()) > 64 * 1024
    assert len(parse_repair_diagnostic_payload(repair).submission_context.interests.items) == 8


def test_legacy_delivery_snapshot_is_unchanged_and_new_snapshot_keeps_integrity():
    payload = TenantWebsiteContactLeadCreatedPayloadV1(
        tenant_id=1, storefront_id=1, lead_id=1, status="new", name="Анна", phone="123",
        submission_context=context(interests=None),
    )
    old_context = payload.model_dump(mode="json")
    assert "interests" not in old_context["submission_context"]
    plan = WebsiteTemplateRegistry.plan_delivery(
        channel="telegram", template_key=TENANT_WEBSITE_CONTACT_TEMPLATE_KEY,
        template_version=1, render_context=old_context,
    )
    assert plan.render_context == old_context
    new_payload = payload.model_copy(update={"submission_context": WebsiteSubmissionContext.model_validate(context())})
    new_plan = WebsiteTemplateRegistry.plan_delivery(
        channel="telegram", template_key=TENANT_WEBSITE_CONTACT_TEMPLATE_KEY,
        template_version=1, render_context=new_payload.model_dump(mode="json"),
    )
    assert new_plan.render_context["submission_context"]["interests"]["items"][0]["active_seconds"] == 123
    assert new_plan.render_context != plan.render_context


@pytest.mark.asyncio
async def test_outbox_interest_snapshots_are_immutable(communications_session_factory):
    async with communications_session_factory() as session:
        event_args = dict(event_type="test.website.context", aggregate_type="lead", aggregate_id=1, idempotency_key="same-context-key")
        event = await IntegrationOutboxService.enqueue(session, **event_args, payload={"submission_context": context()})
        await session.commit()
        changed = context()
        changed["interests"]["items"][0]["active_seconds"] = 456
        with pytest.raises(OutboxEventConflictError):
            await IntegrationOutboxService.enqueue(session, **event_args, payload={"submission_context": changed})
        assert event.payload["submission_context"]["interests"]["items"][0]["active_seconds"] == 123


@pytest.mark.asyncio
async def test_contact_retry_revoke_keeps_first_metadata_event_and_internal_projections(communications_session_factory):
    async with communications_session_factory() as session:
        payload = request_payload("contact")
        response = await WebsiteLeadService.create_contact_lead(session, payload, tenant_scope=SCOPE, idempotency_key="interests-contact-retry-0001")
        no_interests = payload.model_copy(update={"submission_context": WebsiteSubmissionContext.model_validate(context(interests=None))})
        replay = await WebsiteLeadService.create_contact_lead(session, no_interests, tenant_scope=SCOPE, idempotency_key="interests-contact-retry-0001")
        assert replay == response
        lead = await session.get(Lead, response.lead_id)
        assert lead.intake_meta["submission_context"]["interests"]["items"][0]["active_seconds"] == 123
        assert "Daikin" not in lead.request_text
        events = list((await session.execute(select(IntegrationOutboxEvent))).scalars())
        assert len(events) == 1
        assert events[0].payload["submission_context"]["interests"]["consent"] is True
        inbox_item = RawLeadInboxService.project(lead, None, None)
        assert inbox_item.website_interests.items[0].product_id == 999
        assert inbox_item.intake_version == lead.version
        assert inbox_item.intake_state is None
        customer = Customer(tenant_id=1, name="Анна", phone="+375291112233")
        session.add(customer)
        await session.commit()
        result = await LeadService.qualify_lead(session, lead.id, LeadQualifyPayload(
            expected_version=inbox_item.intake_version, customer_id=customer.id,
        ), tenant_scope=SCOPE)
        order = await session.get(Order, result["order_id"])
        assert "Daikin" not in order.comment
        assert "Тихая работа" not in order.comment
        snapshot = order.technical_meta["incoming_intake"]
        assert IncomingOrderContext.model_validate(snapshot).original_text == lead.request_text
        assert website_interests_from_meta(order.technical_meta).items[0].title.startswith("Daikin")
        detail = await OrderProjectionService.get_order_detail_for_manager(session, order.id, tenant_scope=SCOPE)
        assert ManagerOrderDetailResponse.model_validate(detail).website_interests.items[0].product_id == 999
        assert LeadsInboxProjection.item(order).website_interests.items[0].product_id == 999
        foreign_scope = TenantScope(tenant_id=2, storefront_id=2)
        assert await OrderProjectionService.get_order_detail_for_manager(session, order.id, tenant_scope=foreign_scope) is None


@pytest.mark.asyncio
async def test_availability_repeat_does_not_overwrite_first_attention_or_duplicate_source():
    from types import SimpleNamespace

    ctx = WebsiteSubmissionContext.model_validate(context("product_availability"))
    order = Order(tenant_id=1, storefront_id=1, comment=append_submission_context("Original", ctx),
                  technical_meta={**submission_context_meta(ctx), "keep": "yes"})
    changed = context("product_availability")
    changed["interests"]["items"][0]["active_seconds"] = 1800
    await WebsiteLeadService._reuse_existing_order(
        SimpleNamespace(add=lambda *_: None), order, Product(id=7, title="P", slug="p", price=1),
        ProductAvailabilityLeadPayload(product_id=7, phone="+375291112233", submission_context=changed), datetime.now(),
    )
    assert order.comment.count("Страница:") == 1
    assert order.technical_meta["keep"] == "yes"
    assert order.technical_meta["submission_context"]["interests"]["items"][0]["active_seconds"] == 123


def test_telegram_top_three_are_escaped_bounded_and_optional_when_no_space():
    items = [{**interests()["items"][0], "title": f"<script>{i}</script>", "active_seconds": i * 60} for i in range(1, 9)]
    ctx = WebsiteSubmissionContext.model_validate(context(interests=interests(items=items)))
    payload = TenantWebsiteContactLeadCreatedPayloadV1(
        tenant_id=1, storefront_id=1, lead_id=1, status="new", name="Анна", phone="123", submission_context=ctx,
    )
    text = render_tenant_website_contact_v1(payload)
    assert "Интересы на сайте" in text
    assert "&lt;script&gt;8&lt;/script&gt;" in text
    assert "&lt;script&gt;6&lt;/script&gt;" in text
    assert "&lt;script&gt;5&lt;/script&gt;" not in text
    assert "<script>" not in text and len(text) <= 4096
    assert _finish_website_message(["a" * 4090], ctx) == "a" * 4090
    assert _finish_website_message(["a" * 4096], ctx) == "a" * 4096


def test_internal_projection_ignores_malformed_metadata_and_preserves_prior_timezone():
    from services.incoming_agreements import qualification_context

    for bad in [None, [], {"submission_context": {"interests": interests(consent=False)}}]:
        assert website_interests_from_meta(bad) is None
    lead = Lead(id=1, tenant_id=1, storefront_id=1, request_text="Original", intake_meta={
        **submission_context_meta(WebsiteSubmissionContext.model_validate(context())),
        "source_timezone": "UTC", "original_text": "Earlier original",
    })
    snapshot = qualification_context(lead)
    assert snapshot["source_timezone"] == "UTC" and snapshot["original_text"] == "Earlier original"
    snapshot["submission_context"]["interests"]["items"][0]["title"] = "Changed"
    assert lead.intake_meta["submission_context"]["interests"]["items"][0]["title"].startswith("Daikin")


def test_maximum_checkout_and_interest_values_fit_telegram_without_losing_base():
    payload = TenantWebsiteCheckoutCreatedPayloadV1(
        tenant_id=1, storefront_id=1, order_id=1, status="negotiation", total_amount="999999999999.99",
        customer={"name": "&" * 160, "phone": "&" * 80, "email": "&" * 254, "address": "&" * 500},
        comment="&" * 2000,
        product_lines=[{
            "product_id": i + 1, "title": "&" * 180, "quantity": 20, "unit_price": "999999999999.99",
            "installation_included": True, "installation_price": "999999999999.99",
        } for i in range(20)],
        service_lines=[{"title": "&" * 180, "quantity": 20, "unit_price": "999999999999.99"} for _ in range(20)],
        submission_context=context(
            "checkout", page_path="/" + "&" * 499, service_id="&" * 80, product_id=123456789,
            interests=interests(items=[{
                "kind": "product", "page_path": "/" + "&" * 499, "title": "&" * 160,
                "active_seconds": 1800, "topics": ["&" * 80] * 5, "product_id": 123456789,
            }] * 8),
        ),
    )
    rendered = render_tenant_website_checkout_v1(payload)
    assert len(rendered) <= 4096
    assert "Итого:" in rendered
    assert "Интересы на сайте" in rendered
