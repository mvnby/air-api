from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.catalog_management import CatalogManagementFilters, CatalogManagementQuery, CatalogManagementSelection
from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context, require_manager_access, require_system_manager_tenant_scope
from api_contracts.catalog_bulk import CatalogBulkApplyRequest, CatalogBulkApplyResponse, CatalogBulkPreviewRequest, CatalogBulkPreviewResponse
from routers.manager_permission_policy import ManagerPermissionRoute
from services.catalog_bulk_service import CatalogBulkService, CatalogBulkConflict
from schemas import ManagerCatalogProductListResponse
from services.catalog_management_service import CatalogManagementService


router = APIRouter(prefix="/api/manager/catalog-management", tags=["manager-catalog-management"], route_class=ManagerPermissionRoute, dependencies=[Depends(require_manager_access), Depends(require_system_manager_tenant_scope)])


@router.post("/query", response_model=ManagerCatalogProductListResponse, operation_id="query_manager_catalog")
async def query_catalog(payload: CatalogManagementQuery, session: AsyncSession = Depends(get_session)):
    return await CatalogManagementService.query(session, payload)


@router.post("/selection", response_model=CatalogManagementSelection, operation_id="select_manager_catalog")
async def select_catalog(payload: CatalogManagementFilters, session: AsyncSession = Depends(get_session)):
    try:
        return await CatalogManagementService.selection(session, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _actor(auth: AuthenticatedUser) -> str:
    return f"{auth.tenant_id}:{auth.storefront_id}:{auth.staff_user_id or auth.username}"


@router.post("/bulk/preview", response_model=CatalogBulkPreviewResponse, operation_id="preview_manager_catalog_bulk")
async def preview_bulk(payload: CatalogBulkPreviewRequest, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(get_current_auth_context)):
    try:
        return await CatalogBulkService.preview(session, payload, _actor(auth))
    except CatalogBulkConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/bulk/apply", response_model=CatalogBulkApplyResponse, operation_id="apply_manager_catalog_bulk")
async def apply_bulk(payload: CatalogBulkApplyRequest, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(get_current_auth_context)):
    try:
        return await CatalogBulkService.apply(session, payload.token, _actor(auth))
    except CatalogBulkConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
