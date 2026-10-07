from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.logger import logger
from core.security import get_current_username
from routers.manager_operation_ids import BULK_UPDATE_SPECS, NORMALIZE_LEGACY_SPECS
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    BulkSpecUpdate,
    ManagerBulkSpecsResponse,
    ManagerNormalizeLegacySpecsResponse,
)
from services.manager_legacy_specs_service import ManagerLegacySpecsService
from services.manager_specs_service import ManagerSpecsService


router = APIRouter(
    prefix="/api/manager",
    tags=["manager"],
    route_class=ManagerPermissionRoute,
)


@router.post(
    "/specs/bulk-update",
    response_model=ManagerBulkSpecsResponse,
    operation_id=BULK_UPDATE_SPECS,
)
async def bulk_update_specs(
    payload: BulkSpecUpdate,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """
    Merge, replace or delete spec keys on existing selected products, normalize the result
    and synchronize brand/series plus catalog revisions. Replace replaces the full spec map;
    deleting series aliases clears the series assignment when absent. Missing product IDs
    are ignored. Wi-Fi edits replace related source/derived keys as a group; changes commit
    together.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    logger.info(f"Manager {username} bulk updating specs for {len(payload.product_ids)} products. Op: {payload.operation}")
    return await ManagerSpecsService.bulk_update_specs(session, payload)


@router.post(
    "/specs/normalize-legacy",
    response_model=ManagerNormalizeLegacySpecsResponse,
    operation_id=NORMALIZE_LEGACY_SPECS,
)
async def normalize_legacy_specs(
    dry_run: bool = Query(True, description="Если True - не сохраняет изменения в БД, только показывает пример"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """
    Scan products with specs and convert legacy labels/values using the legacy migration
    map. dry_run defaults to true and counts prospective changes without saving;
    dry_run=false commits changed spec maps. Invalid legacy formats and per-product failures
    are logged/skipped. This synchronous catalog-wide migration does not run the ordinary
    normalized-spec/brand-series editor pipeline.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    logger.info(f"Starting specs normalization (dry_run={dry_run}) by {username}")
    return await ManagerLegacySpecsService.normalize_legacy_specs(session, dry_run=dry_run)
