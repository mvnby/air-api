from dataclasses import replace
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from docx import Document
from fastapi import HTTPException
from sqlalchemy import func, select

from api_contracts.bot_order_desk import BotOrderCommand, BotOrderPrepareDocument
from core.command_actor import CommandActor
from models import (
    Customer,
    DocumentArtifact,
    DocumentLegalEntity,
    DocumentNumberReservation,
    Order,
    OrderDocument,
    OrderProductLink,
    OrderProposal,
    OrderServiceLink,
    Product,
    PublicWriteIdempotency,
    StaffUser,
    Storefront,
    Tenant,
)
from models.tenancy import TenantScope
from modules.documents.application.errors import ManagedDocumentNotFoundError
from modules.documents.infrastructure.renderers.pdf import UnavailablePdfConverter
from services import bot_order_documents as documents
from services.bot_order_desk import change_order, get_order_desk
from services.bot_workspace_service import Workspace
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.integration.test_managed_document_lifecycle import _seed


class CapturingPdfConverter:
    def __init__(self):
        self.rendered_rows = []

    def convert_docx(self, content: bytes, *, filename: str) -> bytes:
        assert filename.startswith("draft-") and filename.endswith(".docx")
        rendered = Document(BytesIO(content))
        self.rendered_rows = [[cell.text for cell in row.cells] for row in rendered.tables[0].rows[1:]]
        return b"%PDF-1.4\norder-desk-preview\n%%EOF"


async def _setup(db, tmp_path, monkeypatch, document_type="offer"):
    scope, order, issuer, _, _ = await _seed(db, tmp_path, document_type=document_type)
    manager = StaffUser(username="telegram-manager", display_name="Менеджер Telegram", primary_role="manager")
    db.add(manager)
    await db.commit()
    private = LocalPrivateAttachmentStorage(tmp_path / "private-documents")
    monkeypatch.setattr(documents, "get_private_attachment_storage", lambda: private)
    return Workspace(CommandActor(manager.id, manager.username, scope, "telegram"), "main"), order, issuer, private


def _command(desk, issuer_id, doc_type, *, proposal_id):
    return BotOrderCommand(
        expected_revision=desk.revision,
        idempotency_key=uuid4(),
        change=BotOrderPrepareDocument(kind="prepare_document", document_type=doc_type,
                                       legal_entity_id=issuer_id, proposal_id=proposal_id),
    )


@pytest.mark.parametrize("document_type", ["offer", "invoice"])
async def test_order_draft_and_pdf_use_only_requested_proposal_at_saved_prices(db, tmp_path, monkeypatch, document_type):
    ws, order, issuer, _ = await _setup(db, tmp_path, monkeypatch, document_type)
    product = await db.scalar(select(Product).where(Product.slug == "managed-document-lifecycle-conditioner"))
    selected = await db.scalar(select(OrderProposal).where(OrderProposal.order_id == order.id, OrderProposal.is_selected.is_(True)))
    alternative = OrderProposal(order_id=order.id, name="Альтернатива с монтажом", is_selected=False)
    db.add(alternative)
    await db.flush()
    alternative_line = OrderProductLink(order_id=order.id, proposal_id=alternative.id, product_id=product.id,
                                        quantity=2, price=1234, cost=800, title_snapshot="Согласованный кондиционер")
    db.add_all([
        alternative_line,
        OrderServiceLink(order_id=order.id, proposal_id=alternative.id, title="Согласованный монтаж",
                         quantity=3, price=Decimal("210.50")),
        OrderServiceLink(order_id=order.id, proposal_id=selected.id, title="Монтаж другого варианта",
                         quantity=1, price=Decimal("900.00")),
    ])
    await db.commit()

    desk = await get_order_desk(db, ws, order.id)
    assert [(option.id, option.types) for option in desk.document_issuers] == [(issuer.id, [document_type])]
    request = _command(desk, issuer.id, document_type, proposal_id=alternative.id)
    response = await change_order(db, ws, order.id, request)
    assert len(response.documents) == 1
    item = response.documents[0]
    assert item.status == "Черновик" and item.can_preview and item.url is None
    assert item.proposal_id == alternative.id
    assert next(proposal.id for proposal in response.proposals if proposal.is_selected) == selected.id

    draft = await db.get(OrderDocument, item.id)
    assert (draft.tenant_id, draft.legal_entity_id, draft.order_id, draft.proposal_id) == (1, issuer.id, order.id, alternative.id)
    assert draft.doc_type == document_type and draft.status == "draft"
    assert draft.official_number is None and draft.issued_at is None
    if document_type == "invoice":
        assert draft.business_role == "payment_request"
    snapshot = draft.render_snapshot
    assert snapshot["values"]["totals.amount"] == "3099.50"
    assert [(row["line.title"], row["line.quantity"], row["line.amount"]) for row in snapshot["table_rows"]["lines"]] == [
        ("Согласованный кондиционер", "2", "2468.00"),
        ("Согласованный монтаж", "3", "631.50"),
    ]
    # Changes to both storefront and order prices affect live data, never the frozen draft or its retry.
    product.price = 1777
    alternative_line.price = 1299
    await db.commit()
    replay = await change_order(db, ws, order.id, request)
    assert [saved.id for saved in replay.documents] == [item.id]
    assert await db.scalar(select(func.count(OrderDocument.id)).where(OrderDocument.order_id == order.id)) == 1
    assert await db.scalar(select(func.count(PublicWriteIdempotency.id))) == 1

    converter = CapturingPdfConverter()
    monkeypatch.setattr(documents, "configured_pdf_converter", lambda: converter)
    pdf = await documents.draft_pdf(db, ws.scope, order.id, item.id)
    assert pdf.startswith(b"%PDF-1.4")
    assert [row[1:] for row in converter.rendered_rows] == [
        ["Согласованный кондиционер", "2", "2468.00"],
        ["Согласованный монтаж", "3", "631.50"],
    ]
    await db.refresh(draft)
    assert draft.render_snapshot == snapshot and draft.status == "draft" and draft.official_number is None
    assert draft.issued_at is None and draft.sent_at is None and draft.google_file_id is None
    assert await db.scalar(select(func.count(DocumentNumberReservation.id))) == 0
    assert await db.scalar(select(func.count(DocumentArtifact.id))) == 0


async def test_legacy_draft_materializes_only_ungrouped_lines_and_preserves_archived_proposal(db, tmp_path, monkeypatch):
    ws, order, issuer, _ = await _setup(db, tmp_path, monkeypatch)
    archived = await db.scalar(select(OrderProposal).where(OrderProposal.order_id == order.id))
    archived.is_archived = True
    archived.is_selected = False
    historical_line = await db.scalar(select(OrderProductLink).where(OrderProductLink.proposal_id == archived.id))
    historical_line.title_snapshot = "Архивный кондиционер"
    ungrouped = OrderProductLink(order_id=order.id, product_id=historical_line.product_id, quantity=1,
                                 price=923, title_snapshot="Сохранённый кондиционер")
    install = OrderServiceLink(order_id=order.id, title="Сохранённый монтаж", price=Decimal("50.00"))
    db.add_all([ungrouped, install])
    await db.commit()

    desk = await get_order_desk(db, ws, order.id)
    legacy = next(proposal for proposal in desk.proposals if proposal.is_selected)
    assert legacy.id is None
    assert [line.title for line in legacy.product_lines] == ["Сохранённый кондиционер"]
    assert await db.scalar(select(func.count(OrderProposal.id)).where(OrderProposal.order_id == order.id)) == 1
    assert ungrouped.proposal_id is None and install.proposal_id is None

    request = _command(desk, issuer.id, "offer", proposal_id=None)
    result = await change_order(db, ws, order.id, request)
    draft = await db.get(OrderDocument, result.documents[0].id)
    assert draft.proposal_id != archived.id
    assert draft.proposal_id == next(proposal.id for proposal in result.proposals if proposal.is_selected)
    assert draft.render_snapshot["values"]["totals.amount"] == "973.00"
    assert [row["line.title"] for row in draft.render_snapshot["table_rows"]["lines"]] == [
        "Сохранённый кондиционер", "Сохранённый монтаж",
    ]
    await db.refresh(archived)
    await db.refresh(historical_line)
    assert archived.is_archived and historical_line.proposal_id == archived.id
    assert historical_line.title_snapshot == "Архивный кондиционер" and historical_line.price == 1500


async def test_order_document_availability_is_tenant_issuer_and_customer_scoped(db, tmp_path, monkeypatch):
    ws, order, issuer, _ = await _setup(db, tmp_path, monkeypatch)
    db.add(Tenant(id=2, slug="other-document-company", display_name="Remote company"))
    await db.flush()
    db.add_all([
        Storefront(id=2, tenant_id=2, slug="other", display_name="Foreign storefront"),
        Storefront(id=3, tenant_id=1, slug="secondary", display_name="Secondary storefront"),
    ])
    foreign_issuer = DocumentLegalEntity(tenant_id=2, slug="other-as-issuer", display_name="Foreign issuer",
                                        legal_name="Foreign issuer", unp="200000001")
    same_tenant_issuer = DocumentLegalEntity(tenant_id=1, slug="issuer-without-template", display_name="No template",
                                            legal_name="No template", unp="100000001")
    db.add_all([foreign_issuer, same_tenant_issuer])
    await db.commit()

    desk = await get_order_desk(db, ws, order.id)
    assert [item.id for item in desk.document_issuers] == [issuer.id]
    proposal_id = desk.proposals[0].id
    for unavailable_issuer in (foreign_issuer, same_tenant_issuer):
        with pytest.raises(HTTPException) as error:
            await change_order(db, ws, order.id, _command(desk, unavailable_issuer.id, "offer", proposal_id=proposal_id))
        assert error.value.status_code == 409
    assert await db.scalar(select(func.count(OrderDocument.id))) == 0

    customer = await db.get(Customer, order.customer_id)
    customer.is_archived = True
    await db.commit()
    assert not (await get_order_desk(db, ws, order.id)).document_issuers
    request = _command(desk, issuer.id, "offer", proposal_id=proposal_id)
    with pytest.raises(HTTPException) as error:
        # Model a customer archive committed after the caller took its last projection.
        await documents.prepare_document(db, ws.scope, desk, request.change)
    assert error.value.status_code == 409 and "действующий клиент" in error.value.detail
    assert await db.scalar(select(func.count(OrderDocument.id))) == 0

    customer.is_archived = False
    await db.commit()
    document_id = (await change_order(db, ws, order.id, request)).documents[0].id
    demo = replace(ws, actor=replace(ws.actor, tenant_scope=replace(ws.scope, demo_read_only=True)))
    demo_desk = await get_order_desk(db, demo, order.id)
    assert not demo_desk.document_issuers and not demo_desk.documents[0].can_preview
    with pytest.raises(HTTPException) as error:
        await documents.draft_pdf(db, demo.scope, order.id, document_id)
    assert error.value.status_code == 403

    for unavailable_scope in (TenantScope(2, 2), TenantScope(1, 3)):
        with pytest.raises(ManagedDocumentNotFoundError):
            await documents.draft_pdf(db, unavailable_scope, order.id, document_id)
    with pytest.raises(HTTPException) as error:
        await documents.draft_pdf(db, ws.scope, order.id + 1, document_id)
    assert error.value.status_code == 404

    draft = await db.get(OrderDocument, document_id)
    draft.status = "issued"
    await db.commit()
    assert not (await get_order_desk(db, ws, order.id)).documents[0].can_preview
    with pytest.raises(HTTPException) as error:
        await documents.draft_pdf(db, ws.scope, order.id, document_id)
    assert error.value.status_code == 409


async def test_order_pdf_and_template_failures_preserve_drafts_and_receipts(db, tmp_path, monkeypatch):
    ws, order, issuer, private = await _setup(db, tmp_path, monkeypatch, "invoice")
    desk = await get_order_desk(db, ws, order.id)
    command = _command(desk, issuer.id, "invoice", proposal_id=desk.proposals[0].id)
    original_read = private.read

    async def missing_source(_key):
        raise FileNotFoundError("private-provider-detail")

    monkeypatch.setattr(private, "read", missing_source)
    with pytest.raises(HTTPException) as error:
        await change_order(db, ws, order.id, command)
    assert error.value.status_code == 503 and "private-provider-detail" not in error.value.detail
    assert await db.scalar(select(func.count(OrderDocument.id))) == 0
    assert await db.scalar(select(func.count(PublicWriteIdempotency.id))) == 0

    monkeypatch.setattr(private, "read", original_read)
    result = await change_order(db, ws, order.id, command)
    document_id = result.documents[0].id
    monkeypatch.setattr(documents, "configured_pdf_converter", lambda: UnavailablePdfConverter("private-converter-detail"))
    with pytest.raises(HTTPException) as error:
        await documents.draft_pdf(db, ws.scope, order.id, document_id)
    assert error.value.status_code == 503 and "private-converter-detail" not in error.value.detail

    monkeypatch.setattr(private, "read", missing_source)
    with pytest.raises(HTTPException) as error:
        await documents.draft_pdf(db, ws.scope, order.id, document_id)
    assert error.value.status_code == 503 and "private-provider-detail" not in error.value.detail
    draft = await db.get(OrderDocument, document_id)
    assert draft.status == "draft" and draft.official_number is None
    assert await db.scalar(select(func.count(DocumentNumberReservation.id))) == 0
    assert await db.scalar(select(func.count(DocumentArtifact.id))) == 0
    assert await db.scalar(select(func.count(PublicWriteIdempotency.id))) == 1
