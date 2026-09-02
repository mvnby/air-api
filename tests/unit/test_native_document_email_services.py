from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from core.config import settings
from models import Customer, DocumentLegalEntity, Order, OrderDocument
from models.tenancy import TenantScope
from modules.documents.application.artifact_helpers import artifact_row
from modules.documents.infrastructure.artifact_storage import (
    PrivateDocumentArtifactStorage,
)
from services.document_service import DocumentService, NativeManagedDocumentError
from services.mail_smtp_service import (
    MAX_ORDER_EMAIL_DOCUMENTS,
    MailSmtpService,
    PartnerTenantSmtpUnavailableError,
)
from services.order_email_template_service import OrderEmailTemplateService
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage


SYSTEM_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def native_email_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'native-document-email.db'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _issued_document(session: AsyncSession) -> OrderDocument:
    customer = Customer(
        tenant_id=1,
        name="ООО Клиент",
        phone="+375291111111",
        email="client@example.com",
        type="company",
    )
    session.add(customer)
    await session.flush()
    order = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=customer.id,
        status="negotiation",
    )
    issuer = DocumentLegalEntity(
        tenant_id=1,
        slug="main",
        display_name="ИП Продавец",
        status="active",
        is_default=True,
    )
    session.add_all([order, issuer])
    await session.flush()
    document = OrderDocument(
        tenant_id=1,
        legal_entity_id=issuer.id,
        order_id=order.id,
        doc_type="contract",
        status="issued",
        internal_reference="doc_email_test_1",
        official_series="Д-",
        official_period_key="2026",
        official_number="7",
        official_date=date(2026, 9, 2),
        number="Д-2026-007",
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


@pytest.mark.asyncio
async def test_native_download_reads_tenant_authoritative_pdf(
    native_email_session: AsyncSession,
    tmp_path: Path,
    monkeypatch,
):
    document = await _issued_document(native_email_session)
    private = LocalPrivateAttachmentStorage(tmp_path / "native-email-private")
    artifact_storage = PrivateDocumentArtifactStorage(private)
    stored = await artifact_storage.save(
        tenant_id=1,
        document_id=int(document.id),
        kind="pdf",
        filename="Договор-Д-2026-007.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4\nnative-authoritative\n%%EOF",
    )
    native_email_session.add(artifact_row(stored))
    await native_email_session.commit()
    monkeypatch.setattr(
        "services.private_attachment_storage_service.get_private_attachment_storage",
        lambda provider=None: private,
    )

    stream, filename = await DocumentService.get_download_stream(
        native_email_session,
        int(document.id),
        tenant_scope=SYSTEM_SCOPE,
    )

    assert stream.getvalue() == b"%PDF-1.4\nnative-authoritative\n%%EOF"
    assert filename.endswith(".pdf")
    foreign_stream, foreign_filename = await DocumentService.get_download_stream(
        native_email_session,
        int(document.id),
        tenant_scope=TenantScope(tenant_id=2, storefront_id=2),
    )
    assert (foreign_stream, foreign_filename) == (None, None)
    with pytest.raises(NativeManagedDocumentError, match="контекст организации"):
        await DocumentService.get_download_stream(
            native_email_session,
            int(document.id),
        )


@pytest.mark.asyncio
async def test_tenant_scoped_download_preserves_legacy_google_export(
    native_email_session: AsyncSession,
    monkeypatch,
):
    customer = Customer(
        tenant_id=1,
        name="Legacy Client",
        phone="+375292222222",
        type="individual",
    )
    native_email_session.add(customer)
    await native_email_session.flush()
    order = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=customer.id,
    )
    native_email_session.add(order)
    await native_email_session.flush()
    document = OrderDocument(
        order_id=order.id,
        doc_type="invoice",
        number="С-LEGACY-1",
        google_file_id="legacy-google-id",
        google_edit_url="https://docs.google.com/document/d/legacy-google-id/edit",
    )
    native_email_session.add(document)
    await native_email_session.commit()
    await native_email_session.refresh(document)
    def export_file(file_id, mime_type):
        return BytesIO(f"{file_id}:{mime_type}".encode())
    monkeypatch.setattr(
        "services.document_service.get_google_service",
        lambda: SimpleNamespace(export_file=export_file),
    )

    stream, filename = await DocumentService.get_download_stream(
        native_email_session,
        int(document.id),
        tenant_scope=SYSTEM_SCOPE,
    )

    assert stream.getvalue() == b"legacy-google-id:application/pdf"
    assert filename == "%D0%A1-LEGACY-1.pdf"


@pytest.mark.asyncio
async def test_successful_native_email_marks_issued_document_sent(
    native_email_session: AsyncSession,
    monkeypatch,
):
    document = await _issued_document(native_email_session)
    monkeypatch.setattr(settings, "MAIL_SMTP_USERNAME", "sales@mvn.by")
    monkeypatch.setattr(settings, "MAIL_SMTP_PASSWORD", "secret")
    monkeypatch.setattr(settings, "MAIL_FROM_EMAIL", "sales@mvn.by")
    monkeypatch.setattr(MailSmtpService, "send_message", lambda _message: None)

    async def fake_download(_session, doc_id: int, **kwargs):
        assert kwargs["tenant_scope"] == SYSTEM_SCOPE
        return BytesIO(b"%PDF-1.4\nemail\n%%EOF"), f"document-{doc_id}.pdf"

    monkeypatch.setattr(DocumentService, "get_download_stream", fake_download)

    email = await MailSmtpService.send_order_email(
        native_email_session,
        tenant_scope=SYSTEM_SCOPE,
        order_id=document.order_id,
        to_email="client@example.com",
        subject="Договор",
        body_text="Документ во вложении.",
        document_ids=[int(document.id)],
    )

    refreshed = await native_email_session.get(OrderDocument, document.id)
    assert email.status == "sent"
    assert refreshed.status == "sent"
    assert refreshed.sent_at == email.sent_at


@pytest.mark.asyncio
async def test_failed_native_email_keeps_document_issued(
    native_email_session: AsyncSession,
    monkeypatch,
):
    document = await _issued_document(native_email_session)
    monkeypatch.setattr(settings, "MAIL_SMTP_USERNAME", "sales@mvn.by")
    monkeypatch.setattr(settings, "MAIL_SMTP_PASSWORD", "secret")
    monkeypatch.setattr(settings, "MAIL_FROM_EMAIL", "sales@mvn.by")

    async def fake_download(_session, doc_id: int, **_kwargs):
        return BytesIO(b"%PDF-1.4\nemail\n%%EOF"), f"document-{doc_id}.pdf"

    def failed_send(_message):
        raise OSError("SMTP unavailable")

    monkeypatch.setattr(DocumentService, "get_download_stream", fake_download)
    monkeypatch.setattr(MailSmtpService, "send_message", failed_send)

    with pytest.raises(RuntimeError, match="SMTP unavailable"):
        await MailSmtpService.send_order_email(
            native_email_session,
            tenant_scope=SYSTEM_SCOPE,
            order_id=document.order_id,
            to_email="client@example.com",
            subject="Договор",
            body_text="Документ во вложении.",
            document_ids=[int(document.id)],
        )

    refreshed = await native_email_session.get(OrderDocument, document.id)
    assert refreshed.status == "issued"
    assert refreshed.sent_at is None


@pytest.mark.asyncio
async def test_partner_tenant_cannot_use_global_smtp(
    native_email_session: AsyncSession,
    monkeypatch,
):
    called = False

    def unexpected_send(_message):
        nonlocal called
        called = True

    monkeypatch.setattr(MailSmtpService, "send_message", unexpected_send)
    with pytest.raises(PartnerTenantSmtpUnavailableError, match="партнерскому"):
        await MailSmtpService.send_order_email(
            native_email_session,
            tenant_scope=TenantScope(tenant_id=2, storefront_id=2, is_system=False),
            order_id=1,
            to_email="client@example.com",
            subject="Документ",
            body_text="Документ во вложении.",
            document_ids=[],
        )
    assert called is False


@pytest.mark.asyncio
async def test_native_email_rejects_unbounded_attachment_count(
    native_email_session: AsyncSession,
):
    with pytest.raises(ValueError, match="не более"):
        await MailSmtpService.send_order_email(
            native_email_session,
            tenant_scope=SYSTEM_SCOPE,
            order_id=1,
            to_email="client@example.com",
            subject="Документы",
            body_text="Документы во вложении.",
            document_ids=list(range(1, MAX_ORDER_EMAIL_DOCUMENTS + 2)),
        )


@pytest.mark.asyncio
async def test_compose_is_tenant_scoped_and_uses_partner_sender_name(
    native_email_session: AsyncSession,
):
    document = await _issued_document(native_email_session)
    partner_scope = TenantScope(tenant_id=1, storefront_id=1, is_system=False)

    result = await OrderEmailTemplateService.compose(
        native_email_session,
        tenant_scope=partner_scope,
        order_id=document.order_id,
        document_ids=[int(document.id)],
    )

    assert result["document_ids"] == [document.id]
    assert result["body_text"].endswith("ИП Продавец")
    assert "Мастер Воздуха" not in result["body_text"]
    with pytest.raises(ValueError, match="Order not found"):
        await OrderEmailTemplateService.compose(
            native_email_session,
            tenant_scope=TenantScope(tenant_id=2, storefront_id=2),
            order_id=document.order_id,
            document_ids=[int(document.id)],
        )
