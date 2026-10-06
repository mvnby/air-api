from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from models import DocumentArtifact, TenantAuditEvent
from models.tenancy import TenantScope
from modules.documents.application import facsimile_context, facsimile_pdf, facsimile_preview
from modules.documents.application.artifact_helpers import stored_artifact
from modules.documents.application.facsimile_context import FacsimileContext, FacsimilePdfError
from modules.documents.domain.facsimiles import FacsimilePdfPlacement
from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage


def _context(*, status="issued", signed_id=None, order_status="negotiation"):
    return FacsimileContext(
        document=SimpleNamespace(status=status, template_version_id=7),
        order=SimpleNamespace(status=order_status),
        base=SimpleNamespace(checksum_sha256="a" * 64),
        signed=SimpleNamespace(id=signed_id) if signed_id else None,
        assets={kind: SimpleNamespace(id=value) for kind, value in (
            ("signature", "b" * 32), ("seal", "c" * 32)
        )},
    )


def _placement(**changes):
    values = dict(
        source_checksum_sha256="a" * 64,
        signature_asset_id="b" * 32, seal_asset_id="c" * 32,
        expected_signed_artifact_id=None,
        signature=dict(page_number=1, x_mm=20, y_mm=20, width_mm=40),
        seal=dict(page_number=2, x_mm=40, y_mm=30, width_mm=30),
    )
    values.update(changes)
    return FacsimilePdfPlacement(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize("changes,context,match", [
    ({"source_checksum_sha256": "d" * 64}, _context(), "изменились"),
    ({"signature_asset_id": "d" * 32}, _context(), "изменились"),
    ({"seal_asset_id": "d" * 32}, _context(), "изменились"),
    ({"expected_signed_artifact_id": "d" * 32}, _context(), "уже изменилась"),
    ({}, _context(signed_id="d" * 32), "уже изменилась"),
    ({"expected_signed_artifact_id": "d" * 32}, _context(status="sent", signed_id="d" * 32), "менять нельзя"),
    ({"expected_signed_artifact_id": "d" * 32}, _context(status="signed", signed_id="d" * 32), "менять нельзя"),
    ({}, _context(order_status="closed"), "Заказ завершён"),
])
async def test_invalid_or_locked_edit_never_writes_storage_or_database(monkeypatch, changes, context, match):
    monkeypatch.setattr(facsimile_pdf, "load_context", AsyncMock(return_value=context))
    read_pdf = AsyncMock()
    monkeypatch.setattr(facsimile_pdf, "read_pdf", read_pdf)
    session, storage = AsyncMock(), AsyncMock()
    with pytest.raises(FacsimilePdfError, match=match):
        await facsimile_pdf.FacsimilePdfService.prepare(
            session, tenant_scope=TenantScope(tenant_id=1, storefront_id=1),
            document_id=42, artifact_storage=storage, placement=_placement(**changes),
        )
    read_pdf.assert_not_awaited()
    storage.save.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_asset_preview_rejects_asset_outside_current_document_context(monkeypatch):
    monkeypatch.setattr(facsimile_preview, "load_context", AsyncMock(return_value=_context()))
    read_asset = AsyncMock()
    monkeypatch.setattr(facsimile_preview, "read_asset", read_asset)
    with pytest.raises(FacsimilePdfError, match="изменилась"):
        await facsimile_preview.FacsimilePreviewService.asset(
            AsyncMock(), tenant_scope=TenantScope(tenant_id=1, storefront_id=1),
            document_id=42, asset_id="d" * 32,
        )
    read_asset.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["checksum", "length", "not_png"])
async def test_asset_read_rejects_corrupted_private_png(monkeypatch, damage):
    output = BytesIO()
    Image.new("RGBA", (10, 5), (0, 0, 0, 128)).save(output, format="PNG")
    content = b"invalid image" if damage == "not_png" else output.getvalue()
    asset = SimpleNamespace(
        provider="local", storage_key="private/signature.png",
        checksum_sha256="f" * 64 if damage == "checksum" else sha256(content).hexdigest(),
        size_bytes=len(content) + (1 if damage == "length" else 0),
    )
    storage = SimpleNamespace(provider_name="local", inventory_id="test", read=AsyncMock(return_value=content))
    monkeypatch.setattr(facsimile_context, "get_private_attachment_storage", lambda provider: storage)
    with pytest.raises(FacsimilePdfError, match="повреждён"):
        await facsimile_context.read_asset(asset)


@pytest.mark.asyncio
async def test_prepare_retains_immutable_copy_and_reloads_audited_positions(monkeypatch, tmp_path):
    pdf_output, png_output = BytesIO(), BytesIO()
    canvas = Canvas(pdf_output, pagesize=(595, 842))
    for page in (1, 2):
        canvas.drawString(50, 800, f"Original page {page}")
        canvas.showPage()
    canvas.save()
    original = pdf_output.getvalue()
    Image.new("RGBA", (100, 50), (0, 0, 255, 100)).save(png_output, format="PNG")
    png = png_output.getvalue()
    context = _context()
    context.base.filename = "issued.pdf"
    context.base.checksum_sha256 = sha256(original).hexdigest()
    for module in (facsimile_pdf, facsimile_preview):
        monkeypatch.setattr(module, "load_context", AsyncMock(return_value=context))
        monkeypatch.setattr(module, "read_pdf", AsyncMock(return_value=original))
        monkeypatch.setattr(module, "read_asset", AsyncMock(return_value=png))
    session = MagicMock()
    for method in ("commit", "flush", "refresh", "execute"):
        setattr(session, method, AsyncMock())
    storage = PrivateDocumentArtifactStorage(LocalPrivateAttachmentStorage(tmp_path / "private"))
    scope = TenantScope(tenant_id=1, storefront_id=1)

    async def prepare(placement):
        return await facsimile_pdf.FacsimilePdfService.prepare(
            session, tenant_scope=scope, document_id=42, artifact_storage=storage,
            placement=placement, actor_username="manager", actor_staff_user_id=17,
        )

    first = await prepare(_placement(source_checksum_sha256=sha256(original).hexdigest()))
    first_bytes = await storage.read(stored_artifact(first))
    assert [page.extract_text().strip() for page in PdfReader(BytesIO(first_bytes)).pages] == [
        "Original page 1", "Original page 2"
    ]
    assert all("/XObject" in page["/Resources"] for page in PdfReader(BytesIO(first_bytes)).pages)
    context.signed = first
    next_placement = _placement(
        source_checksum_sha256=sha256(original).hexdigest(), expected_signed_artifact_id=first.id,
        signature=dict(page_number=1, x_mm=60, y_mm=70, width_mm=35),
    )
    second = await prepare(next_placement)
    assert not first.is_authoritative and second.is_authoritative and first.id != second.id
    assert await storage.read(stored_artifact(first)) == first_bytes
    saved_rows = [call.args[0] for call in session.add.call_args_list]
    audits = [row for row in saved_rows if isinstance(row, TenantAuditEvent)]
    audit = audits[-1]
    assert (audit.actor_username, audit.actor_staff_user_id) == ("manager", 17)
    assert (audit.tenant_id, audit.storefront_id, audit.entity_id) == (1, 1, 42)
    assert audit.change_set["artifact_id"] == second.id
    assert audit.change_set["previous_artifact_id"] == first.id
    assert audit.change_set["source_checksum_sha256"] == sha256(original).hexdigest()
    assert audit.change_set["signature_asset_id"] == "b" * 32
    assert audit.change_set["seal_asset_id"] == "c" * 32
    assert len([row for row in saved_rows if isinstance(row, DocumentArtifact) and row.is_authoritative]) == 1
    context.signed = second
    session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: audit)
    preview = await facsimile_preview.FacsimilePreviewService.describe(
        session, tenant_scope=scope, document_id=42,
    )
    assert preview["signed_artifact_id"] == second.id
    assert preview["placement"] == audit.change_set["placement"]
    assert preview["placement"]["signature"] == next_placement.signature.model_dump()
