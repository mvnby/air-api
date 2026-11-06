import json

import pytest
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from routers.api_leads import installation_estimate_form_payload
from schemas import PublicContactLeadPayload
from schemas_website_context import WebsiteSubmissionContext, append_submission_context
from services.communications.contracts import TenantWebsiteContactLeadCreatedPayloadV1
from services.communications.templates.website import render_tenant_website_contact_v1
from services.public_write_fingerprint_service import PublicWriteFingerprintService
from services.repair_diagnostic_service import RepairDiagnosticService


@pytest.mark.parametrize("path", [
    "https://example.com/a", "//example.com/a", "foo", "/foo?phone=123", "/foo#bar",
    "/foo\nbar", "/foo\x00bar", "/foo\\bar", "/%2fexample.com", "/foo%0dbar",
    "/foo%3Fphone=123", "/" + "a" * 500,
])
def test_context_rejects_non_pathname_and_unbounded_values(path):
    with pytest.raises(ValidationError):
        WebsiteSubmissionContext(page_path=path, form_id="contact")


@pytest.mark.parametrize("form_id", [
    "contact", "checkout", "installation_calculator", "installation_estimate",
    "repair_diagnostic", "product_availability", "multi_split",
])
def test_context_accepts_exact_seven_forms_and_retains_message(form_id):
    context = WebsiteSubmissionContext(page_path="/services/ремонт", form_id=form_id)
    text = append_submission_context("Original message", context)
    assert text.startswith("Original message\n")
    assert "Форма: " in text
    assert "Страница: /services/ремонт" in text


@pytest.mark.parametrize("changes", [
    {"form_id": "other"}, {"service_id": "s" * 81}, {"product_id": 0},
    {"service_id": "a\nb"}, {"visitor_id": "123"},
])
def test_context_limits_reference_fields_and_has_no_tracking(changes):
    with pytest.raises(ValidationError):
        WebsiteSubmissionContext.model_validate({"page_path": "/", "form_id": "contact", **changes})


def test_context_absence_preserves_legacy_fingerprint_and_context_is_significant():
    original = {"name": "Иван", "phone": "+375291112233", "email": None, "address": None, "message": "Hi"}
    payload = PublicContactLeadPayload.model_validate(original)
    old_hash = PublicWriteFingerprintService._hash({"payload": original})
    assert PublicWriteFingerprintService.for_payload(payload) == old_hash
    assert PublicWriteFingerprintService.for_payload(payload.model_dump(mode="json")) == old_hash
    payload.submission_context = WebsiteSubmissionContext(page_path="/services", form_id="contact")
    assert PublicWriteFingerprintService.for_payload(payload) != old_hash


@pytest.mark.asyncio
async def test_installation_multipart_context_json_parses_without_losing_description():
    context = {"page_path": "/services/installation", "form_id": "installation_estimate", "service_id": "installation"}
    payload = await installation_estimate_form_payload(
        name="Иван", phone="+375291112233", consent=True, description="Original description",
        submission_context=json.dumps(context),
    )
    assert payload.description == "Original description"
    assert payload.submission_context.model_dump(exclude_none=True) == context
    for raw in ["{broken", '{"page_path":"//evil","form_id":"contact"}']:
        with pytest.raises(RequestValidationError):
            await installation_estimate_form_payload(name="Иван", phone="+375291112233", consent=True, submission_context=raw)


def test_repair_payload_roundtrip_keeps_context_and_client_comment():
    payload = RepairDiagnosticService.parse_payload(json.dumps({
        "symptom": "water_leak", "contact": {"name": "Иван", "phone": "+375291112233"},
        "client_comment": "Original complaint",
        "submission_context": {"page_path": "/repair", "form_id": "repair_diagnostic"},
    }))
    assert payload.submission_context.page_path == "/repair"
    assert "Original complaint" in RepairDiagnosticService._build_order_comment(payload, {})


def test_context_telegram_rendering_escapes_and_bounds_untrusted_page():
    payload = TenantWebsiteContactLeadCreatedPayloadV1(
        tenant_id=1, storefront_id=1, lead_id=1, status="new", name="Иван", phone="123",
        message="Original message", submission_context={
            "page_path": "/" + "<>&\"'" * 99, "form_id": "contact", "service_id": "<script>",
        },
    )
    text = render_tenant_website_contact_v1(payload)
    assert "Original message" in text
    assert "Форма: Обратная связь" in text
    assert "&lt;script&gt;" in text
    assert "<script>" not in text
    page_line = next(line for line in text.splitlines() if line.startswith("Страница:"))
    assert len(page_line) <= 410
    assert page_line.endswith("...")
    assert len(text) <= 4096


@pytest.mark.asyncio
async def test_availability_repeat_preserves_existing_comment_and_context_once():
    from datetime import datetime
    from types import SimpleNamespace

    from models import Order, Product
    from schemas import ProductAvailabilityLeadPayload
    from services.website_lead_service import WebsiteLeadService

    order = Order(tenant_id=1, storefront_id=1, comment="Original manager note", technical_meta={"keep": "value"})
    product = Product(id=7, title="Product", slug="product", price=100)
    payload = ProductAvailabilityLeadPayload(
        product_id=7, phone="+375291112233", submission_context={
            "page_path": "/product/product", "form_id": "product_availability", "product_id": 7,
        },
    )
    for _ in range(2):
        await WebsiteLeadService._reuse_existing_order(
            SimpleNamespace(add=lambda *_: None), order, product, payload, datetime.now(),
        )
    assert order.comment.startswith("Original manager note\n")
    assert order.comment.count("Страница: /product/product") == 1
    assert order.technical_meta["keep"] == "value"
    assert order.technical_meta["submission_context"]["product_id"] == 7


def test_maximum_checkout_context_stays_within_telegram_limit():
    from services.communications.contracts import TenantWebsiteCheckoutCreatedPayloadV1
    from services.communications.templates.website import render_tenant_website_checkout_v1

    payload = TenantWebsiteCheckoutCreatedPayloadV1(
        tenant_id=1, storefront_id=1, order_id=1, status="negotiation", total_amount="999999999999.99",
        customer={"name": "&" * 160, "phone": "&" * 80, "email": "&" * 254, "address": "&" * 500},
        comment="&" * 2000,
        product_lines=[{
            "product_id": i + 1, "title": "&" * 180, "quantity": 20,
            "unit_price": "999999999999.99", "installation_included": True,
            "installation_price": "999999999999.99",
        } for i in range(20)],
        service_lines=[{"title": "&" * 180, "quantity": 20, "unit_price": "999999999999.99"} for _ in range(20)],
        submission_context={"page_path": "/" + "&" * 499, "form_id": "checkout", "service_id": "&" * 80, "product_id": 123456789},
    )
    assert len(render_tenant_website_checkout_v1(payload)) <= 4096
