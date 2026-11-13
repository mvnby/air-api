from unittest.mock import AsyncMock

import pytest

from models import Order, OrderDocument
from services.order_email_template_service import OrderEmailTemplateService as Templates


@pytest.fixture
def compose_email(monkeypatch, tenant_scope):
    order = Order(id=742, tenant_id=1, storefront_id=1, title="Ремонт — внутренний заказ #742")
    document = OrderDocument(id=91, order_id=742, tenant_id=1, doc_type="offer", number="КП-91")
    order.documents = [document]
    monkeypatch.setattr("services.order_email_template_service.TenantEntityAccessService.get_order",
                        AsyncMock(return_value=order))
    monkeypatch.setattr(Templates, "_sender_name", AsyncMock(return_value="Компания"))
    monkeypatch.setattr(Templates, "_signature", AsyncMock(return_value="Менеджер\nКомпания"))

    async def compose(*, rows=None, template_key="auto", with_document=True, **kwargs):
        document.render_snapshot = {"table_rows": {"lines": rows}} if rows is not None else None
        return await Templates.compose(None, tenant_scope=tenant_scope, order_id=order.id,
                                       document_ids=[document.id] if with_document else [],
                                       template_key=template_key, **kwargs)

    return order, compose


@pytest.mark.parametrize("source", ["email", "site", "phone", "manager", "belzakupki"])
@pytest.mark.asyncio
async def test_legacy_documents_reference_customer_request_without_crm_id(compose_email, source):
    order, compose = compose_email
    order.lead_source = source
    result = await compose()

    assert result["subject"] == "Коммерческое предложение по вашей заявке"
    assert "Направляем коммерческое предложение по вашей заявке." in result["body_text"]
    assert "742" not in result["subject"] + result["body_text"]
    assert "ремонт" not in result["body_text"].lower()  # No guessing from the order title.


@pytest.mark.asyncio
async def test_tender_uses_selected_external_number_and_frozen_service_topic(compose_email):
    order, compose = compose_email
    order.lead_source = "belzakupki"
    order.technical_meta = {"belzakupki": {
        "match_id": 998, "external_tender_id": "old-mirror-10",
        "tender": {"id": 456, "external_id": "  3837629  ", "source": "goszakupki_by"},
        "source_references": {"icetrade_by:12": {"external_id": "old-mirror-12"}},
    }}
    result = await compose(rows=[{"line.kind": "service", "line.title": "Техническое обслуживание кондиционеров"}])

    assert result["subject"] == (
        "Коммерческое предложение на техническое обслуживание кондиционеров — по тендеру № 3837629")
    assert ("Направляем коммерческое предложение на техническое обслуживание кондиционеров "
            "по тендеру № 3837629.") in result["body_text"]
    assert "742" not in result["subject"] + result["body_text"]
    assert "old-mirror" not in result["subject"] + result["body_text"]


@pytest.mark.parametrize(("rows", "topic"), [
    ([{"line.kind": "service", "line.title": "Ремонт кондиционера"}], "ремонт кондиционеров"),
    ([{"line.kind": "service", "line.title": "Установка кондиционера"}], "монтаж кондиционеров"),
    ([{"line.kind": "product", "line.title": "Кондиционер TCL"}], "поставку кондиционеров"),
    ([{"line.kind": "product", "line.title": "Кондиционер TCL"},
      {"line.kind": "product", "line.title": "Вентилятор"}], "поставку товаров"),
    ([{"line.kind": "service", "line.title": "Ремонт оборудования\nКондиционер заказчика"}], "ремонт оборудования"),
    ([{"line.kind": "service", "line.title": "Ремонт осушителя без кондиционера"}], "ремонт оборудования"),
    ([{"line.kind": "product", "line.title": "Вентилятор без кондиционера"}], "поставку товаров"),
])
@pytest.mark.asyncio
async def test_service_and_supply_topics_describe_attached_contents(compose_email, rows, topic):
    _, compose = compose_email
    result = await compose(rows=rows)
    assert result["subject"] == f"Коммерческое предложение на {topic}"
    assert f"Направляем коммерческое предложение на {topic} по вашей заявке." in result["body_text"]


@pytest.mark.parametrize("template", ["auto", "offer", "invoice", "contract", "documents", "act", "custom"])
@pytest.mark.asyncio
async def test_every_document_template_and_custom_letter_omit_crm_reference(compose_email, template):
    _, compose = compose_email
    result = await compose(template_key=template, with_document=template != "custom")
    assert "742" not in result["subject"] + result["body_text"]
    assert "заказу" not in result["subject"] + result["body_text"]
    assert "вашей заявке" in result["subject"]


@pytest.mark.parametrize("template", ["custom", "request_requisites", "request_signer"])
@pytest.mark.asyncio
async def test_non_document_letters_can_reference_tender(compose_email, template):
    order, compose = compose_email
    order.technical_meta = {"belzakupki": {"tender": {"external_id": "2026-AB/15"}}}
    result = await compose(template_key=template, with_document=False)
    assert "тендеру № 2026-AB/15" in result["subject"]
    assert "742" not in result["subject"] + result["body_text"]


@pytest.mark.asyncio
async def test_registration_certificate_has_neutral_customer_context(compose_email, monkeypatch):
    from types import SimpleNamespace

    _, compose = compose_email
    monkeypatch.setattr("services.legal_entity_attachment_service.LegalEntityAttachmentService.resolve_for_mail",
                        AsyncMock(return_value=SimpleNamespace(legal_entity_id=1)))
    result = await compose(with_document=False, registration_certificate_id="certificate")
    assert result["subject"] == "Свидетельство о регистрации по вашей заявке"
    assert "Направляем свидетельство о регистрации по вашей заявке." in result["body_text"]


@pytest.mark.parametrize("metadata", [
    None, [], {"belzakupki": "invalid"}, {"belzakupki": {"tender": []}},
    {"belzakupki": {"tender": {"id": 123, "url": "https://example.test/123"}}},
    {"belzakupki": {"external_tender_id": "stale-mirror-123"}},
    {"belzakupki": {"tender": {"external_id": "  "}}},
    {"belzakupki": {"tender": {"external_id": True}}},
])
def test_missing_or_invalid_tender_number_never_falls_back_to_internal_identity(metadata):
    order = Order(id=742, tenant_id=1, storefront_id=1)
    order.technical_meta = metadata
    assert Templates._request_reference(order) == "по вашей заявке"
