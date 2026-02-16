from typing import List, Optional
from datetime import datetime
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import (
    BulkSpecUpdate,
    SpecsKeysResponse,
    ProductUpdate,
    BulkRoundRequest,
)

from core.database import get_session
from core.config import settings
from core.security import get_current_username
from core.logger import logger
from services.manager_catalog_service import ManagerCatalogService
from services.manager_legacy_specs_service import ManagerLegacySpecsService
from services.manager_specs_service import ManagerSpecsService

router = APIRouter(prefix="/api/manager", tags=["manager"])

@router.get("/me", operation_id="read_user_me")
async def check_auth_status(username: str = Depends(get_current_username)):
    """
    Check if current user is authenticated.
    Returns username if valid, 401 otherwise (via Depends).
    """
    return {"username": username, "status": "authenticated"}

@router.post("/specs/bulk-update", operation_id="bulk_update_specs")
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

@router.post("/specs/normalize-legacy", operation_id="normalize_legacy_specs")
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

# =============================================
# Manager List Endpoints (Stitch Integration)
# =============================================

@router.get("/products/list", operation_id="get_manager_products")
async def list_products_for_manager(
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    search: Optional[str] = Query(None),
    is_published: Optional[bool] = Query(None),
    area_min: Optional[int] = Query(None),
    area_max: Optional[int] = Query(None),
    is_inverter: Optional[bool] = Query(None),
    sort: str = Query("newest"),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Paginated product list for manager UI.
    Unlike the public catalog, this can show unpublished products.
    """
    return await ManagerCatalogService.list_products(
        session=session,
        page=page,
        limit=limit,
        search=search,
        is_published=is_published,
        area_min=area_min,
        area_max=area_max,
        is_inverter=is_inverter,
        sort=sort,
    )


@router.get("/customers", operation_id="get_manager_customers")
async def list_customers_for_manager(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    customer_type: Optional[str] = Query(None, alias="type"),
    only_with_orders: bool = Query(True),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Paginated customer list for manager UI.
    Includes order count per customer.
    """
    return await ManagerCatalogService.list_customers(
        session=session,
        page=page,
        limit=limit,
        search=search,
        customer_type=customer_type,
        only_with_orders=only_with_orders,
    )


@router.patch("/products/{product_id}", operation_id="update_product")
async def update_product(
    product_id: int,
    data: ProductUpdate,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Update individual product fields.
    """
    result = await ManagerCatalogService.update_product(
        session=session,
        product_id=product_id,
        data=data,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Product not found")

    return result


@router.post("/products/bulk-round-price", operation_id="bulk_round_price")
async def bulk_round_price(
    request: BulkRoundRequest,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Round prices down to the nearest multiple of 50.
    """
    return await ManagerCatalogService.bulk_round_prices(session=session, request=request)


@router.get("/tags/all", operation_id="get_all_tags")
async def get_all_tags(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Return all tags grouped by TagGroup for the product editor.
    """
    return await ManagerCatalogService.get_all_tags(session)
