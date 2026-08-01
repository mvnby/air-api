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
    Массовое добавление или обновление характеристик.
    Идеально для установки диаметров труб для целой серии кондиционеров сразу.
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
    Массовая миграция характеристик.
    Переводит ключи Onliner (кириллица) в System (английский).
    """
    logger.info(f"Starting specs normalization (dry_run={dry_run}) by {username}")
    return await ManagerLegacySpecsService.normalize_legacy_specs(session, dry_run=dry_run)
