from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.catalog_decision import (
    CatalogDecisionAttachToOrderPayload,
    CatalogDecisionCreateCollectionPayload,
    CatalogDecisionCreateOrderPayload,
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
    CREATE_MANAGER_CATALOG_DECISION_ORDER,
    LIST_MANAGER_CATALOG_DECISION_FILTER_OPTIONS,
    LIST_MANAGER_CATALOG_DECISION_PRODUCTS,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from services.catalog_decision_projection import (
    SUPPORTED_COOLING_BTU_CLASSES,
    CatalogDecisionFilters,
    CatalogDecisionQueryService,
)
from services.catalog_decision_collection_service import CatalogDecisionCollectionService
from services.catalog_decision_order_service import (
    CatalogDecisionOrderConflict,
    CatalogDecisionOrderService,
)
from services.catalog_decision_quick_order_service import CatalogDecisionQuickOrderService
from schemas import ManagerOrderDetailResponse

router = APIRouter(prefix="/api/manager/catalog-decision", tags=["manager catalog decision"], route_class=ManagerPermissionRoute)


@router.get("/filter-options", response_model=CatalogDecisionFilterOptionsResponse, operation_id=LIST_MANAGER_CATALOG_DECISION_FILTER_OPTIONS)
async def list_catalog_decision_filter_options(
    session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read available brands, series and supported technical filters for the selected
    storefront’s split-system decision catalog. Options use storefront
    visibility/eligibility; this does not expose a supplier-management surface or mutate
    product data.

    Access and scope: Manager access is required; data is restricted to the authenticated
    tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await CatalogDecisionQueryService.list_filter_options(session, tenant_scope=tenant_scope)


@router.get("/products", response_model=CatalogDecisionListResponse, operation_id=LIST_MANAGER_CATALOG_DECISION_PRODUCTS)
async def list_catalog_decision_products(
    page: int = Query(1, ge=1), limit: int = Query(40, ge=1, le=100), search: str | None = Query(None, max_length=200),
    cooling_btu_classes: list[int] | None = Query(None), cooling_min_kw: float | None = Query(None, ge=0), cooling_max_kw: float | None = Query(None, ge=0),
    retail_min_byn: float | None = Query(None, ge=0), retail_max_byn: float | None = Query(None, ge=0),
    area_min: float | None = Query(None, ge=0), area_max: float | None = Query(None, ge=0),
    category: Literal["household", "multi", "semi_industrial"] | None = None,
    indoor_form_factor: Literal["wall", "cassette", "duct", "floor_ceiling", "column", "console"] | None = None,
    brand_ids: list[int] | None = Query(None), series_ids: list[int] | None = Query(None), is_inverter: bool | None = None,
    has_wifi: bool | None = None, wifi: Literal["builtin", "ready", "none"] | None = None, availability: Literal["in_stock", "out_of_stock"] | None = None,
    include_orderable: bool = False, product_ids: list[int] | None = Query(None, min_length=1, max_length=24),
    is_published: bool | None = None, sort: CatalogDecisionSort = "title", direction: Literal["asc", "desc"] = "asc",
    heating_min: int | None = Query(None, ge=-30, le=-20, multiple_of=5, description="Required outdoor heating temperature in Celsius; includes colder-rated models."),
    session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read eligible complete split systems with technical and commercial projections; limit is
    1–100. Availability defaults to in_stock; include_orderable removes that restriction.
    category=multi, unsupported BTU classes or inverted retail bounds return 422. Explicit
    product_ids is limited to 24. Demo purchase-cost projection uses a synthetic discount
    from RRC rather than actual supplier cost. This endpoint only reads.

    Access and scope: Manager access is required; data is restricted to the authenticated
    tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    if retail_min_byn is not None and retail_max_byn is not None and retail_min_byn > retail_max_byn:
        raise HTTPException(status_code=422, detail="retail_min_byn cannot exceed retail_max_byn")
    if any(btu not in SUPPORTED_COOLING_BTU_CLASSES for btu in cooling_btu_classes or ()):
        raise HTTPException(status_code=422, detail="Unsupported cooling BTU class")
    if category == "multi":
        raise HTTPException(status_code=422, detail="Мультисплиты не входят в подбор комплектных сплит-систем")
    effective_availability = None if include_orderable else (availability or "in_stock")
    return await CatalogDecisionQueryService.list_products(
        session, tenant_scope=tenant_scope, page=page, limit=limit, sort=sort, direction=direction,
        filters=CatalogDecisionFilters(search=search, cooling_btu_classes=tuple(cooling_btu_classes or ()), cooling_min_kw=cooling_min_kw, cooling_max_kw=cooling_max_kw, retail_min_byn=retail_min_byn, retail_max_byn=retail_max_byn, area_min=area_min, area_max=area_max, category=category, indoor_form_factor=indoor_form_factor, brand_ids=tuple(brand_ids or ()), series_ids=tuple(series_ids or ()), is_inverter=is_inverter, has_wifi=has_wifi, wifi=wifi, availability=effective_availability, is_published=is_published, heating_min=heating_min, product_ids=tuple(product_ids or ())),
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
    """
    Create a manual draft collection from the chosen split-system IDs, preserving their
    order as pinned items. Requires Manager access; unlike the general collection routes
    this bridge does not require storefront.collections.manage. Empty title/duplicates or
    non-split-system selections return 400; products unavailable to the storefront return
    404. Each POST creates a new collection.

    Access and scope: Manager access is required; data is restricted to the authenticated
    tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
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
    """
    Add selected equipment to a scoped negotiation-stage order. auto returns 409 when active
    proposals already contain products; replace_selected replaces the selected proposal,
    new_alternative creates variant(s), and append_to_proposal skips products already in the
    chosen draft. Invalid selection/proposal/lifecycle mode returns 400. Commands lock the
    order and recalculate financials. No idempotency receipt exists; repeating
    new_alternative can create another proposal.

    Access and scope: Manager access is required; data is restricted to the authenticated
    tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await CatalogDecisionOrderService.attach(
            session,
            order_id=order_id,
            product_ids=payload.product_ids,
            mode=payload.mode,
            proposal_mode=payload.proposal_mode,
            proposal_id=payload.proposal_id,
            tenant_scope=tenant_scope,
        )
    except CatalogDecisionOrderConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/orders",
    response_model=ManagerOrderDetailResponse,
    operation_id=CREATE_MANAGER_CATALOG_DECISION_ORDER,
)
async def create_catalog_decision_order(
    payload: CatalogDecisionCreateOrderPayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Create a scoped negotiation-stage quick order with a new proposal and selected equipment
    snapshots. Duplicate products, empty key or invalid mode returns 400. idempotency_key is
    scoped to tenant/storefront; a repeat returns the existing order even if the new payload
    differs, rather than checking a payload receipt. Reuse a key only for the same creation
    intent.

    Access and scope: Manager access is required; data is restricted to the authenticated
    tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await CatalogDecisionQuickOrderService.create(
            session,
            product_ids=payload.product_ids,
            idempotency_key=payload.idempotency_key,
            prospect_type=payload.prospect_type,
            proposal_mode=payload.proposal_mode,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
