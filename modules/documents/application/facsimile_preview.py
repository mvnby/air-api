"""Read-only page previews using the same geometry and assets as the saved PDF."""

import asyncio
from io import BytesIO

from pypdf import PdfWriter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import DocumentTemplateFacsimilePlacement, TenantAuditEvent
from models.tenancy import TenantScope
from modules.documents.application.facsimile_context import (
    MM_TO_POINTS, FacsimilePdfError, load_context, normalized_reader, png_size, read_asset, read_pdf,
)
from modules.documents.application.facsimile_pdf import FACSIMILE_AUDIT_ACTION, legacy_placement
from modules.documents.domain.facsimiles import FacsimileImagePlacement, FacsimilePlacement

_render_slots = asyncio.Semaphore(2)


class FacsimilePreviewService:
    @classmethod
    async def describe(cls, session: AsyncSession, *, tenant_scope: TenantScope, document_id: int) -> dict:
        context = await load_context(session, tenant_scope=tenant_scope, document_id=document_id)
        content = await read_pdf(context.base)
        pages = await asyncio.to_thread(page_dimensions, content)
        assets = {}
        for kind, asset in context.assets.items():
            width, height = png_size(await read_asset(asset))
            assets[kind] = {"asset_id": asset.id, "width_px": width, "height_px": height}
        placement = None
        if context.signed:
            audit = (await session.execute(select(TenantAuditEvent).where(
                TenantAuditEvent.tenant_id == tenant_scope.tenant_id,
                TenantAuditEvent.storefront_id == tenant_scope.storefront_id,
                TenantAuditEvent.entity_type == "order_document",
                TenantAuditEvent.entity_id == document_id,
                TenantAuditEvent.action == FACSIMILE_AUDIT_ACTION,
            ).order_by(TenantAuditEvent.id.desc()).limit(1))).scalar_one_or_none()
            if audit and audit.change_set.get("artifact_id") == context.signed.id:
                placement = FacsimilePlacement.model_validate(audit.change_set["placement"])
        if placement is None:
            legacy = (await session.execute(select(DocumentTemplateFacsimilePlacement).where(
                DocumentTemplateFacsimilePlacement.template_version_id == context.document.template_version_id
            ))).scalar_one_or_none()
            if legacy is not None:
                placement = legacy_placement(legacy)
        placement = fit_initial_placement(placement, pages, assets)
        return {
            "document_id": document_id, "source_checksum_sha256": context.base.checksum_sha256,
            "signed_artifact_id": context.signed.id if context.signed else None,
            "can_save": context.can_save, "pages": pages, **assets,
            "placement": placement.model_dump(),
        }

    @classmethod
    async def page(cls, session: AsyncSession, *, tenant_scope: TenantScope,
                   document_id: int, page_number: int) -> bytes:
        context = await load_context(session, tenant_scope=tenant_scope, document_id=document_id)
        content = await read_pdf(context.base)
        normalized = await asyncio.to_thread(single_page_pdf, content, page_number)
        async with _render_slots:
            try:
                process = await asyncio.create_subprocess_exec(
                    "pdftoppm", "-singlefile", "-scale-to", "2400", "-png", "-cropbox", "-",
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as exc:
                raise FacsimilePdfError("Предпросмотр PDF временно недоступен") from exc
            try:
                output, _ = await asyncio.wait_for(process.communicate(normalized), timeout=20)
            except (TimeoutError, asyncio.CancelledError) as exc:
                if process.returncode is None:
                    process.kill()
                await process.communicate()
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise FacsimilePdfError("Предпросмотр не успел загрузиться. Попробуйте ещё раз") from exc
            if process.returncode != 0 or not output.startswith(b"\x89PNG\r\n\x1a\n"):
                raise FacsimilePdfError("Не удалось построить предпросмотр PDF")
            return output

    @classmethod
    async def asset(cls, session: AsyncSession, *, tenant_scope: TenantScope,
                    document_id: int, asset_id: str) -> bytes:
        context = await load_context(session, tenant_scope=tenant_scope, document_id=document_id)
        asset = next((item for item in context.assets.values() if item.id == asset_id), None)
        if asset is None:
            raise FacsimilePdfError("Подпись или печать изменилась. Откройте предпросмотр заново")
        return await read_asset(asset)


def page_dimensions(content: bytes) -> list[dict]:
    return [{"page_number": index + 1,
             "width_mm": float(page.cropbox.width) / MM_TO_POINTS,
             "height_mm": float(page.cropbox.height) / MM_TO_POINTS}
            for index, page in enumerate(normalized_reader(content).pages)]


def single_page_pdf(content: bytes, page_number: int) -> bytes:
    reader = normalized_reader(content)
    if not 1 <= page_number <= len(reader.pages):
        raise FacsimilePdfError("Указана страница, которой нет в PDF")
    writer = PdfWriter()
    writer.add_page(reader.pages[page_number - 1])
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


def fit_initial_placement(placement: FacsimilePlacement | None, pages: list[dict], assets: dict) -> FacsimilePlacement:
    positions = {}
    for kind, default_width, default_x in (("signature", 45, 20), ("seal", 35, 75)):
        proposed = getattr(placement, kind) if placement is not None else None
        page_number = proposed.page_number if proposed and proposed.page_number <= len(pages) else len(pages)
        page = pages[page_number - 1]
        ratio = assets[kind]["height_px"] / assets[kind]["width_px"]
        width = min(proposed.width_mm if proposed else default_width,
                    page["width_mm"], page["height_mm"] / ratio)
        x = min(proposed.x_mm if proposed else default_x, page["width_mm"] - width)
        y = min(proposed.y_mm if proposed else max(0, page["height_mm"] - 65), page["height_mm"] - width * ratio)
        positions[kind] = FacsimileImagePlacement(
            page_number=page_number, x_mm=max(0, x), y_mm=max(0, y), width_mm=width,
        )
    return FacsimilePlacement(**positions)
