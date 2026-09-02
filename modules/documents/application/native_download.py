"""Download adapter for issued native document PDFs."""

from __future__ import annotations

from io import BytesIO
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from models import OrderDocument
from models.tenancy import TenantScope
from modules.documents.infrastructure.artifact_storage import (
    PrivateDocumentArtifactStorage,
)
from services.private_attachment_storage_service import get_private_attachment_storage

from .lifecycle_service import ManagedDocumentService


async def native_document_pdf_download(
    session: AsyncSession,
    *,
    tenant_scope: TenantScope,
    document: OrderDocument,
) -> tuple[BytesIO, str]:
    artifacts = await ManagedDocumentService.list_artifacts(
        session,
        tenant_scope=tenant_scope,
        document_id=int(document.id),
    )
    pdf_artifact = next((item for item in artifacts if item.kind == "pdf"), None)
    if pdf_artifact is None:
        raise ValueError("У документа отсутствует выпущенный PDF-файл")
    try:
        storage = PrivateDocumentArtifactStorage(
            get_private_attachment_storage(pdf_artifact.provider)
        )
        content = await storage.read(
            ManagedDocumentService.stored_artifact(pdf_artifact)
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ValueError("PDF-файл документа повреждён или недоступен") from exc
    return BytesIO(content), quote(pdf_artifact.filename)
