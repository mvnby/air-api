"""Prepare immutable PDF copies from a checked visual placement."""

from __future__ import annotations

import asyncio
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.request_context import current_request_id
from models import DocumentArtifact, DocumentTemplateFacsimilePlacement, TenantAuditEvent
from models.tenancy import TenantScope
from modules.documents.application.artifact_helpers import artifact_row
from modules.documents.application.facsimile_context import (
    MAX_FACSIMILE_BYTES, MM_TO_POINTS, FacsimilePdfError, load_context,
    normalized_reader, read_asset, read_pdf,
)
from modules.documents.domain.facsimiles import FacsimileImagePlacement, FacsimilePdfPlacement, FacsimilePlacement
from modules.documents.infrastructure.artifact_storage import DocumentArtifactStorage

FACSIMILE_AUDIT_ACTION = "document.facsimile_pdf.prepared"


class FacsimilePdfService:
    @classmethod
    async def prepare(cls, session: AsyncSession, *, tenant_scope: TenantScope, document_id: int,
                      artifact_storage: DocumentArtifactStorage,
                      placement: FacsimilePdfPlacement | None = None,
                      actor_username: str | None = None,
                      actor_staff_user_id: int | None = None) -> DocumentArtifact:
        context = await load_context(session, tenant_scope=tenant_scope, document_id=document_id, for_update=True)
        if context.order.status == "closed":
            raise FacsimilePdfError("Заказ завершён: документы доступны только для просмотра и повторной отправки")
        if placement is None:
            if context.signed is not None:
                return context.signed
            legacy = (await session.execute(select(DocumentTemplateFacsimilePlacement).where(
                DocumentTemplateFacsimilePlacement.template_version_id == context.document.template_version_id
            ))).scalar_one_or_none()
            if legacy is None:
                raise FacsimilePdfError("Откройте предпросмотр документа и разместите подпись и печать на странице")
            positions = legacy_placement(legacy)
        else:
            if not context.can_save:
                raise FacsimilePdfError("PDF отправленного или подписанного документа менять нельзя. Создайте исправленную редакцию")
            signed_id = context.signed.id if context.signed else None
            if placement.expected_signed_artifact_id != signed_id:
                raise FacsimilePdfError("Копия PDF уже изменилась. Откройте предпросмотр заново")
            if placement.source_checksum_sha256 != context.base.checksum_sha256 or (
                placement.signature_asset_id != context.assets["signature"].id
                or placement.seal_asset_id != context.assets["seal"].id
            ):
                raise FacsimilePdfError("PDF, подпись или печать изменились. Откройте предпросмотр заново")
            positions = FacsimilePlacement(signature=placement.signature, seal=placement.seal)
        base_pdf = await read_pdf(context.base)
        signature = await read_asset(context.assets["signature"])
        seal = await read_asset(context.assets["seal"])
        content = await asyncio.to_thread(_overlay, base_pdf, signature, seal, positions)
        stored = await artifact_storage.save(
            tenant_id=tenant_scope.tenant_id, document_id=document_id, kind="signed_pdf",
            filename=context.base.filename.removesuffix(".pdf") + "-с-подписью-и-печатью.pdf",
            content_type="application/pdf", content=content,
        )
        previous_id = context.signed.id if context.signed else None
        if context.signed is not None:
            # Retain immutable previous bytes; only the current download selection changes.
            context.signed.is_authoritative = False
            session.add(context.signed)
            await session.flush()
        row = artifact_row(stored)
        session.add(row)
        if actor_username:
            session.add(TenantAuditEvent(
                tenant_id=tenant_scope.tenant_id, storefront_id=tenant_scope.storefront_id,
                actor_username=actor_username, actor_staff_user_id=actor_staff_user_id,
                action=FACSIMILE_AUDIT_ACTION, entity_type="order_document", entity_id=document_id,
                request_id=current_request_id(), change_set={
                    "artifact_id": row.id, "previous_artifact_id": previous_id,
                    "source_checksum_sha256": context.base.checksum_sha256,
                    "signature_asset_id": context.assets["signature"].id,
                    "seal_asset_id": context.assets["seal"].id,
                    "placement": positions.model_dump(),
                },
            ))
        await session.commit()
        await session.refresh(row)
        return row


def legacy_placement(placement) -> FacsimilePlacement:
    return FacsimilePlacement(**{
        kind: FacsimileImagePlacement(
            page_number=placement.page_number,
            x_mm=getattr(placement, f"{kind}_x_mm"),
            y_mm=getattr(placement, f"{kind}_y_mm"),
            width_mm=getattr(placement, f"{kind}_width_mm"),
        ) for kind in ("signature", "seal")
    })


def _overlay(pdf: bytes, signature: bytes, seal: bytes, placement) -> bytes:
    reader = normalized_reader(pdf)
    positions = placement if isinstance(placement, FacsimilePlacement) else legacy_placement(placement)
    layers: dict[int, Canvas] = {}
    buffers: dict[int, BytesIO] = {}
    for kind, image in (("signature", signature), ("seal", seal)):
        position = getattr(positions, kind)
        index = position.page_number - 1
        if index < 0 or index >= len(reader.pages):
            raise FacsimilePdfError("Указана страница, которой нет в PDF")
        page = reader.pages[index]
        width, height = float(page.cropbox.width), float(page.cropbox.height)
        try:
            reader_image = ImageReader(BytesIO(image))
            px_width, px_height = reader_image.getSize()
        except Exception as exc:
            raise FacsimilePdfError("PNG подписи или печати повреждён") from exc
        draw_width = position.width_mm * MM_TO_POINTS
        draw_height = draw_width * px_height / px_width
        x_points, y_points = position.x_mm * MM_TO_POINTS, position.y_mm * MM_TO_POINTS
        if x_points + draw_width > width + 0.001 or y_points + draw_height > height + 0.001:
            raise FacsimilePdfError("Подпись или печать выходит за границы страницы PDF")
        if index not in layers:
            buffers[index] = BytesIO()
            layers[index] = Canvas(buffers[index], pagesize=(width, height))
        layers[index].drawImage(reader_image, x_points, height - y_points - draw_height,
                               width=draw_width, height=draw_height, mask="auto")
    for index, canvas in layers.items():
        canvas.save()
        layer = PdfReader(BytesIO(buffers[index].getvalue())).pages[0]
        page = reader.pages[index]
        page.merge_translated_page(layer, float(page.cropbox.left), float(page.cropbox.bottom))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()
