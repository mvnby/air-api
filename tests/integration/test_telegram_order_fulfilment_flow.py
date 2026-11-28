"""Run the real staff order API against PostgreSQL and local document storage."""

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO

from docx import Document
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from models import (
    DocumentArtifact, DocumentNumberReservation, OrderDocument, PublicWriteIdempotency, StaffUser, TenantMembership,
)
from modules.documents.infrastructure.renderers.pdf import PdfConversionError
from routers.internal_bot_order_desk import router
from services import bot_order_documents, bot_order_issuance
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.integration.test_internal_bot_order_desk import ACTOR, BASE, command
from tests.integration.test_managed_document_lifecycle import _seed


class RetriableFixtureConverter:
    """Replace only the external converter, preserving real input DOCX values."""

    def __init__(self):
        self.attempts = 0

    def convert_docx(self, content: bytes, *, filename: str) -> bytes:
        self.attempts += 1
        if self.attempts == 1:
            raise PdfConversionError("fixture conversion interrupted")
        assert filename.endswith(".docx")
        rendered = Document(BytesIO(content))
        output = BytesIO()
        pdf = Canvas(output, invariant=True)
        pdf.setTitle(rendered.paragraphs[0].text)
        # The fixture template puts the final number in the heading and each
        # line amount in the last column. This converter skips visual layout.
        pdf.drawString(50, 800, rendered.paragraphs[0].text.rsplit(" ", 1)[-1])
        for index, row in enumerate(rendered.tables[0].rows[1:]):
            pdf.drawString(50, 780 - index * 20, row.cells[-1].text)
        pdf.save()
        return output.getvalue()


async def test_manager_reserves_records_payment_and_retries_official_invoice(db_engine, tmp_path, monkeypatch):
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        _, order, issuer, _, _ = await _seed(db, tmp_path, document_type="invoice")
        manager = StaffUser(
            telegram_id=ACTOR["telegram_id"], username="fulfilment-manager", display_name="Тестовый менеджер",
            primary_role="manager", roles=["manager"], telegram_verified_at=datetime.now(timezone.utc),
        )
        db.add(manager)
        await db.flush()
        db.add(TenantMembership(tenant_id=1, staff_user_id=manager.id, role="manager"))
        await db.commit()
        order_id, issuer_id = order.id, issuer.id

    private = LocalPrivateAttachmentStorage(tmp_path / "private-documents")
    monkeypatch.setattr(bot_order_documents, "get_private_attachment_storage", lambda *args: private)
    converter = RetriableFixtureConverter()
    monkeypatch.setattr(bot_order_issuance, "configured_pdf_converter", lambda: converter)
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "test-fulfilment-flow")

    async def database():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = database
    path = f"{BASE}/{order_id}"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"Authorization": "Bearer test-fulfilment-flow"},
    ) as client:
        async def apply(payload):
            response = await client.post(f"{path}/commands", json=payload)
            assert response.status_code == 200, response.text
            return response.json()

        initial = await client.get(path, params=ACTOR)
        assert initial.status_code == 200, initial.text
        desk = initial.json()
        assert desk["reserve"]["can_set_order_status"] and not desk["reserve"]["supplier_access"]
        reserve = command(desk, kind="set_order_reserve_status", status="reserved")
        desk = await apply(reserve)
        assert desk["reserve"]["manager_status"] == "reserved"

        payment = command(
            desk, kind="record_payment", amount="500.25", currency="BYN", type="prepayment",
            received_on=desk["payments"]["received_on_max"], confirmed=True,
        )
        desk = await apply(payment)
        assert len(desk["payments"]["entries"]) == 1
        assert Decimal(desk["payments"]["balance_due"]) == Decimal("999.75")
        draft = command(
            desk, kind="prepare_document", document_type="invoice", legal_entity_id=issuer_id,
            proposal_id=desk["selected_proposal_id"],
        )
        desk = await apply(draft)
        capability, = desk["issuance"]
        assert capability["state"] == "ready"
        document_id = capability["document_id"]
        download = f"{path}/documents/{document_id}/pdf"
        assert (await client.get(download, params=ACTOR)).status_code == 409

        issue = command(
            desk, kind="issue_document", document_id=document_id,
            expected_document_revision=capability["revision"], confirmed=True,
        )
        interrupted = await client.post(f"{path}/commands", json=issue)
        assert interrupted.status_code == 503, interrupted.text
        async with AsyncSession(db_engine) as db:
            reserved = await db.get(OrderDocument, document_id)
            assert reserved.status == "draft" and reserved.official_number
            number = reserved.official_number
            assert len((await db.scalars(select(DocumentNumberReservation.id))).all()) == 1
            assert not (await db.scalars(select(DocumentArtifact.id))).all()
        waiting = await client.get(path, params=ACTOR)
        assert waiting.status_code == 200 and waiting.json()["issuance"][0]["state"] == "reserved"
        assert (await client.get(download, params=ACTOR)).status_code == 409

        issued = await apply(issue)
        assert issued["issuance"][0]["state"] == "issued" and issued["issuance"][0]["can_download_pdf"]
        assert issued["reserve"]["manager_status"] == "reserved"
        assert issued["payments"] == desk["payments"]
        pdf = await client.get(download, params=ACTOR)
        assert pdf.status_code == 200 and pdf.headers["cache-control"] == "private, no-store"
        assert pdf.headers["content-type"] == "application/pdf"
        for payload in (reserve, payment, draft, issue):
            assert await apply(payload) == issued
        assert converter.attempts == 2
        assert (await client.get(download, params=ACTOR)).content == pdf.content

    async with AsyncSession(db_engine) as db:
        document = await db.get(OrderDocument, document_id)
        values = document.render_snapshot["values"]
        assert document.official_number == number and document.sent_at is None
        assert Decimal(values["totals.amount"]) == Decimal("1500.00")
        read_pdf = PdfReader(BytesIO(pdf.content))
        assert values["document.official_full_number"] in read_pdf.metadata.title
        printed_values = read_pdf.pages[0].extract_text()
        assert number in printed_values and values["totals.amount"] in printed_values
        official_pdf = await db.scalar(
            select(DocumentArtifact).where(DocumentArtifact.order_document_id == document_id, DocumentArtifact.kind == "pdf")
        )
        assert official_pdf.is_authoritative and official_pdf.checksum_sha256 == sha256(pdf.content).hexdigest()
        assert len((await db.scalars(select(DocumentNumberReservation.id))).all()) == 1
        receipts = (await db.scalars(select(PublicWriteIdempotency))).all()
        assert sorted(row.command_name for row in receipts) == [
            "authenticated:order.telegram_change",
            "authenticated:order.telegram_change",
            "authenticated:order.telegram_change",
            "authenticated:order.telegram_change",
            "authenticated:order.telegram_issue_finalize",
        ]
        assert all(row.completed_at and row.response_status == 200 for row in receipts)
