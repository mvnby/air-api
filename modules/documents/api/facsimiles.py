from __future__ import annotations

from hashlib import sha256
from io import BytesIO

from fastapi import APIRouter, Depends, File, UploadFile, Response, Path
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from models import DocumentFacsimileAsset, DocumentLegalEntity, DocumentTemplate, DocumentTemplateFacsimilePlacement, DocumentTemplateVersion
from modules.documents.application.facsimile_pdf import FacsimilePdfError, FacsimilePdfService, MAX_FACSIMILE_BYTES
from modules.documents.application.facsimile_preview import FacsimilePreviewService
from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
from routers.manager_permission_policy import ManagerPermissionRoute
from routers.manager_operation_ids import (
    GET_MANAGER_DOCUMENT_FACSIMILE_PLACEMENT,
    PREPARE_MANAGER_DOCUMENT_FACSIMILE_PDF,
    GET_MANAGER_DOCUMENT_FACSIMILE_PREVIEW,
    GET_MANAGER_DOCUMENT_FACSIMILE_PREVIEW_PAGE,
    GET_MANAGER_DOCUMENT_FACSIMILE_PREVIEW_ASSET,
    UPLOAD_MANAGER_DOCUMENT_FACSIMILE,
    UPSERT_MANAGER_DOCUMENT_FACSIMILE_PLACEMENT,
)
from services.private_attachment_storage_service import VariantScopedPrivateAttachmentStorage, get_private_attachment_storage
from .schemas import DocumentFacsimilePlacementItem, DocumentFacsimilePlacementPayload
from .facsimile_schemas import DocumentFacsimilePdfPayload, DocumentFacsimilePreviewResponse

router = APIRouter(prefix="/api/manager/document-system", tags=["manager-document-system"], dependencies=[Depends(require_manager_access)], route_class=ManagerPermissionRoute)
MAX_FACSIMILE_PIXELS = 20_000_000


@router.post("/legal-entities/{legal_entity_id}/facsimiles/{kind}", operation_id=UPLOAD_MANAGER_DOCUMENT_FACSIMILE)
async def upload_facsimile(legal_entity_id: int, kind: str, file: UploadFile = File(...), session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access)):
    """
    Upload a private PNG signature or seal for a legal entity in the current tenant.
    Requires owner/admin access. Only signature/seal is accepted; file must be nonempty, at
    most 5 MB and 20 million pixels (400 otherwise); missing entity returns 404. Makes a new
    asset current without rewriting already prepared PDFs.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    if kind not in {"signature", "seal"}:
        raise manager_http_error(status_code=400, endpoint=UPLOAD_MANAGER_DOCUMENT_FACSIMILE, error_code="document_facsimile_kind_invalid", message="Допустимы только signature и seal")
    entity = (await session.execute(select(DocumentLegalEntity).where(DocumentLegalEntity.id == legal_entity_id, DocumentLegalEntity.tenant_id == auth.tenant_id))).scalar_one_or_none()
    if entity is None:
        raise manager_http_error(status_code=404, endpoint=UPLOAD_MANAGER_DOCUMENT_FACSIMILE, error_code="document_legal_entity_not_found", message="Юридическое лицо не найдено")
    content = await file.read(MAX_FACSIMILE_BYTES + 1)
    if len(content) > MAX_FACSIMILE_BYTES or not content:
        raise manager_http_error(status_code=400, endpoint=UPLOAD_MANAGER_DOCUMENT_FACSIMILE, error_code="document_facsimile_file_invalid", message="PNG не должен быть пустым или больше 5 МБ")
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format != "PNG" or image.width < 1 or image.height < 1:
                raise ValueError()
            if image.width * image.height > MAX_FACSIMILE_PIXELS:
                raise ValueError()
            image.load()
    except Exception:
        raise manager_http_error(status_code=400, endpoint=UPLOAD_MANAGER_DOCUMENT_FACSIMILE, error_code="document_facsimile_file_invalid", message="Загрузите корректный PNG до 20 млн пикселей")
    storage = get_private_attachment_storage()
    stored = await VariantScopedPrivateAttachmentStorage(storage, variant_scope="document-facsimiles").save(content=content, content_hash=sha256(content).hexdigest(), extension="png", content_type="image/png", variant=f"tenant-{auth.tenant_id}-legal-entity-{legal_entity_id}-{kind}")
    await session.execute(DocumentFacsimileAsset.__table__.update().where(DocumentFacsimileAsset.tenant_id == auth.tenant_id, DocumentFacsimileAsset.legal_entity_id == legal_entity_id, DocumentFacsimileAsset.kind == kind, DocumentFacsimileAsset.is_current.is_(True)).values(is_current=False))
    row = DocumentFacsimileAsset(tenant_id=auth.tenant_id, legal_entity_id=legal_entity_id, kind=kind, provider=stored.provider, storage_key=stored.storage_key, checksum_sha256=sha256(content).hexdigest(), size_bytes=len(content))
    session.add(row); await session.commit(); await session.refresh(row)
    return {"id": row.id, "kind": row.kind, "checksum_sha256": row.checksum_sha256}


@router.post("/documents/{document_id}/facsimile-pdf", operation_id=PREPARE_MANAGER_DOCUMENT_FACSIMILE_PDF)
async def prepare_facsimile_pdf(document_id: int, payload: DocumentFacsimilePdfPayload | None = None,
                                session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access)):
    """
    Prepare a separate authoritative signed_pdf artifact for a scoped managed document using
    signature/seal PNGs and placement. The issued source PDF and earlier copies stay
    immutable. Submitted placement checks source checksum, current assets and
    expected_signed_artifact_id to prevent replacing a changed copy;
    stale/missing/ineligible context returns 409. Sent/signed or closed-order copies cannot
    be changed; without placement an existing prepared copy can be reused. This is
    preparation, not email delivery or cryptographic signing. See the [document lifecycle
    contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        row = await FacsimilePdfService.prepare(
            session, tenant_scope=auth.tenant_scope(), document_id=document_id,
            artifact_storage=PrivateDocumentArtifactStorage(get_private_attachment_storage()),
            placement=payload, actor_username=auth.username, actor_staff_user_id=auth.staff_user_id,
        )
    except FacsimilePdfError as exc:
        raise manager_http_error(status_code=409, endpoint=PREPARE_MANAGER_DOCUMENT_FACSIMILE_PDF, error_code="document_facsimile_pdf_unavailable", message=str(exc)) from exc
    return {"id": row.id, "kind": row.kind, "filename": row.filename}


@router.get("/documents/{document_id}/facsimile-preview", response_model=DocumentFacsimilePreviewResponse,
            operation_id=GET_MANAGER_DOCUMENT_FACSIMILE_PREVIEW)
async def get_facsimile_preview(document_id: int, response: Response, session: AsyncSession = Depends(get_session),
                               auth: AuthenticatedUser = Depends(require_manager_access)):
    """
    Read private/no-store PDF page geometry, current signature/seal assets and
    expected-state metadata for the scoped facsimile editor. Does not prepare a signed PDF.
    Unavailable source/document/assets return 409; obtain fresh metadata before saving
    placement.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return await FacsimilePreviewService.describe(session, tenant_scope=auth.tenant_scope(), document_id=document_id)
    except FacsimilePdfError as exc:
        raise _preview_error(GET_MANAGER_DOCUMENT_FACSIMILE_PREVIEW, exc) from exc


@router.get("/documents/{document_id}/facsimile-preview/pages/{page_number}", response_class=Response,
            responses={200: {"content": {"image/png": {}}}}, operation_id=GET_MANAGER_DOCUMENT_FACSIMILE_PREVIEW_PAGE)
async def get_facsimile_preview_page(document_id: int, page_number: int = Path(ge=1, le=100),
                                    session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access)):
    """
    Render one authenticated scoped PDF preview page as private/no-store PNG, with
    page_number limited to 1–100. Unavailable document/page/render context returns 409. Does
    not issue or change the PDF.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        content = await FacsimilePreviewService.page(
            session, tenant_scope=auth.tenant_scope(), document_id=document_id, page_number=page_number,
        )
    except FacsimilePdfError as exc:
        raise _preview_error(GET_MANAGER_DOCUMENT_FACSIMILE_PREVIEW_PAGE, exc) from exc
    return _private_png(content)


@router.get("/documents/{document_id}/facsimile-preview/assets/{asset_id}", response_class=Response,
            responses={200: {"content": {"image/png": {}}}}, operation_id=GET_MANAGER_DOCUMENT_FACSIMILE_PREVIEW_ASSET)
async def get_facsimile_preview_asset(document_id: int, asset_id: str = Path(pattern=r"^[0-9a-f]{32}$"),
                                     session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access)):
    """
    Read an authenticated private/no-store PNG signature/seal asset belonging to this scoped
    document’s legal entity. asset_id is constrained to the asset identifier format.
    Unavailable or mismatched asset context returns 409; this is not a public media
    endpoint.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        content = await FacsimilePreviewService.asset(
            session, tenant_scope=auth.tenant_scope(), document_id=document_id, asset_id=asset_id,
        )
    except FacsimilePdfError as exc:
        raise _preview_error(GET_MANAGER_DOCUMENT_FACSIMILE_PREVIEW_ASSET, exc) from exc
    return _private_png(content)


def _preview_error(endpoint: str, exc: FacsimilePdfError):
    return manager_http_error(status_code=409, endpoint=endpoint,
                              error_code="document_facsimile_preview_unavailable", message=str(exc))


def _private_png(content: bytes) -> Response:
    return Response(content=content, media_type="image/png", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.put("/templates/{template_id}/versions/{version_id}/facsimile-placement", response_model=DocumentFacsimilePlacementItem, operation_id=UPSERT_MANAGER_DOCUMENT_FACSIMILE_PLACEMENT)
async def upsert_placement(template_id: int, version_id: int, payload: DocumentFacsimilePlacementPayload, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access)):
    """
    Set legacy facsimile placement defaults for a native template/version owned by the
    current tenant. Requires owner/admin access. Missing or inaccessible version returns
    404. Updates placement defaults only; previously generated PDFs are not rewritten and
    document-specific placement is saved by facsimile-pdf.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    version = (await session.execute(select(DocumentTemplateVersion).join(DocumentTemplate).where(
        DocumentTemplateVersion.id == version_id, DocumentTemplateVersion.template_id == template_id,
        DocumentTemplate.tenant_id == auth.tenant_id,
    ))).scalar_one_or_none()
    if version is None:
        raise manager_http_error(status_code=404, endpoint=UPSERT_MANAGER_DOCUMENT_FACSIMILE_PLACEMENT, error_code="native_template_version_not_found", message="Версия шаблона не найдена")
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
    """
    Read legacy facsimile placement defaults for a current-tenant native template/version.
    Requires owner/admin access. Missing/inaccessible or unconfigured placement returns 404.
    This does not return the current document-specific prepared PDF placement.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    row = (await session.execute(select(DocumentTemplateFacsimilePlacement).join(DocumentTemplateVersion).join(DocumentTemplate).where(
        DocumentTemplateFacsimilePlacement.template_version_id == version_id, DocumentTemplateVersion.template_id == template_id,
        DocumentTemplate.tenant_id == auth.tenant_id,
    ))).scalar_one_or_none()
    if row is None:
        raise manager_http_error(status_code=404, endpoint=GET_MANAGER_DOCUMENT_FACSIMILE_PLACEMENT, error_code="document_facsimile_placement_not_found", message="Размещение для версии шаблона не задано")
    return DocumentFacsimilePlacementItem(template_version_id=version_id, page_number=row.page_number, signature_x_mm=row.signature_x_mm, signature_y_mm=row.signature_y_mm, signature_width_mm=row.signature_width_mm, seal_x_mm=row.seal_x_mm, seal_y_mm=row.seal_y_mm, seal_width_mm=row.seal_width_mm)
