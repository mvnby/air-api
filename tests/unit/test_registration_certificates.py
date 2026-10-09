from io import BytesIO
from types import SimpleNamespace
import pytest
from PIL import Image
from pypdf import PdfWriter
from sqlalchemy import select
from models import Customer, DocumentLegalEntity, Order, OrderDocument
from models.legal_entity_attachment import LegalEntityAttachment
from models.tenancy import TenantScope
from services.legal_entity_attachment_service import (
    LegalEntityAttachmentService as Certificates,
    validate_certificate,
    MAX_CERTIFICATE_BYTES,
)
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from services.mail_smtp_service import (
    MailSmtpService,
    PartnerTenantSmtpUnavailableError,
)
from services.order_email_template_service import OrderEmailTemplateService


def scan(color="white", fmt="PNG"):
    output = BytesIO()
    Image.new("RGB", (4, 4), color).save(output, format=fmt)
    return output.getvalue()


@pytest.mark.parametrize(
    "fmt,mime,extension", [("PNG", "image/png", "png"), ("JPEG", "image/jpeg", "jpg")]
)
def test_actual_file_type_and_safe_name(fmt, mime, extension):
    assert validate_certificate(scan(fmt=fmt), "../../опасно\r\n.exe") == (
        mime,
        extension,
        f"опасно__.{extension}",
    )
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = BytesIO()
    writer.write(output)
    assert validate_certificate(output.getvalue(), "scan.pdf")[0] == "application/pdf"


@pytest.mark.parametrize(
    "content", [b"", b"%PDF-invalid", b"not png", b"x" * (MAX_CERTIFICATE_BYTES + 1)]
)
def test_invalid_certificate(content):
    with pytest.raises(ValueError):
        validate_certificate(content, "certificate.pdf")


@pytest.fixture
async def certificates(db, monkeypatch, tmp_path):
    storage = LocalPrivateAttachmentStorage(tmp_path / "certificates")
    monkeypatch.setattr(
        "services.legal_entity_attachment_service.get_private_attachment_storage",
        lambda *args: storage,
    )
    issuer = DocumentLegalEntity(
        tenant_id=1,
        slug="certificate-issuer",
        display_name="ИП Партнёр",
        is_default=True,
    )
    db.add(issuer)
    await db.commit()
    await db.refresh(issuer)
    first = await Certificates.upload(db, 1, issuer.id, scan(), "registration.png")
    return issuer, first


@pytest.mark.asyncio
async def test_replacement_keeps_original_bytes_and_switches_current(db, certificates):
    issuer, first = certificates
    second = await Certificates.upload(db, 1, issuer.id, scan("blue"), "new.png")
    await db.refresh(first)
    assert first.is_current is False and second.is_current is True
    assert await Certificates.read(first) == scan()
    await Certificates.make_current(db, 1, first)
    await db.refresh(second)
    assert first.is_current is True and second.is_current is False
    with pytest.raises(ValueError):
        await Certificates.get(db, 2, first.id)
    with pytest.raises(ValueError):
        await Certificates.entity(db, 2, issuer.id)


@pytest.mark.asyncio
async def test_mail_binding_fails_closed(db, certificates, tenant_scope):
    issuer, first = certificates
    assert (
        await Certificates.resolve_for_mail(db, tenant_scope, first.id, [])
    ).id == first.id
    assert (
        await Certificates.resolve_for_mail(
            db, tenant_scope, first.id, [SimpleNamespace(legal_entity_id=issuer.id)]
        )
    ).id == first.id
    for docs, explicit in [
        ([SimpleNamespace(legal_entity_id=None)], None),
        (
            [
                SimpleNamespace(legal_entity_id=issuer.id),
                SimpleNamespace(legal_entity_id=999),
            ],
            None,
        ),
        ([], 999),
        ([SimpleNamespace(legal_entity_id=issuer.id)], 999),
    ]:
        with pytest.raises(ValueError):
            await Certificates.resolve_for_mail(
                db, tenant_scope, first.id, docs, explicit
            )
    with pytest.raises(ValueError):
        await Certificates.resolve_for_mail(
            db,
            TenantScope(tenant_id=2, storefront_id=2, is_system=False),
            first.id,
            [],
            issuer.id,
        )


@pytest.mark.asyncio
async def test_certificate_only_compose_send_history_immutable(
    db, certificates, tenant_scope, monkeypatch
):
    issuer, first = certificates
    customer = Customer(tenant_id=1, name="Клиент", phone="+375291111111")
    db.add(customer)
    await db.flush()
    order = Order(
        tenant_id=1, storefront_id=1, customer_id=customer.id, status="negotiation"
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    composed = await OrderEmailTemplateService.compose(
        db,
        tenant_scope=tenant_scope,
        order_id=order.id,
        document_ids=[],
        registration_certificate_id=first.id,
    )
    assert "Свидетельство о регистрации" in composed["subject"]
    captured = []
    monkeypatch.setattr(
        MailSmtpService,
        "_configured_from_email",
        staticmethod(lambda: "sender@example.com"),
    )
    monkeypatch.setattr(
        MailSmtpService, "send_message", staticmethod(lambda msg: captured.append(msg))
    )
    row = await MailSmtpService.send_order_email(
        db,
        tenant_scope=tenant_scope,
        order_id=order.id,
        to_email="client@example.com",
        subject=composed["subject"],
        body_text=composed["body_text"],
        registration_certificate_id=first.id,
    )
    await Certificates.upload(db, 1, issuer.id, scan("blue"), "replacement.png")
    await db.refresh(row)
    assert row.attachments[0]["registration_certificate_id"] == first.id
    assert row.attachments[0]["checksum_sha256"] == first.checksum_sha256
    assert row.attachments[0]["mime_type"] == "image/png"
    assert list(captured[0].iter_attachments())[0].get_payload(decode=True) == scan()
    assert await Certificates.read(first) == scan()
    with pytest.raises(PartnerTenantSmtpUnavailableError):
        await MailSmtpService.send_order_email(
            db,
            tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=False),
            order_id=order.id,
            to_email="client@example.com",
            subject="x",
            body_text="x",
            registration_certificate_id=first.id,
        )


@pytest.mark.asyncio
async def test_corrupt_saved_bytes_fail_integrity(db, certificates, monkeypatch):
    _, first = certificates

    class CorruptStorage:
        async def read(self, key):
            return b"corrupt"

    monkeypatch.setattr(
        "services.legal_entity_attachment_service.get_private_attachment_storage",
        lambda *args: CorruptStorage(),
    )
    with pytest.raises(ValueError):
        await Certificates.read(first)


@pytest.mark.asyncio
async def test_concurrent_replacements_leave_exactly_one_current(
    db_engine, monkeypatch, tmp_path
):
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

    storage = LocalPrivateAttachmentStorage(tmp_path / "concurrent-certificates")
    monkeypatch.setattr(
        "services.legal_entity_attachment_service.get_private_attachment_storage",
        lambda *args: storage,
    )
    async with AsyncSession(bind=db_engine, expire_on_commit=False) as session:
        issuer = DocumentLegalEntity(
            tenant_id=1,
            slug="concurrent-certificate",
            display_name="Issuer",
            is_default=True,
        )
        session.add(issuer)
        await session.commit()
        await session.refresh(issuer)
        issuer_id = issuer.id
        original = await Certificates.upload(
            session, 1, issuer_id, scan(), "original.png"
        )

    async def upload(color):
        async with AsyncSession(bind=db_engine, expire_on_commit=False) as other:
            return await Certificates.upload(
                other, 1, issuer_id, scan(color), color + ".png"
            )

    versions = await asyncio.gather(upload("red"), upload("blue"))
    async with AsyncSession(bind=db_engine) as session:
        current = (
            (
                await session.execute(
                    select(LegalEntityAttachment).where(
                        LegalEntityAttachment.legal_entity_id == issuer_id,
                        LegalEntityAttachment.is_current.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(current) == 1 and current[0].id in {item.id for item in versions}
        assert await Certificates.read(original) == scan()


@pytest.mark.asyncio
async def test_certificate_counts_against_mail_count_and_total_caps(
    db, certificates, tenant_scope, monkeypatch
):
    from services.document_service import DocumentService

    issuer, first = certificates
    customer = Customer(tenant_id=1, name="Клиент", phone="+375291111111")
    db.add(customer)
    await db.flush()
    order = Order(
        tenant_id=1, storefront_id=1, customer_id=customer.id, status="negotiation"
    )
    db.add(order)
    await db.flush()
    doc = OrderDocument(
        tenant_id=1,
        legal_entity_id=issuer.id,
        order_id=order.id,
        doc_type="uploaded_pdf",
        google_file_id="test",
        number="DOC",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(order)
    await db.refresh(doc)
    calls = []

    async def download(*args, **kwargs):
        return BytesIO(b"x" * 20), "doc.pdf"

    async def send(*args, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(DocumentService, "get_download_stream", staticmethod(download))
    monkeypatch.setattr(MailSmtpService, "send_and_record", staticmethod(send))
    payload = dict(
        tenant_scope=tenant_scope,
        order_id=order.id,
        to_email="client@example.com",
        subject="Docs",
        body_text="Docs",
        document_ids=[doc.id],
        registration_certificate_id=first.id,
    )
    monkeypatch.setattr("services.mail_smtp_service.MAX_ORDER_EMAIL_DOCUMENTS", 1)
    with pytest.raises(ValueError):
        await MailSmtpService.send_order_email(db, **payload)
    monkeypatch.setattr("services.mail_smtp_service.MAX_ORDER_EMAIL_DOCUMENTS", 10)
    monkeypatch.setattr(
        "services.mail_smtp_service.MAX_ORDER_EMAIL_TOTAL_ATTACHMENT_BYTES",
        first.size_bytes + 10,
    )
    with pytest.raises(ValueError):
        await MailSmtpService.send_order_email(db, **payload)
    assert not calls


@pytest.mark.asyncio
async def test_certificate_only_partner_compose_uses_explicit_issuer(db, certificates):
    second = DocumentLegalEntity(
        tenant_id=1, slug="alternate", display_name="ООО Второй отправитель"
    )
    customer = Customer(tenant_id=1, name="Клиент", phone="+375291111111")
    db.add_all([second, customer])
    await db.flush()
    order = Order(
        tenant_id=1, storefront_id=1, customer_id=customer.id, status="negotiation"
    )
    db.add(order)
    await db.commit()
    await db.refresh(second)
    await db.refresh(order)
    certificate = await Certificates.upload(db, 1, second.id, scan(), "alternate.png")
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=False)
    with pytest.raises(ValueError):
        await OrderEmailTemplateService.compose(
            db,
            tenant_scope=scope,
            order_id=order.id,
            document_ids=[],
            registration_certificate_id=certificate.id,
        )
    result = await OrderEmailTemplateService.compose(
        db,
        tenant_scope=scope,
        order_id=order.id,
        document_ids=[],
        registration_certificate_id=certificate.id,
        legal_entity_id=second.id,
    )
    assert result["body_text"].endswith("ООО Второй отправитель")


@pytest.mark.asyncio
async def test_missing_saved_bytes_fail_closed(db, certificates, monkeypatch):
    _, first = certificates

    class MissingStorage:
        async def read(self, key):
            raise FileNotFoundError(key)

    monkeypatch.setattr(
        "services.legal_entity_attachment_service.get_private_attachment_storage",
        lambda *args: MissingStorage(),
    )
    with pytest.raises(ValueError, match="недоступно"):
        await Certificates.read(first)
