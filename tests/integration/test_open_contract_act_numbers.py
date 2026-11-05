from datetime import date, datetime
from io import BytesIO

import pytest
from docx import Document
from sqlalchemy import func, select

from models import CustomerContract, DocumentNumberReservation, OrderDocument
from modules.documents.api.managed_documents_artifacts import _document_item_from_parts
from modules.documents.application import DocumentContextSelection, ManagedDocumentService
from modules.documents.application.contract_act_numbers import ContractActNumberConfirmationRequired
from modules.documents.application.draft_preview import ManagedDocumentDraftPreviewService
from modules.documents.application.errors import ManagedDocumentGenerationError
from modules.documents.domain import ActTerms
from services.customer_reconciliation_projection import document_identity
from services.document_service import DocumentService
from tests.integration.test_managed_document_lifecycle import (
    FailingPdfConverter, FakePdfConverter, _seed, _template_docx,
)


class CapturePdfSource(FakePdfConverter):
    def convert_docx(self, content: bytes, *, filename: str = "document.docx") -> bytes:
        self.source = content
        return super().convert_docx(content, filename=filename)


def _act_template():
    doc = Document(BytesIO(_template_docx()))
    doc.paragraphs[0].text = "АКТ №{{ document.official_full_number }}"
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("edited", [False, True])
async def test_open_contract_issue_continues_verified_printed_number(db, tmp_path, monkeypatch, edited):
    from tests.integration import test_managed_document_lifecycle as lifecycle
    from modules.documents.application.managed_document_external_edits import ManagedDocumentExternalEditSessionService
    from tests.integration.test_managed_document_google_editing import FakeGoogleEditor

    monkeypatch.setattr(lifecycle, "_template_docx", _act_template)
    scope, order, issuer, templates, artifacts = await _seed(db, tmp_path, document_type="act")
    contract = CustomerContract(
        customer_id=order.customer_id, number="ОД-2026-001", document_role_type="executor_customer",
        valid_from=datetime(2026, 4, 25), valid_until=datetime(2027, 4, 25),
    )
    db.add(contract)
    await db.flush()
    # Only one row is present, but the paper original is act 21. Neither 1 nor
    # the legacy CRM number 086 is a valid floor for the new printed sequence.
    previous = OrderDocument(
        order_id=order.id, base_customer_contract_id=contract.id, doc_type="act",
        number="А-2026-086", google_file_id="historical-act",
        date=datetime(2026, 11, 4),
    )
    db.add(previous)
    await db.commit()
    selection = DocumentContextSelection(
        order_id=order.id, legal_entity_id=issuer.id, document_type="act",
        issue_date=date(2026, 11, 5), base_customer_contract_id=contract.id,
        act_terms=ActTerms(claims_status="none"),
    )
    draft = await ManagedDocumentService.create_draft(
        db, tenant_scope=scope, selection=selection, template_storage=templates,
    )
    capture = CapturePdfSource()
    issue = dict(tenant_scope=scope, document_id=draft.id, template_storage=templates,
                 artifact_storage=artifacts, pdf_converter=capture)
    await ManagedDocumentDraftPreviewService.render_pdf(db, **issue)
    assert "НОМЕР НЕ ПРИСВОЕН" in Document(BytesIO(capture.source)).paragraphs[0].text
    assert draft.contract_act_number is None and contract.last_act_number is None

    if edited:
        provider = FakeGoogleEditor()
        editor = await ManagedDocumentExternalEditSessionService.ensure_session(
            db, tenant_scope=scope, document_id=draft.id, template_storage=templates,
            artifact_storage=artifacts, provider=provider,
        )
        provider.add_manual_paragraph("Исправлено менеджером")
        changed = await ManagedDocumentExternalEditSessionService.get_session(
            db, tenant_scope=scope, document_id=draft.id, provider=provider,
        )
        synced = await ManagedDocumentExternalEditSessionService.sync(
            db, tenant_scope=scope, document_id=draft.id,
            expected_base_checksum_sha256=editor.base_checksum_sha256,
            expected_remote_revision=changed.remote_revision, idempotency_key="open-act-edit",
            artifact_storage=artifacts, provider=provider,
        )
        issue["verified_remote_revision"] = synced.remote_revision

    for confirmation in ({}, {"expected_previous_act_id": previous.id + 1, "confirmed_previous_act_number": 21}):
        with pytest.raises(ContractActNumberConfirmationRequired) as error:
            await ManagedDocumentService.issue(db, **issue, **confirmation)
        assert error.value.previous_act == {
            "id": previous.id, "order_id": order.id, "number": "А-2026-086",
            "url": "https://drive.google.com/open?id=historical-act",
        }
        assert await db.scalar(select(func.count()).select_from(DocumentNumberReservation)) == 0

    with pytest.raises(ManagedDocumentGenerationError):
        await ManagedDocumentService.issue(
            db, **{**issue, "pdf_converter": FailingPdfConverter()},
            expected_previous_act_id=previous.id, confirmed_previous_act_number=21,
            confirmed_previous_act_by="manager",
        )
    assert draft.contract_act_number == 22
    assert draft.scope_meta["contract_act_number_confirmation"]["previous_act_id"] == previous.id
    assert draft.scope_meta["contract_act_number_confirmation"]["confirmed_by"] == "manager"
    assert draft.official_number == "087"
    issued = await ManagedDocumentService.issue(db, **issue)
    item = _document_item_from_parts(issued.document, issued.artifacts)
    assert item.contract_act_number == 22 and item.official_full_number == "А-2026-087"
    assert document_identity(issued.document)["number"] == "22"
    rendered = next(row for row in issued.artifacts if row.kind == "rendered_docx")
    assert await artifacts.read(ManagedDocumentService.stored_artifact(rendered)) == capture.source
    paragraphs = [p.text for p in Document(BytesIO(capture.source)).paragraphs]
    assert paragraphs[0] == "АКТ №22"
    if edited:
        assert "Исправлено менеджером" in paragraphs
    assert (await ManagedDocumentService.issue(db, **issue)).document.contract_act_number == 22
    assert await DocumentService._get_next_number(db, "act", datetime(2026, 11, 5), tenant_id=1) == "А-2026-088"

    replacement = await ManagedDocumentService.create_draft(
        db, tenant_scope=scope, selection=selection, replaces_document_id=draft.id,
        template_storage=templates,
    )
    second = await ManagedDocumentService.issue(
        db, tenant_scope=scope, document_id=replacement.id, template_storage=templates,
        artifact_storage=artifacts, pdf_converter=capture,
    )
    assert second.document.contract_act_number == 23
    assert Document(BytesIO(capture.source)).paragraphs[0].text == "АКТ №23"
    assert issued.document.contract_act_number == 22


@pytest.mark.asyncio
async def test_google_and_native_open_act_allocations_have_one_transactional_sequence(db_engine, monkeypatch):
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from models import Customer, DocumentLegalEntity, Order
    from modules.documents.application.contract_act_numbers import allocate_contract_act_number
    from modules.documents.domain import DocumentNumberScope
    from modules.documents.infrastructure import DocumentNumberingRepository
    from services import customer_reconciliation_legacy_review as legacy_review

    # Whichever backend reaches the series first sees a verified baseline of 21.
    monkeypatch.setattr(legacy_review, "_text_from_google", lambda _: "АКТ №21\nДоговор №ОД-1 от 25.04.2026")
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions.begin() as db:
        customer = Customer(tenant_id=1, name="Заказчик", phone="1")
        issuer = DocumentLegalEntity(tenant_id=1, slug="open-act-concurrency", display_name="ИП", is_default=True)
        db.add_all([customer, issuer])
        await db.flush()
        contract = CustomerContract(customer_id=customer.id, number="ОД-1", valid_until=datetime(2027, 4, 25))
        db.add(contract)
        await db.flush()
        order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, customer_contract_id=contract.id)
        db.add(order)
        await db.flush()
        # The oldest rows may relate solely through order.customer_contract_id.
        last = OrderDocument(order_id=order.id, number="А-2026-086", doc_type="act", google_file_id="history")
        db.add(last)
        await db.flush()

    async def issue_one(index):
        async with sessions.begin() as db:
            pending = OrderDocument(order_id=order.id, doc_type="act", base_customer_contract_id=contract.id)
            printed = await allocate_contract_act_number(
                db, contract_id=contract.id, storefront_id=1,
                issuing_document=pending if index % 2 else None,
                expected_previous_act_id=last.id, confirmed_previous_act_number=21,
            )
            if index % 2:
                crm = (await DocumentNumberingRepository.reserve(
                    db, scope=DocumentNumberScope(1, issuer.id, "act", "А-", "2026"),
                    idempotency_key=f"issue:native-act-{index}", legacy_document_type="act",
                    number_text_formatter=lambda value: f"А-2026-{value:03d}",
                )).number_text
                pending.internal_reference = pending.number = f"native-act-{index}"
            else:
                crm = await DocumentService._get_next_number(db, "act", datetime(2026, 11, 5), tenant_id=1)
                pending.number = crm
            pending.contract_act_number = printed
            db.add(pending)
        return crm, printed

    results = await asyncio.gather(*(issue_one(i) for i in range(8)))
    assert sorted(number for _, number in results) == list(range(22, 30))
    assert sorted(crm for crm, _ in results) == [f"А-2026-{n:03d}" for n in range(87, 95)]


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_native", [False, True])
async def test_unverifiable_history_never_silently_seeds_crm(db, tmp_path, monkeypatch, previous_native):
    from modules.documents.application.contract_act_numbers import allocate_contract_act_number
    from services import customer_reconciliation_legacy_review as legacy_review

    def unreadable(_):
        raise OSError("original no longer accessible")

    monkeypatch.setattr(legacy_review, "_text_from_google", unreadable)
    scope, order, issuer, _templates, _artifacts = await _seed(db, tmp_path, document_type="act")
    contract = CustomerContract(customer_id=order.customer_id, number="ОД-2", valid_until=datetime(2027, 4, 25))
    db.add(contract)
    await db.flush()
    previous = OrderDocument(
        order_id=order.id, base_customer_contract_id=contract.id, doc_type="act",
        number="А-2026-021", google_file_id=None if previous_native else "unreadable",
        status="issued" if previous_native else None,
        internal_reference="old-native-act" if previous_native else None,
        tenant_id=scope.tenant_id, legal_entity_id=issuer.id if previous_native else None,
    )
    db.add(previous)
    await db.commit()
    pending = OrderDocument(order_id=order.id, base_customer_contract_id=contract.id, doc_type="act")
    native = dict(contract_id=contract.id, issuing_document=pending, storefront_id=scope.storefront_id)
    with pytest.raises(ContractActNumberConfirmationRequired) as required:
        await allocate_contract_act_number(db, **native)
    assert required.value.previous_act["id"] == previous.id
    if previous_native:
        assert required.value.previous_act["url"] == f"/manager/orders/kanban?orderId={order.id}"
        # The original contained only the annual office identifier; first ordinal is 1.
        assert await allocate_contract_act_number(
            db, **native, expected_previous_act_id=previous.id, confirmed_previous_act_number=0,
        ) == 1
    else:
        # Legacy Google can continue even with a missing earlier original.
        assert await allocate_contract_act_number(db, contract_id=contract.id) == 2
        legacy = OrderDocument(order_id=order.id, base_customer_contract_id=contract.id,
                               doc_type="act", number="А-2026-022", contract_act_number=2)
        db.add(legacy)
        await db.commit()
        for wrong in ({}, {"expected_previous_act_id": previous.id, "confirmed_previous_act_number": 21},
                      {"expected_previous_act_id": legacy.id, "confirmed_previous_act_number": 1}):
            with pytest.raises(ContractActNumberConfirmationRequired) as required:
                await allocate_contract_act_number(db, **native, **wrong)
            assert required.value.previous_act["id"] == legacy.id
        assert await allocate_contract_act_number(
            db, **native, expected_previous_act_id=legacy.id, confirmed_previous_act_number=21,
        ) == 22
        assert contract.act_number_confirmation_pending is False
