from dataclasses import replace
from io import BytesIO
from uuid import uuid4

from docx import Document
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
import pytest

from api_contracts.bot_order_desk import BotOrderCommand
from api_contracts.bot_order_issuance import BotIssueDocument
from models import (
    Customer,
    CustomerType,
    DocumentArtifact,
    DocumentNumberPolicy,
    DocumentNumberReservation,
    OrderDocument,
    OrderProductLink,
    OrderProposal,
    OrderStatus,
    PublicWriteIdempotency,
)
from models.tenancy import TenantScope
from modules.documents.application import ManagedDocumentService
from modules.documents.application.errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
from services import bot_order_issuance as issuance
from services.authenticated_command_service import AuthenticatedCommandService
from services.bot_order_desk import change_order, get_order_desk
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict
from tests.integration.test_bot_order_documents import _command, _setup
from tests.integration.test_managed_document_lifecycle import _draft


PDF = b"%PDF-1.4\nissued-telegram-fixture\n%%EOF"


class RecordingConverter:
    def __init__(self):
        self.calls = []
        self.fail = False

    def convert_docx(self, content, *, filename):
        rendered = Document(BytesIO(content))
        self.calls.append(([item.text for item in rendered.paragraphs],
                           [row.cells[1].text for row in rendered.tables[0].rows[1:]]))
        if self.fail:
            raise RuntimeError("converter backend address")
        return PDF


def _issue_command(desk, *, idempotency_key=None):
    capability = desk.issuance[0]
    return BotOrderCommand(expected_revision=desk.revision, idempotency_key=idempotency_key or uuid4(),
                           change=BotIssueDocument(kind="issue_document", document_id=capability.document_id,
                                                   expected_document_revision=capability.revision, confirmed=True))


async def _ready(db, tmp_path, monkeypatch, document_type="offer"):
    ws, order, issuer, private = await _setup(db, tmp_path, monkeypatch, document_type)
    # Issued PDFs are loaded with the provider persisted on the artifact.
    monkeypatch.setattr("services.bot_order_documents.get_private_attachment_storage", lambda provider=None: private)
    converter = RecordingConverter()
    monkeypatch.setattr(issuance, "configured_pdf_converter", lambda: converter)
    if document_type == "contract":
        await _draft(db, scope=ws.scope, order=order, issuer=issuer)
    else:
        primary = await db.scalar(select(OrderProductLink).where(OrderProductLink.order_id == order.id))
        alternative = OrderProposal(order_id=order.id, name="Вариант с другим кондиционером", is_selected=False)
        db.add(alternative)
        await db.flush()
        db.add(OrderProductLink(order_id=order.id, proposal_id=alternative.id, product_id=primary.product_id,
                                title_snapshot="Модель из альтернативы", price=1650, quantity=2))
        await db.commit()
        desk = await get_order_desk(db, ws, order.id)
        await change_order(db, ws, order.id, _command(desk, issuer.id, document_type, proposal_id=alternative.id))
    desk = await get_order_desk(db, ws, order.id)
    assert desk.issuance[0].state == "ready" and desk.documents[0].can_preview
    return ws, order, issuer, private, desk, converter


@pytest.mark.parametrize("document_type", ["offer", "invoice", "contract"])
async def test_official_bot_issue_uses_saved_draft_and_same_pdf_on_retry(db, tmp_path, monkeypatch, document_type):
    ws, order, issuer, _, desk, converter = await _ready(db, tmp_path, monkeypatch, document_type)
    command = _issue_command(desk)
    document_id = command.change.document_id
    with pytest.raises(ManagedDocumentConflictError, match="после выпуска"):
        await issuance.issued_pdf(db, ws.scope, order.id, document_id)
    updated = await change_order(db, ws, order.id, command)
    assert updated.issuance[0].state == "issued" and updated.issuance[0].can_download_pdf
    assert not updated.documents[0].can_preview
    assert updated.selected_proposal_id == desk.selected_proposal_id
    doc = await db.get(OrderDocument, document_id)
    assert doc.status == "issued" and doc.issued_at and not doc.sent_at and doc.legal_entity_id == issuer.id
    full_number = doc.render_snapshot["values"]["document.official_full_number"]
    assert full_number in updated.documents[0].title
    paragraphs, titles = converter.calls[0]
    assert any(full_number in paragraph for paragraph in paragraphs)
    assert titles == (["Кондиционер"] if document_type == "contract" else ["Модель из альтернативы"])

    # Scope checks apply independently to the requested bytes and to issuing the draft.
    for scope in (TenantScope(2, 1), TenantScope(1, 99)):
        with pytest.raises(ManagedDocumentNotFoundError):
            await issuance.issued_pdf(db, scope, order.id, document_id)
    with pytest.raises(ManagedDocumentNotFoundError):
        await issuance.issued_pdf(db, ws.scope, order.id + 1, document_id)
    with pytest.raises(HTTPException) as error:
        await issuance.issued_pdf(db, replace(ws.scope, demo_read_only=True), order.id, document_id)
    assert error.value.status_code == 403
    assert await issuance.issued_pdf(db, ws.scope, order.id, document_id) == PDF

    replay = await change_order(db, ws, order.id, command)
    assert replay.documents[0].title == updated.documents[0].title
    assert await db.scalar(select(func.count(DocumentNumberReservation.id))) == 1
    assert await db.scalar(select(func.count(DocumentArtifact.id))) == 2
    assert len(converter.calls) == 1
    with pytest.raises(PublicWriteIdempotencyConflict):
        await change_order(db, ws, order.id, command.model_copy(update={"expected_revision": updated.revision}))

    order.status = OrderStatus.CLOSED
    order.closing_result = "won"
    await db.commit()
    assert await issuance.issued_pdf(db, ws.scope, order.id, document_id) == PDF


@pytest.mark.parametrize("storage_failure", [False, True])
@pytest.mark.parametrize("new_key", [False, True])
async def test_failure_preserves_reserved_number_for_retry(db, tmp_path, monkeypatch, storage_failure, new_key):
    ws, order, issuer, private, desk, converter = await _ready(db, tmp_path, monkeypatch)
    order_id, issuer_id = order.id, issuer.id
    command = _issue_command(desk)
    original_save = private.save

    async def fail_pdf_save(**kwargs):
        if kwargs["content_type"] == "application/pdf":
            raise RuntimeError("private provider key")
        return await original_save(**kwargs)

    if storage_failure:
        monkeypatch.setattr(private, "save", fail_pdf_save)
    else:
        converter.fail = True
    with pytest.raises(HTTPException) as error:
        await change_order(db, ws, order_id, command)
    assert error.value.status_code == 503
    assert "сохранил номер" in error.value.detail
    assert error.value.headers == {"X-Kitlane-Document-State": "number-reserved"}
    assert "private provider key" not in error.value.detail and "converter backend address" not in error.value.detail
    reserved = await get_order_desk(db, ws, order_id)
    assert reserved.issuance[0].state == "reserved" and not reserved.issuance[0].can_download_pdf
    assert await db.scalar(select(func.count(DocumentArtifact.id))) == 0
    reservation = await db.scalar(select(DocumentNumberReservation))
    assert reservation.status == "reserved"
    reservation_id, number = reservation.id, reservation.number_text
    db.add(DocumentNumberPolicy(tenant_id=ws.scope.tenant_id, legal_entity_id=issuer_id, document_type="offer",
                                series="НОВАЯ-", minimum_width=7))
    await db.commit()
    converter.fail = False
    monkeypatch.setattr(private, "save", original_save)
    updated = await change_order(db, ws, order_id, _issue_command(reserved) if new_key else command)
    assert updated.issuance[0].state == "issued" and number in updated.documents[0].title
    reservation = await db.get(DocumentNumberReservation, reservation_id, populate_existing=True)
    assert reservation.status == "assigned" and reservation.number_text == number
    assert await db.scalar(select(func.count(DocumentNumberReservation.id))) == 1
    assert await db.scalar(select(func.count(DocumentArtifact.id))) == 2
    assert len(converter.calls) == 2


@pytest.mark.parametrize("fail_commit", [1, 2])
async def test_commit_ack_loss_can_replay_without_converting_twice(db, tmp_path, monkeypatch, fail_commit):
    ws, order, _, _, desk, converter = await _ready(db, tmp_path, monkeypatch)
    command = _issue_command(desk)
    commit = db.commit
    count = 0

    async def lose_ack():
        nonlocal count
        count += 1
        await commit()
        if count == fail_commit:
            raise ConnectionError("commit acknowledgement lost")

    monkeypatch.setattr(db, "commit", lose_ack)
    with pytest.raises(ConnectionError, match="acknowledgement"):
        await change_order(db, ws, order.id, command)
    monkeypatch.setattr(db, "commit", commit)
    replayed = await change_order(db, ws, order.id, command)
    assert replayed.issuance[0].state == "issued"
    assert await db.scalar(select(func.count(DocumentNumberReservation.id))) == 1
    assert await db.scalar(select(func.count(PublicWriteIdempotency.id))) == 3
    assert len(converter.calls) == 1


async def test_manager_can_finalize_between_telegram_stages(db, tmp_path, monkeypatch):
    ws, order, _, private, desk, converter = await _ready(db, tmp_path, monkeypatch)
    command = _issue_command(desk)
    execute = AuthenticatedCommandService.execute

    async def issue_in_manager_after_reserve(session, **kwargs):
        result = await execute(session, **kwargs)
        if kwargs["command_name"] == "order.telegram_change" and not result.replayed:
            async with async_sessionmaker(db.bind, expire_on_commit=False)() as manager_session:
                await ManagedDocumentService.issue(
                    manager_session, tenant_scope=ws.scope, document_id=command.change.document_id,
                    template_storage=db.info["test_template_storage"],
                    artifact_storage=PrivateDocumentArtifactStorage(private), pdf_converter=converter,
                )
        return result

    monkeypatch.setattr(AuthenticatedCommandService, "execute", issue_in_manager_after_reserve)
    result = await change_order(db, ws, order.id, command)
    assert result.issuance[0].state == "issued"
    assert await db.scalar(select(func.count(DocumentNumberReservation.id))) == 1
    assert len(converter.calls) == 1


async def test_stale_versions_and_draft_blocking_reasons(db, tmp_path, monkeypatch):
    ws, order, _, _, desk, _ = await _ready(db, tmp_path, monkeypatch)
    stale = _issue_command(desk)
    draft = await db.get(OrderDocument, stale.change.document_id)
    draft.render_snapshot = {**draft.render_snapshot, "values": {
        **draft.render_snapshot["values"], "contract.additional_conditions": "Изменённые условия",
    }}
    await db.commit()
    updated = await get_order_desk(db, ws, order.id)
    assert updated.issuance[0].state == "ready" and updated.issuance[0].revision != stale.change.expected_document_revision
    command = stale.model_copy(update={"expected_revision": updated.revision})
    with pytest.raises(ManagedDocumentConflictError, match="Черновик изменился"):
        await change_order(db, ws, order.id, command)

    line = await db.scalar(select(OrderProductLink).where(OrderProductLink.proposal_id == draft.proposal_id))
    line.price += 100
    await db.commit()
    stale_proposal = (await get_order_desk(db, ws, order.id)).issuance[0]
    assert stale_proposal.state == "blocked" and "Предложение изменилось" in stale_proposal.reason
    doc = OrderDocument(order_id=order.id, doc_type="invoice", number="Старый счёт", google_file_id="abc")
    external = OrderDocument(order_id=order.id, tenant_id=ws.scope.tenant_id, doc_type="contract",
                             number="Внешний договор", origin="external_upload", external_status="received")
    db.add_all([doc, external])
    order.status = OrderStatus.CLOSED
    order.closing_result = "lost"
    await db.commit()
    blocked = {item.document_id: item.reason for item in (await get_order_desk(db, ws, order.id)).issuance}
    assert "Заказ закрыт" in blocked[draft.id]
    assert "прежнем контуре" in blocked[doc.id]
    assert "загружен извне" in blocked[external.id]
    assert await db.scalar(select(func.count(DocumentNumberReservation.id))) == 0


async def test_actual_consumer_requisites_gate_applies_to_older_draft(db, tmp_path, monkeypatch):
    document_type = "b2c_route_laying_act"
    ws, order, issuer, _ = await _setup(db, tmp_path, monkeypatch, document_type)
    monkeypatch.setattr(issuance, "configured_pdf_converter", RecordingConverter)
    issuer.requisites = {"offer_url": "https://example.test/offer", "offer_version": "2026",
                         "offer_published_on": "01.01.2026"}
    customer = await db.get(Customer, order.customer_id)
    customer.type = CustomerType.individual
    customer.name = customer.full_legal_name = ""
    await db.commit()
    draft = await _draft(db, scope=ws.scope, order=order, issuer=issuer, document_type=document_type)
    desk = await get_order_desk(db, ws, order.id)
    assert desk.issuance[0].state == "blocked" and "ФИО клиента" in desk.issuance[0].reason
    assert desk.documents[0].can_preview

    # Old drafts may lack the readiness hint. The command checks their stored DOCX
    # and snapshot through the native readiness gate before any reservation.
    draft.render_snapshot = {**draft.render_snapshot, "meta": {
        key: value for key, value in draft.render_snapshot["meta"].items() if key != "customer_readiness"
    }}
    await db.commit()
    desk = await get_order_desk(db, ws, order.id)
    assert desk.issuance[0].state == "ready"
    with pytest.raises(ManagedDocumentConflictError, match="ФИО клиента"):
        await change_order(db, ws, order.id, _issue_command(desk))
    assert await db.scalar(select(func.count(DocumentNumberReservation.id))) == 0
    assert await db.scalar(select(func.count(DocumentArtifact.id))) == 0


async def test_oversized_issued_pdf_is_rejected_before_storage_read(db, tmp_path, monkeypatch):
    ws, order, _, private, desk, _ = await _ready(db, tmp_path, monkeypatch)
    command = _issue_command(desk)
    await change_order(db, ws, order.id, command)
    pdf = await db.scalar(select(DocumentArtifact).where(DocumentArtifact.kind == "pdf"))
    pdf.size_bytes = issuance.MAX_PDF_BYTES + 1
    await db.commit()

    async def unexpected_read(*_args, **_kwargs):
        raise AssertionError("oversized artifact must not be read")

    monkeypatch.setattr(private, "read_bounded", unexpected_read)
    capability = (await get_order_desk(db, ws, order.id)).issuance[0]
    assert not capability.can_download_pdf and "превышает" in capability.reason
    with pytest.raises(HTTPException) as error:
        await issuance.issued_pdf(db, ws.scope, order.id, command.change.document_id)
    assert error.value.status_code == 413
