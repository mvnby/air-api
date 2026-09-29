from __future__ import annotations

from hashlib import sha256
from io import BytesIO

from fastapi import APIRouter, Depends, File, UploadFile
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from models import DocumentFacsimileAsset, DocumentLegalEntity, DocumentTemplate, DocumentTemplateFacsimilePlacement, DocumentTemplateVersion
from modules.documents.application.facsimile_pdf import FacsimilePdfError, FacsimilePdfService, MAX_FACSIMILE_BYTES
from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
from routers.manager_permission_policy import ManagerPermissionRoute
from routers.manager_operation_ids import (
    GET_MANAGER_DOCUMENT_FACSIMILE_PLACEMENT,
    PREPARE_MANAGER_DOCUMENT_FACSIMILE_PDF,
    UPLOAD_MANAGER_DOCUMENT_FACSIMILE,
    UPSERT_MANAGER_DOCUMENT_FACSIMILE_PLACEMENT,
)
from services.private_attachment_storage_service import VariantScopedPrivateAttachmentStorage, get_private_attachment_storage
from .schemas import DocumentFacsimilePlacementItem, DocumentFacsimilePlacementPayload

router = APIRouter(prefix="/api/manager/document-system", tags=["manager-document-system"], dependencies=[Depends(require_manager_access)], route_class=ManagerPermissionRoute)
MAX_FACSIMILE_PIXELS = 20_000_000


@router.post("/legal-entities/{legal_entity_id}/facsimiles/{kind}", operation_id=UPLOAD_MANAGER_DOCUMENT_FACSIMILE)
async def upload_facsimile(legal_entity_id: int, kind: str, file: UploadFile = File(...), session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access)):
    if kind not in {"signature", "seal"}:
        raise manager_http_error(400, "upload_manager_document_facsimile", "document_facsimile_kind_invalid", "Допустимы только signature и seal")
    entity = (await session.execute(select(DocumentLegalEntity).where(DocumentLegalEntity.id == legal_entity_id, DocumentLegalEntity.tenant_id == auth.tenant_id))).scalar_one_or_none()
    if entity is None:
        raise manager_http_error(404, "upload_manager_document_facsimile", "document_legal_entity_not_found", "Юридическое лицо не найдено")
    content = await file.read(MAX_FACSIMILE_BYTES + 1)
    if len(content) > MAX_FACSIMILE_BYTES or not content:
        raise manager_http_error(400, "upload_manager_document_facsimile", "document_facsimile_file_invalid", "PNG не должен быть пустым или больше 5 МБ")
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format != "PNG" or image.width < 1 or image.height < 1:
                raise ValueError()
            if image.width * image.height > MAX_FACSIMILE_PIXELS:
                raise ValueError()
            image.load()
    except Exception:
        raise manager_http_error(400, "upload_manager_document_facsimile", "document_facsimile_file_invalid", "Загрузите корректный PNG до 20 млн пикселей")
    storage = get_private_attachment_storage()
    stored = await VariantScopedPrivateAttachmentStorage(storage, variant_scope="document-facsimiles").save(content=content, content_hash=sha256(content).hexdigest(), extension="png", content_type="image/png", variant=f"tenant-{auth.tenant_id}-legal-entity-{legal_entity_id}-{kind}")
    await session.execute(DocumentFacsimileAsset.__table__.update().where(DocumentFacsimileAsset.tenant_id == auth.tenant_id, DocumentFacsimileAsset.legal_entity_id == legal_entity_id, DocumentFacsimileAsset.kind == kind, DocumentFacsimileAsset.is_current.is_(True)).values(is_current=False))
    row = DocumentFacsimileAsset(tenant_id=auth.tenant_id, legal_entity_id=legal_entity_id, kind=kind, provider=stored.provider, storage_key=stored.storage_key, checksum_sha256=sha256(content).hexdigest(), size_bytes=len(content))
    session.add(row); await session.commit(); await session.refresh(row)
    return {"id": row.id, "kind": row.kind, "checksum_sha256": row.checksum_sha256}


@router.post("/documents/{document_id}/facsimile-pdf", operation_id=PREPARE_MANAGER_DOCUMENT_FACSIMILE_PDF)
async def prepare_facsimile_pdf(document_id: int, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access)):
    try:
        row = await FacsimilePdfService.prepare(session, tenant_scope=auth.tenant_scope(), document_id=document_id, artifact_storage=PrivateDocumentArtifactStorage(get_private_attachment_storage()))
    except FacsimilePdfError as exc:
        raise manager_http_error(409, "prepare_manager_document_facsimile_pdf", "document_facsimile_pdf_unavailable", str(exc)) from exc
    return {"id": row.id, "kind": row.kind, "filename": row.filename}


@router.put("/templates/{template_id}/versions/{version_id}/facsimile-placement", response_model=DocumentFacsimilePlacementItem, operation_id=UPSERT_MANAGER_DOCUMENT_FACSIMILE_PLACEMENT)
async def upsert_placement(template_id: int, version_id: int, payload: DocumentFacsimilePlacementPayload, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access)):
    version = (await session.execute(select(DocumentTemplateVersion).join(DocumentTemplate).where(
        DocumentTemplateVersion.id == version_id, DocumentTemplateVersion.template_id == template_id,
        DocumentTemplate.tenant_id == auth.tenant_id,
    ))).scalar_one_or_none()
    if version is None:
        raise manager_http_error(404, "upsert_manager_document_facsimile_placement", "native_template_version_not_found", "Версия шаблона не найдена")
    row = (await session.execute(select(DocumentTemplateFacsimilePlacement).where(DocumentTemplateFacsimilePlacement.template_version_id == version_id))).scalar_one_or_none()
    values = payload.model_dump()
    if row is None:
        row = DocumentTemplateFacsimilePlacement(template_version_id=version_id, **values)
        session.add(row)
    else:
        for key, value in values.items(): setattr(row, key, value)
        session.add(row)
    await session.commit(); await session.refresh(row)
    return DocumentFacsimilePlacementItem(template_version_id=version_id, **values)


@router.get("/templates/{template_id}/versions/{version_id}/facsimile-placement", response_model=DocumentFacsimilePlacementItem, operation_id=GET_MANAGER_DOCUMENT_FACSIMILE_PLACEMENT)
async def get_placement(template_id: int, version_id: int, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access)):
    row = (await session.execute(select(DocumentTemplateFacsimilePlacement).join(DocumentTemplateVersion).join(DocumentTemplate).where(
        DocumentTemplateFacsimilePlacement.template_version_id == version_id, DocumentTemplateVersion.template_id == template_id,
        DocumentTemplate.tenant_id == auth.tenant_id,
    ))).scalar_one_or_none()
    if row is None:
        raise manager_http_error(404, "get_manager_document_facsimile_placement", "document_facsimile_placement_not_found", "Размещение для версии шаблона не задано")
    return DocumentFacsimilePlacementItem(template_version_id=version_id, page_number=row.page_number, signature_x_mm=row.signature_x_mm, signature_y_mm=row.signature_y_mm, signature_width_mm=row.signature_width_mm, seal_x_mm=row.seal_x_mm, seal_y_mm=row.seal_y_mm, seal_width_mm=row.seal_width_mm)
