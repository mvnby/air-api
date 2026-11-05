import asyncio
from datetime import datetime
from io import BytesIO
from unittest.mock import Mock

import pytest
from docx import Document
from sqlalchemy.ext.asyncio import async_sessionmaker

from models import Customer, CustomerType, DocumentLegalEntity, DocumentNumberPolicy, Order, OrderDocument, Storefront, Tenant
from modules.documents.application import DocumentContextSelection, ManagedDocumentGenerationError, ManagedDocumentService
from modules.documents.application.artifact_helpers import stored_artifact
from modules.documents.domain import DocumentNumberScope
from modules.documents.domain.numbering import google_number_history_type
from modules.documents.infrastructure import DocumentNumberingRepository
from services.document_service import DocumentService
from tests.integration import test_managed_document_lifecycle as lifecycle
from tests.integration.test_managed_document_lifecycle import FailingPdfConverter, FakePdfConverter, _seed


NATIVE = "b2c_supply_installation_act"
GOOGLE = "service_act"
ISSUED = datetime(2026, 11, 6)


@pytest.mark.asyncio
@pytest.mark.parametrize(("custom_series", "native_number", "google_number", "following"), [
    (None, "ЗА-2026-005", "ЗА-2026-006", "ЗА-2026-007"),
    ("СВОЯ-", "СВОЯ-2026-001", "ЗА-2026-005", "ЗА-2026-006"),
])
async def test_native_and_google_print_the_next_consumer_act_and_retry_keeps_it(
    db, tmp_path, monkeypatch, custom_series, native_number, google_number, following,
):
    template = Document(BytesIO(lifecycle._template_docx()))
    template.paragraphs[0].text = "ЗАКАЗ-АКТ № {{ document.official_full_number }}"
    source = BytesIO()
    template.save(source)
    monkeypatch.setattr(lifecycle, "_template_docx", source.getvalue)
    scope, order, issuer, templates, artifacts = await _seed(db, tmp_path, document_type=NATIVE)
    buyer = await db.get(Customer, order.customer_id)
    buyer.type = CustomerType.individual
    issuer.requisites = {"offer_url": "https://example.test/offer", "offer_version": "1", "offer_published_on": "01.06.2026"}
    if custom_series:
        db.add(DocumentNumberPolicy(tenant_id=1, legal_entity_id=issuer.id, document_type=NATIVE, series=custom_series))
        db.add(OrderDocument(order_id=order.id, doc_type=GOOGLE, number="СВОЯ-2026-070"))
    # Legacy uploads can be recorded out of order. Other years, malformed entries
    # and another tenant's numbers do not belong to this annual sequence.
    db.add_all([OrderDocument(order_id=order.id, doc_type=GOOGLE, number=n) for n in
                ("ЗА-2026-004", "ЗА-2026-001", "ЗА-2026-test", "ЗА-2025-400")])
    tenant = Tenant(slug="other-consumer-company", display_name="Other")
    db.add(tenant)
    await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug="other", display_name="Other", is_default=True)
    db.add(storefront)
    await db.flush()
    other_order = Order(tenant_id=tenant.id, storefront_id=storefront.id)
    db.add(other_order)
    await db.flush()
    db.add(OrderDocument(order_id=other_order.id, doc_type=GOOGLE, number="ЗА-2026-900"))
    await db.commit()

    draft = await ManagedDocumentService.create_draft(db, tenant_scope=scope, template_storage=templates,
        selection=DocumentContextSelection(order_id=order.id, legal_entity_id=issuer.id, document_type=NATIVE, issue_date=ISSUED.date()))
    assert draft.official_number is None
    issue = dict(tenant_scope=scope, document_id=draft.id, template_storage=templates, artifact_storage=artifacts)
    with pytest.raises(ManagedDocumentGenerationError):
        await ManagedDocumentService.issue(db, **issue, pdf_converter=FailingPdfConverter())

    google = Mock()
    google.copy_template.return_value = {"file_id": "example", "edit_url": "https://example.test/docs/example"}
    monkeypatch.setattr("services.document_service.get_google_service", lambda: google)
    monkeypatch.setattr("googleapiclient.discovery.build", Mock())
    issued_google = await DocumentService.create_or_get_document(
        db, order.id, GOOGLE, template_id="test-template", contract_date=ISSUED)
    assert issued_google.number == google_number
    substitutions = google.replace_placeholders.call_args.args[1]
    assert substitutions["{{doc_number}}"] == substitutions["{{number}}"] == issued_google.number

    issued_native = await ManagedDocumentService.issue(db, **issue, pdf_converter=FakePdfConverter())
    docx_artifact = next(item for item in issued_native.artifacts if item.kind == "rendered_docx")
    content = await artifacts.read(stored_artifact(docx_artifact))
    assert Document(BytesIO(content)).paragraphs[0].text == f"ЗАКАЗ-АКТ № {native_number}"
    assert await DocumentService._get_next_number(db, GOOGLE, ISSUED, tenant_id=1) == following
    assert await DocumentService._get_next_number(db, GOOGLE, datetime(2027, 1, 1), tenant_id=1) == "ЗА-2027-001"


@pytest.mark.asyncio
async def test_google_and_native_allocate_concurrently_under_the_same_annual_lock(db_engine):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions.begin() as db:
        issuer = DocumentLegalEntity(tenant_id=1, slug="consumer-numbers", display_name="Issuer", is_default=True)
        order = Order(tenant_id=1, storefront_id=1)
        db.add_all([issuer, order])
        await db.flush()
        db.add(OrderDocument(order_id=order.id, doc_type=GOOGLE, number="ЗА-2026-004"))

    async def allocate(i):
        async with sessions.begin() as db:
            if i % 2:
                reservation = await DocumentNumberingRepository.reserve(
                    db, scope=DocumentNumberScope(1, issuer.id, NATIVE, "ЗА-", "2026"),
                    idempotency_key=f"consumer-act-{i}", legacy_document_type=google_number_history_type(NATIVE, "ЗА-"),
                    number_text_formatter=lambda n: f"ЗА-2026-{n:03d}",
                )
                return reservation.number_text
            number = await DocumentService._get_next_number(db, GOOGLE, ISSUED, tenant_id=1)
            db.add(OrderDocument(order_id=order.id, doc_type=GOOGLE, number=number))
            return number

    numbers = await asyncio.gather(*(allocate(i) for i in range(8)))
    assert sorted(numbers) == [f"ЗА-2026-{n:03d}" for n in range(5, 13)]
