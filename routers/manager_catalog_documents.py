from fastapi import APIRouter, Depends, File, Path, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_catalog_username
from routers.manager_operation_ids import (
    GET_MANAGER_CATALOG_DOCUMENTS,
    REPLACE_MANAGER_CATALOG_DOCUMENTS,
    UPLOAD_MANAGER_CATALOG_DOCUMENT,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_catalog_documents import (
    CatalogDocumentsReplacePayload,
    CatalogDocumentTarget,
    CatalogDocumentUploadResponse,
    CatalogDocumentWorkspace,
)
from services.catalog_document_service import CatalogDocumentService
from services.catalog_document_upload import upload_catalog_document


router = APIRouter(
    prefix="/api/manager/catalog-documents",
    tags=["manager catalog documents"],
    dependencies=[Depends(get_current_catalog_username)],
    route_class=ManagerPermissionRoute,
)


@router.get("/{target_type}/{target_id}", response_model=CatalogDocumentWorkspace, operation_id=GET_MANAGER_CATALOG_DOCUMENTS)
async def get_manager_catalog_documents(
    target_type: CatalogDocumentTarget,
    target_id: int = Path(ge=1),
    session: AsyncSession = Depends(get_session),
):
    """Read own, inherited and effective shared catalog reference documents.

    Requires platform-owner or delegated catalog.master.edit permission. Internal research sources are included;
    these are not order documents. Inherited documents preserve their original brand
    or series owner and are edited there. Missing target returns 404. No content is
    fetched from external URLs. Effective references deduplicate identical canonical
    URLs, preferring the product, then series, then brand; separate URLs are retained.
    """
    return await CatalogDocumentService.get_workspace(session, target_type=target_type, target_id=target_id)


@router.put("/{target_type}/{target_id}", response_model=CatalogDocumentWorkspace, operation_id=REPLACE_MANAGER_CATALOG_DOCUMENTS)
async def replace_manager_catalog_documents(
    target_type: CatalogDocumentTarget,
    payload: CatalogDocumentsReplacePayload,
    target_id: int = Path(ge=1),
    session: AsyncSession = Depends(get_session),
):
    """Replace up to 100 own technical/reference documents in the shared catalog.

    Requires platform-owner or delegated catalog.master.edit permission. An empty set
    removes only the target's own references; inherited files remain attached to their
    owner. References default to public and inherited; set visibility=internal for
    staff/AI research and inherit_to_products=false for owner-only materials. Missing
    target returns 404; duplicate URLs return 400. Metadata and catalog invalidation
    commit together; an unchanged ordered set does not bump the catalog revision.
    No external URLs are fetched and no stored files are physically deleted.
    """
    return await CatalogDocumentService.replace_documents(session, target_type=target_type, target_id=target_id, payload=payload)


@router.post("/{target_type}/{target_id}/upload", response_model=CatalogDocumentUploadResponse, operation_id=UPLOAD_MANAGER_CATALOG_DOCUMENT)
async def upload_manager_catalog_document(
    target_type: CatalogDocumentTarget,
    target_id: int = Path(ge=1),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Upload a public PDF/DOCX (up to 25 MiB) and return its immutable material URL.

    Requires platform-owner or delegated catalog.master.edit permission. Missing target
    returns 404; invalid type/content returns 400, oversized input 413. Uses the existing
    public media store under a dedicated catalog-documents namespace, separate from
    business documents. The returned URL is attached by the subsequent whole-set PUT;
    upload alone does not change the catalog. Upload only materials approved for public
    hosting; private research documents must be attached as links to their source.
    """
    await CatalogDocumentService.require_target(session, target_type=target_type, target_id=target_id)
    return await upload_catalog_document(file)
