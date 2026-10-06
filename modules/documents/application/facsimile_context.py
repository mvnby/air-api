"""Tenant-bound inputs shared by visual preview and signed-copy preparation."""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from math import isfinite

from PIL import Image
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import DocumentArtifact, DocumentFacsimileAsset, Order, OrderDocument, OrderStatus
from models.tenancy import TenantScope
from modules.documents.application.artifact_helpers import stored_artifact
from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
from services.private_attachment_storage_service import VariantScopedPrivateAttachmentStorage, get_private_attachment_storage

MM_TO_POINTS = 72 / 25.4
MAX_FACSIMILE_BYTES = 5 * 1024 * 1024
MAX_PDF_BYTES = 40 * 1024 * 1024


class FacsimilePdfError(ValueError):
    pass


@dataclass
class FacsimileContext:
    document: OrderDocument
    order: Order
    base: DocumentArtifact
    signed: DocumentArtifact | None
    assets: dict[str, DocumentFacsimileAsset]

    @property
    def can_save(self) -> bool:
        return self.order.status != OrderStatus.CLOSED and (
            self.signed is None or self.document.status == "issued"
        )


async def load_context(session: AsyncSession, *, tenant_scope: TenantScope,
                       document_id: int, for_update: bool = False) -> FacsimileContext:
    statement = select(OrderDocument, Order).join(Order, Order.id == OrderDocument.order_id).where(
        OrderDocument.id == document_id, OrderDocument.tenant_id == tenant_scope.tenant_id,
        Order.tenant_id == tenant_scope.tenant_id, Order.storefront_id == tenant_scope.storefront_id,
    )
    if for_update:
        statement = statement.with_for_update()
    found = (await session.execute(statement)).first()
    if found is None:
        raise FacsimilePdfError("Документ не найден")
    document, order = found
    if not document.template_version_id or document.status not in {"issued", "sent", "signed"}:
        raise FacsimilePdfError("Подготовить PDF можно только для выпущенного нативного документа")
    artifacts = list((await session.execute(select(DocumentArtifact).where(
        DocumentArtifact.order_document_id == document_id,
        DocumentArtifact.tenant_id == tenant_scope.tenant_id,
        DocumentArtifact.kind.in_(["pdf", "signed_pdf"]), DocumentArtifact.is_authoritative.is_(True),
    ))).scalars())
    by_kind = {row.kind: row for row in artifacts}
    if "pdf" not in by_kind:
        raise FacsimilePdfError("У документа отсутствует выпускной PDF")
    assets = list((await session.execute(select(DocumentFacsimileAsset).where(
        DocumentFacsimileAsset.tenant_id == tenant_scope.tenant_id,
        DocumentFacsimileAsset.legal_entity_id == document.legal_entity_id,
        DocumentFacsimileAsset.is_current.is_(True),
    ))).scalars())
    asset_by_kind = {item.kind: item for item in assets}
    if set(asset_by_kind) != {"signature", "seal"}:
        raise FacsimilePdfError("В настройках организации загрузите PNG подписи и печати")
    return FacsimileContext(document, order, by_kind["pdf"], by_kind.get("signed_pdf"), asset_by_kind)


async def read_pdf(artifact: DocumentArtifact) -> bytes:
    if artifact.size_bytes > MAX_PDF_BYTES:
        raise FacsimilePdfError("Для предпросмотра PDF должен быть не больше 40 МБ")
    try:
        storage = PrivateDocumentArtifactStorage(get_private_attachment_storage(artifact.provider))
        return await storage.read(stored_artifact(artifact))
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise FacsimilePdfError("Выпускной PDF повреждён или недоступен") from exc


async def read_asset(asset: DocumentFacsimileAsset) -> bytes:
    try:
        storage = get_private_attachment_storage(asset.provider)
        scoped = VariantScopedPrivateAttachmentStorage(storage, variant_scope="document-facsimiles")
        content = await scoped.read(asset.storage_key)
        if sha256(content).hexdigest() != asset.checksum_sha256 or len(content) != asset.size_bytes:
            raise ValueError()
        png_size(content)
        return content
    except (FileNotFoundError, TypeError, ValueError, OSError) as exc:
        raise FacsimilePdfError("PNG подписи или печати повреждён или недоступен") from exc


def png_size(content: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(content)) as image:
        if image.format != "PNG" or image.width < 1 or image.height < 1:
            raise FacsimilePdfError("PNG подписи или печати повреждён")
        return image.size


def normalized_reader(content: bytes) -> PdfReader:
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
            raise ValueError()
        for page in reader.pages:
            # Preview and saved overlays use the same visual orientation and crop box.
            if page.rotation:
                page.transfer_rotation_to_content()
            width, height = float(page.cropbox.width), float(page.cropbox.height)
            if not all(isfinite(value) and value > 0 for value in (width, height)):
                raise ValueError()
            if max(width, height) / MM_TO_POINTS > 1000:
                raise ValueError()
        return reader
    except Exception as exc:
        raise FacsimilePdfError("Нужен корректный незашифрованный PDF до 100 страниц") from exc
