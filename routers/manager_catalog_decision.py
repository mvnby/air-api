from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.catalog_decision import (
    CatalogDecisionAttachToOrderPayload,
    CatalogDecisionCreateCollectionPayload,
    CatalogDecisionFilterOptionsResponse,
    CatalogDecisionListResponse,
    CatalogDecisionSort,
)
from api_contracts.product_collections import ManagerProductCollectionResponse
from core.database import get_session
from core.security import AuthenticatedUser, get_current_manager_tenant_scope, require_manager_access
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    ATTACH_MANAGER_CATALOG_DECISION_TO_ORDER,
    CREATE_MANAGER_CATALOG_DECISION_COLLECTION,
    LIST_MANAGER_CATALOG_DECISION_FILTER_OPTIONS,
    LIST_MANAGER_CATALOG_DECISION_PRODUCTS,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from services.catalog_decision_projection import CatalogDecisionFilters, CatalogDecisionQueryService
from services.catalog_decision_collection_service import CatalogDecisionCollectionService
from services.catalog_decision_order_service import (
    CatalogDecisionOrderConflict,
    CatalogDecisionOrderService,
)
from schemas import ManagerOrderDetailResponse

router = APIRouter(prefix="/api/manager/catalog-decision", tags=["manager catalog decision"], route_class=ManagerPermissionRoute)


@router.get("/filter-options", response_model=CatalogDecisionFilterOptionsResponse, operation_id=LIST_MANAGER_CATALOG_DECISION_FILTER_OPTIONS)
async def list_catalog_decision_filter_options(
    session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    return await CatalogDecisionQueryService.list_system_filter_options(session, tenant_scope=tenant_scope)


@router.get("/products", response_model=CatalogDecisionListResponse, operation_id=LIST_MANAGER_CATALOG_DECISION_PRODUCTS)
async def list_catalog_decision_products(
    page: int = Query(1, ge=1), limit: int = Query(40, ge=1, le=100), search: str | None = Query(None, max_length=200),
    cooling_btu_classes: list[int] | None = Query(None), cooling_min_kw: float | None = Query(None, ge=0), cooling_max_kw: float | None = Query(None, ge=0),
    area_min: float | None = Query(None, ge=0), area_max: float | None = Query(None, ge=0),
    category: Literal["household", "multi", "semi_industrial"] | None = None,
    indoor_form_factor: Literal["wall", "cassette", "duct", "floor_ceiling", "column"] | None = None,
    brand_ids: list[int] | None = Query(None), series_ids: list[int] | None = Query(None), is_inverter: bool | None = None,
    has_wifi: bool | None = None, wifi: Literal["builtin", "ready", "none"] | None = None, availability: Literal["in_stock", "out_of_stock"] | None = "in_stock",
    is_published: bool | None = None, sort: CatalogDecisionSort = "title", direction: Literal["asc", "desc"] = "asc",
    session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    return await CatalogDecisionQueryService.list_system_products(
        session, tenant_scope=tenant_scope, page=page, limit=limit, sort=sort, direction=direction,
        filters=CatalogDecisionFilters(search=search, cooling_btu_classes=tuple(cooling_btu_classes or ()), cooling_min_kw=cooling_min_kw, cooling_max_kw=cooling_max_kw, area_min=area_min, area_max=area_max, category=category, indoor_form_factor=indoor_form_factor, brand_ids=tuple(brand_ids or ()), series_ids=tuple(series_ids or ()), is_inverter=is_inverter, has_wifi=has_wifi, wifi=wifi, availability=availability, is_published=is_published),
    )


@router.post(
    "/collections",
    response_model=ManagerProductCollectionResponse,
    operation_id=CREATE_MANAGER_CATALOG_DECISION_COLLECTION,
)
async def create_catalog_decision_collection(
    payload: CatalogDecisionCreateCollectionPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    return await CatalogDecisionCollectionService.create(
        session,
        title=payload.title,
        product_ids=payload.product_ids,
        tenant_scope=tenant_scope,
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
    )


@router.post(
    "/orders/{order_id}/attach",
    response_model=ManagerOrderDetailResponse,
    operation_id=ATTACH_MANAGER_CATALOG_DECISION_TO_ORDER,
)
async def attach_catalog_decision_to_order(
    order_id: int,
    payload: CatalogDecisionAttachToOrderPayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await CatalogDecisionOrderService.attach(
            session,
            order_id=order_id,
            product_ids=payload.product_ids,
            mode=payload.mode,
            tenant_scope=tenant_scope,
        )
    except CatalogDecisionOrderConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
