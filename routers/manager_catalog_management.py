from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.catalog_management import CatalogManagementFilters, CatalogManagementQuery, CatalogManagementSelection
from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context, require_catalog_master_edit
from api_contracts.catalog_bulk import CatalogBulkApplyRequest, CatalogBulkApplyResponse, CatalogBulkPreviewRequest, CatalogBulkPreviewResponse
from routers.manager_permission_policy import ManagerPermissionRoute
from services.catalog_bulk_service import CatalogBulkService, CatalogBulkConflict
from schemas import ManagerCatalogProductListResponse
from services.catalog_management_service import CatalogManagementService
from services.catalog_access_service import CatalogAccessService, CatalogCommercialAccessDenied


router = APIRouter(prefix="/api/manager/catalog-management", tags=["manager-catalog-management"], route_class=ManagerPermissionRoute, dependencies=[Depends(require_catalog_master_edit)])


@router.post("/query", response_model=ManagerCatalogProductListResponse, operation_id="query_manager_catalog")
async def query_catalog(payload: CatalogManagementQuery, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_catalog_master_edit)):
    """
    Query the shared catalog-management workspace using its combined technical, publication,
    supplier and missing-data filters. Filtering precedes pagination. Supplier means a
    mapped active supplier offer, not ownership of the product; results include draft and
    orderable products.

    Access and scope: shared catalog operations require an explicit platform-owner or
    delegated catalog permission, independent of company membership. Destructive operations
    require catalog.master.delete; imports, bulk tools and procurement remain platform-owner-only.
    This operates on the shared platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [catalog
    workspace](https://github.com/mvnby/air-api/blob/main/docs/catalog-management-workspace.md).
    """
    try:
        CatalogAccessService.validate_filters(payload.filters, is_platform_owner=auth.is_platform_owner)
    except CatalogCommercialAccessDenied as exc:
        raise HTTPException(403, str(exc)) from exc
    result = await CatalogManagementService.query(session, payload)
    return CatalogAccessService.project_product(result, is_platform_owner=auth.is_platform_owner)


@router.post("/selection", response_model=CatalogManagementSelection, operation_id="select_manager_catalog")
async def select_catalog(payload: CatalogManagementFilters, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_catalog_master_edit)):
    """
    Resolve the same workspace filters to a bounded full selection of product IDs without
    pagination. More than 500 matches returns 400 rather than a truncated selection. The
    returned IDs are a snapshot; later preview/apply validates their current availability.

    Access and scope: shared catalog operations require an explicit platform-owner or
    delegated catalog permission, independent of company membership. Destructive operations
    require catalog.master.delete; imports, bulk tools and procurement remain platform-owner-only.
    This operates on the shared platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [catalog
    workspace](https://github.com/mvnby/air-api/blob/main/docs/catalog-management-workspace.md).
    """
    try:
        CatalogAccessService.validate_filters(payload, is_platform_owner=auth.is_platform_owner)
        return await CatalogManagementService.selection(session, payload)
    except CatalogCommercialAccessDenied as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _actor(auth: AuthenticatedUser) -> str:
    return f"{auth.tenant_id}:{auth.storefront_id}:{auth.staff_user_id or auth.username}"


@router.post("/bulk/preview", response_model=CatalogBulkPreviewResponse, operation_id="preview_manager_catalog_bulk")
async def preview_bulk(payload: CatalogBulkPreviewRequest, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(get_current_auth_context)):
    """
    Calculate before/after results for selected products inside a transaction that is rolled
    back. No catalog changes are saved. Returns a signed token valid for 900 seconds, bound
    to the tenant/storefront/actor, selection, change and product fingerprints. Invalid
    choices return 400; unavailable products return 409. Apply must use this token.

    Access and scope: shared catalog operations require an explicit platform-owner or
    delegated catalog permission, independent of company membership. Destructive operations
    require catalog.master.delete; imports, bulk tools and procurement remain platform-owner-only.
    This operates on the shared platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [catalog
    workspace](https://github.com/mvnby/air-api/blob/main/docs/catalog-management-workspace.md).
    """
    try:
        return await CatalogBulkService.preview(session, payload, _actor(auth))
    except CatalogBulkConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/bulk/apply", response_model=CatalogBulkApplyResponse, operation_id="apply_manager_catalog_bulk")
async def apply_bulk(payload: CatalogBulkApplyRequest, session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(get_current_auth_context)):
    """
    Apply the signed preview after locking selected products and checking their
    fingerprints. All product changes commit in one transaction. Invalid/expired/wrong-actor
    token returns 400; removed or changed products return 409 and require a new preview.
    This is not a reusable idempotency receipt: a successful changing apply can make its own
    preview stale.

    Access and scope: shared catalog operations require an explicit platform-owner or
    delegated catalog permission, independent of company membership. Destructive operations
    require catalog.master.delete; imports, bulk tools and procurement remain platform-owner-only.
    This operates on the shared platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [catalog
    workspace](https://github.com/mvnby/air-api/blob/main/docs/catalog-management-workspace.md).
    """
    try:
        return await CatalogBulkService.apply(session, payload.token, _actor(auth))
    except CatalogBulkConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
