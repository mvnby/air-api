"""Prepare immutable PDF copies with a seller's signature and seal images."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    DocumentArtifact,
    DocumentFacsimileAsset,
    DocumentTemplateFacsimilePlacement,
    OrderDocument,
)
from models.tenancy import TenantScope
from modules.documents.application.artifact_helpers import artifact_row, stored_artifact
from modules.documents.infrastructure.artifact_storage import DocumentArtifactStorage, PrivateDocumentArtifactStorage
from services.private_attachment_storage_service import VariantScopedPrivateAttachmentStorage, get_private_attachment_storage


MM_TO_POINTS = 72 / 25.4
MAX_FACSIMILE_BYTES = 5 * 1024 * 1024


class FacsimilePdfError(ValueError):
    pass


class FacsimilePdfService:
    @classmethod
    async def prepare(cls, session: AsyncSession, *, tenant_scope: TenantScope, document_id: int,
                      artifact_storage: DocumentArtifactStorage) -> DocumentArtifact:
        document = (await session.execute(select(OrderDocument).where(
            OrderDocument.id == document_id, OrderDocument.tenant_id == tenant_scope.tenant_id
        ).with_for_update())).scalar_one_or_none()
        if document is None or not document.template_version_id or document.status not in {"issued", "sent", "signed"}:
            raise FacsimilePdfError("Подготовить PDF можно только для выпущенного нативного документа")
        existing = (await session.execute(select(DocumentArtifact).where(
            DocumentArtifact.order_document_id == document_id,
            DocumentArtifact.tenant_id == tenant_scope.tenant_id,
            DocumentArtifact.kind == "signed_pdf", DocumentArtifact.is_authoritative.is_(True),
        ))).scalar_one_or_none()
        if existing is not None:
            return existing
        placement = (await session.execute(select(DocumentTemplateFacsimilePlacement).where(
            DocumentTemplateFacsimilePlacement.template_version_id == document.template_version_id
        ))).scalar_one_or_none()
        if placement is None:
            raise FacsimilePdfError("Для версии шаблона не задано размещение подписи и печати")
        assets = list((await session.execute(select(DocumentFacsimileAsset).where(
            DocumentFacsimileAsset.tenant_id == tenant_scope.tenant_id,
            DocumentFacsimileAsset.legal_entity_id == document.legal_entity_id,
            DocumentFacsimileAsset.is_current.is_(True),
        ))).scalars())
        by_kind = {item.kind: item for item in assets}
        if set(by_kind) != {"signature", "seal"}:
            raise FacsimilePdfError("Загрузите текущие PNG подписи и печати для юридического лица")
        base = (await session.execute(select(DocumentArtifact).where(
            DocumentArtifact.order_document_id == document_id, DocumentArtifact.tenant_id == tenant_scope.tenant_id,
            DocumentArtifact.kind == "pdf", DocumentArtifact.is_authoritative.is_(True),
        ))).scalar_one_or_none()
        if base is None:
            raise FacsimilePdfError("У документа отсутствует выпускной PDF")
        base_storage = PrivateDocumentArtifactStorage(get_private_attachment_storage(base.provider))
        base_pdf = await base_storage.read(stored_artifact(base))
        signature = await _read_asset(by_kind["signature"])
        seal = await _read_asset(by_kind["seal"])
        content = _overlay(base_pdf, signature, seal, placement)
        stored = await artifact_storage.save(
            tenant_id=tenant_scope.tenant_id, document_id=document_id, kind="signed_pdf",
            filename=base.filename.removesuffix(".pdf") + "-с-подписью-и-печатью.pdf",
            content_type="application/pdf", content=content,
        )
        row = artifact_row(stored)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


def _overlay(pdf: bytes, signature: bytes, seal: bytes, placement) -> bytes:
    reader = PdfReader(BytesIO(pdf))
    index = placement.page_number - 1
    if index < 0 or index >= len(reader.pages):
        raise FacsimilePdfError("В шаблоне указана страница, которой нет в PDF")
    page = reader.pages[index]
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    layer = BytesIO()
    canvas = Canvas(layer, pagesize=(width, height))
    # API coordinates are measured from the top-left to match the document preview.
    for image, x, y, image_width in (
        (signature, placement.signature_x_mm, placement.signature_y_mm, placement.signature_width_mm),
        (seal, placement.seal_x_mm, placement.seal_y_mm, placement.seal_width_mm),
    ):
        try:
            reader_image = ImageReader(BytesIO(image))
            px_width, px_height = reader_image.getSize()
        except Exception as exc:
            raise FacsimilePdfError("PNG подписи или печати повреждён") from exc
        draw_width = image_width * MM_TO_POINTS
        draw_height = draw_width * px_height / px_width
        x_points = x * MM_TO_POINTS
        y_points = y * MM_TO_POINTS
        if x_points + draw_width > width or y_points + draw_height > height:
            raise FacsimilePdfError("Подпись или печать выходит за границы страницы PDF")
        canvas.drawImage(reader_image, x_points, height - y_points - draw_height,
                         width=draw_width, height=draw_height, mask="auto")
    canvas.save()
    layer.seek(0)
    page.merge_page(PdfReader(layer).pages[0])
    writer = PdfWriter()
    for source_page in reader.pages:
        writer.add_page(source_page)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


async def _read_asset(asset: DocumentFacsimileAsset) -> bytes:
    storage = get_private_attachment_storage(asset.provider)
    scoped = VariantScopedPrivateAttachmentStorage(storage, variant_scope="document-facsimiles")
    content = await scoped.read(asset.storage_key)
    if sha256(content).hexdigest() != asset.checksum_sha256 or len(content) != asset.size_bytes:
        raise FacsimilePdfError("PNG подписи или печати повреждён")
    return content
