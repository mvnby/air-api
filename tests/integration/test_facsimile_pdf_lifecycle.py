from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas
from sqlmodel import select

from models import DocumentArtifact, DocumentFacsimileAsset, OrderStatus, TenantAuditEvent
from models.tenancy import TenantScope
from modules.documents.application import ManagedDocumentService
from modules.documents.application.artifact_helpers import stored_artifact
from modules.documents.application.facsimile_context import FacsimilePdfError
from modules.documents.application.facsimile_pdf import FACSIMILE_AUDIT_ACTION, FacsimilePdfService
from modules.documents.application.facsimile_preview import FacsimilePreviewService
from modules.documents.domain.facsimiles import FacsimilePdfPlacement
from services.private_attachment_storage_service import VariantScopedPrivateAttachmentStorage
from tests.integration.test_managed_document_lifecycle import _draft, _seed


class TwoPagePdfConverter:
    def convert_docx(self, content: bytes, *, filename="document.docx") -> bytes:
        assert content.startswith(b"PK")
        output = BytesIO()
        canvas = Canvas(output, pagesize=(595, 842))
        for page in (1, 2):
            canvas.drawString(50, 800, f"Original document page {page}")
            canvas.showPage()
        canvas.save()
        return output.getvalue()


async def _issued(db, tmp_path, monkeypatch):
    scope, order, issuer, templates, storage = await _seed(db, tmp_path)
    draft = await _draft(db, scope=scope, order=order, issuer=issuer)
    issued = await ManagedDocumentService.issue(
        db, tenant_scope=scope, document_id=draft.id, template_storage=templates,
        artifact_storage=storage, pdf_converter=TwoPagePdfConverter(),
    )
    private = storage._storage.storage
    monkeypatch.setattr(
        "modules.documents.application.facsimile_context.get_private_attachment_storage",
        lambda provider: private,
    )
    scoped = VariantScopedPrivateAttachmentStorage(private, variant_scope="document-facsimiles")
    for kind, color in (("signature", (0, 0, 255, 150)), ("seal", (255, 0, 0, 150))):
        output = BytesIO()
        Image.new("RGBA", (100, 50), color).save(output, format="PNG")
        content = output.getvalue()
        saved = await scoped.save(
            content=content, content_hash=sha256(content).hexdigest(),
            extension="png", content_type="image/png", variant=f"tenant-1-{kind}",
        )
        db.add(DocumentFacsimileAsset(
            tenant_id=scope.tenant_id, legal_entity_id=issuer.id, kind=kind,
            provider=saved.provider, storage_key=saved.storage_key,
            checksum_sha256=sha256(content).hexdigest(), size_bytes=len(content),
        ))
    await db.commit()
    return scope, order, issued.document, storage


def _placement(preview, **changes):
    values = dict(
        source_checksum_sha256=preview["source_checksum_sha256"],
        expected_signed_artifact_id=preview["signed_artifact_id"],
        signature_asset_id=preview["signature"]["asset_id"],
        seal_asset_id=preview["seal"]["asset_id"],
        signature=dict(page_number=1, x_mm=20, y_mm=30, width_mm=40),
        seal=dict(page_number=2, x_mm=70, y_mm=45, width_mm=30),
    )
    values.update(changes)
    return FacsimilePdfPlacement(**values)


async def _describe(db, scope, document):
    return await FacsimilePreviewService.describe(db, tenant_scope=scope, document_id=document.id)


async def _prepare(db, scope, document, storage, placement):
    return await FacsimilePdfService.prepare(
        db, tenant_scope=scope, document_id=document.id,
        artifact_storage=storage, placement=placement, actor_username="facsimile-manager",
    )


@pytest.mark.asyncio
async def test_visual_placement_without_legacy_template_preserves_pdf_and_audits_edits(db, tmp_path, monkeypatch):
    scope, order, document, storage = await _issued(db, tmp_path, monkeypatch)
    preview = await _describe(db, scope, document)
    assert preview["can_save"] is True
    assert preview["signed_artifact_id"] is None
    assert [page["page_number"] for page in preview["pages"]] == [1, 2]
    assert preview["placement"]["signature"]["page_number"] == 2
    base = (await db.execute(select(DocumentArtifact).where(
        DocumentArtifact.order_document_id == document.id, DocumentArtifact.kind == "pdf"
    ))).scalar_one()
    original = await storage.read(stored_artifact(base))

    first_placement = _placement(preview)
    first = await _prepare(db, scope, document, storage, first_placement)
    first_bytes = await storage.read(stored_artifact(first))
    reader = PdfReader(BytesIO(first_bytes))
    assert first.kind == "signed_pdf" and first.is_authoritative
    assert len(reader.pages) == 2
    assert all("/XObject" in page["/Resources"] for page in reader.pages)
    assert [page.extract_text().strip() for page in reader.pages] == [
        "Original document page 1", "Original document page 2"
    ]
    after_first = await _describe(db, scope, document)
    assert after_first["placement"] == {
        "signature": first_placement.signature.model_dump(), "seal": first_placement.seal.model_dump()
    }
    assert after_first["signed_artifact_id"] == first.id
    next_placement = _placement(after_first, signature=dict(page_number=1, x_mm=60, y_mm=80, width_mm=35))
    second = await _prepare(db, scope, document, storage, next_placement)
    await db.refresh(first)
    assert second.id != first.id
    assert second.is_authoritative and not first.is_authoritative
    assert await storage.read(stored_artifact(first)) == first_bytes
    assert await storage.read(stored_artifact(base)) == original
    await db.refresh(base)
    assert base.is_authoritative and base.checksum_sha256 == sha256(original).hexdigest()
    latest = await _describe(db, scope, document)
    assert latest["placement"]["signature"] == next_placement.signature.model_dump()
    assert latest["signed_artifact_id"] == second.id
    audits = list((await db.execute(select(TenantAuditEvent).where(
        TenantAuditEvent.action == FACSIMILE_AUDIT_ACTION, TenantAuditEvent.entity_id == document.id
    ).order_by(TenantAuditEvent.id))).scalars())
    assert len(audits) == 2
    audit = audits[-1]
    assert (audit.tenant_id, audit.storefront_id, audit.actor_username) == (1, 1, "facsimile-manager")
    assert audit.change_set["artifact_id"] == second.id
    assert audit.change_set["previous_artifact_id"] == first.id
    assert audit.change_set["source_checksum_sha256"] == base.checksum_sha256
    assert audit.change_set["signature_asset_id"] == preview["signature"]["asset_id"]
    assert audit.change_set["seal_asset_id"] == preview["seal"]["asset_id"]
    assert audit.change_set["placement"] == latest["placement"]


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [TenantScope(tenant_id=1, storefront_id=999), TenantScope(tenant_id=999, storefront_id=1)])
async def test_preview_and_private_png_are_tenant_and_storefront_bound(db, tmp_path, monkeypatch, scope):
    own_scope, order, document, storage = await _issued(db, tmp_path, monkeypatch)
    preview = await _describe(db, own_scope, document)
    content = await FacsimilePreviewService.asset(
        db, tenant_scope=own_scope, document_id=document.id, asset_id=preview["signature"]["asset_id"]
    )
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(FacsimilePdfError, match="не найден"):
        await _describe(db, scope, document)
    with pytest.raises(FacsimilePdfError, match="не найден"):
        await FacsimilePreviewService.asset(
            db, tenant_scope=scope, document_id=document.id, asset_id=preview["signature"]["asset_id"]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["sent", "signed", "closed"])
async def test_sent_signed_or_closed_existing_pdf_cannot_be_changed(db, tmp_path, monkeypatch, status):
    scope, order, document, storage = await _issued(db, tmp_path, monkeypatch)
    signed = await _prepare(db, scope, document, storage, _placement(await _describe(db, scope, document)))
    before = await storage.read(stored_artifact(signed))
    if status == "closed":
        order.status = OrderStatus.CLOSED
        db.add(order)
    else:
        document.status = status
        db.add(document)
    await db.commit()
    preview = await _describe(db, scope, document)
    assert preview["can_save"] is False
    with pytest.raises(FacsimilePdfError, match="Заказ завершён|менять нельзя"):
        await _prepare(db, scope, document, storage, _placement(preview))
    rows = list((await db.execute(select(DocumentArtifact).where(
        DocumentArtifact.order_document_id == document.id, DocumentArtifact.kind == "signed_pdf"
    ))).scalars())
    assert len(rows) == 1 and rows[0].is_authoritative
    assert await storage.read(stored_artifact(rows[0])) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("source_checksum_sha256", "f" * 64), ("signature_asset_id", "f" * 32),
    ("seal_asset_id", "f" * 32), ("expected_signed_artifact_id", "f" * 32),
])
async def test_stale_visual_edit_creates_no_artifact_or_audit(db, tmp_path, monkeypatch, field, value):
    scope, order, document, storage = await _issued(db, tmp_path, monkeypatch)
    preview = await _describe(db, scope, document)
    with pytest.raises(FacsimilePdfError, match="изменил|изменили"):
        await _prepare(db, scope, document, storage, _placement(preview, **{field: value}))
    assert not list((await db.execute(select(DocumentArtifact).where(
        DocumentArtifact.order_document_id == document.id, DocumentArtifact.kind == "signed_pdf"
    ))).scalars())
    assert not list((await db.execute(select(TenantAuditEvent).where(
        TenantAuditEvent.entity_id == document.id, TenantAuditEvent.action == FACSIMILE_AUDIT_ACTION
    ))).scalars())
