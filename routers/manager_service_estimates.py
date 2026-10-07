from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    CALCULATE_MANAGER_INSTALL_ESTIMATE,
    CREATE_MANAGER_SERVICE_ESTIMATE,
    DELETE_MANAGER_SERVICE_ESTIMATE,
    GET_MANAGER_SERVICE_ESTIMATE,
    GET_MANAGER_SERVICE_ESTIMATE_ORDER_LINES,
    LIST_MANAGER_SERVICE_ESTIMATES,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    ManagerActionMessageResponse,
    ManagerInstallEstimateCalculatePayload,
    ManagerInstallEstimateResponse,
    ManagerInstallEstimateSavePayload,
    ManagerServiceDescriptionMode,
    ManagerServiceEstimateOrderLinesMode,
    ManagerServiceEstimateOrderLinesResponse,
    ManagerServiceEstimateListResponse,
    ManagerServiceEstimateResponse,
)
from services.service_estimate_service import ServiceEstimateService


router = APIRouter(
    prefix="/api/manager/service-estimates",
    tags=["manager/service-estimates"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)


@router.post("/calculate", response_model=ManagerInstallEstimateResponse, operation_id=CALCULATE_MANAGER_INSTALL_ESTIMATE)
async def calculate_manager_install_estimate(
    payload: ManagerInstallEstimateCalculatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Calculate legacy tariff/rule pricing and discount without saving a ServiceEstimate or
    adding order lines. Missing/out-of-scope tariff returns 404; inactive tariffs remain
    addressable by ID, but inactive rules are excluded from calculation. After tenant
    price-book publication, installation tariffs return 409 book_preview_required while
    other service kinds remain available. Use published-book preview/confirmation for new
    typed installation pricing.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await ServiceEstimateService.calculate_install_estimate(
        session, payload, tenant_scope
    )


@router.post(
    "",
    response_model=ManagerServiceEstimateResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_SERVICE_ESTIMATE,
)
async def create_manager_service_estimate(
    payload: ManagerInstallEstimateSavePayload,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Calculate current legacy tariff/rules and save an independent estimate/item snapshot,
    optionally linked to a tenant customer. Missing/out-of-scope tariff or inaccessible
    customer returns 404; inactive tariffs remain addressable by ID. Installation tariffs
    are blocked with 409 book_preview_required after book publication; other service kinds
    remain supported. No idempotency receipt exists: each successful call creates a new
    snapshot and does not attach it to an order.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await ServiceEstimateService.create_install_estimate(
        session=session,
        payload=payload,
        created_by=username,
        tenant_scope=tenant_scope,
    )


@router.get("", response_model=ManagerServiceEstimateListResponse, operation_id=LIST_MANAGER_SERVICE_ESTIMATES)
async def list_manager_service_estimates(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    customer_id: int | None = Query(None, ge=1),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read saved historical service estimates, optionally by customer, with page starting at 1
    and limit 1–100. Publication of a typed installation price book does not hide prior
    estimates. Reading uses saved snapshots rather than recalculating current tariffs.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await ServiceEstimateService.list_estimates(
        session=session,
        page=page,
        limit=limit,
        customer_id=customer_id,
        tenant_scope=tenant_scope,
    )


@router.get(
    "/{estimate_id}/order-lines",
    response_model=ManagerServiceEstimateOrderLinesResponse,
    operation_id=GET_MANAGER_SERVICE_ESTIMATE_ORDER_LINES,
)
async def get_manager_service_estimate_order_lines(
    estimate_id: int,
    mode: ManagerServiceEstimateOrderLinesMode = Query(ManagerServiceEstimateOrderLinesMode.detailed),
    description_mode: ManagerServiceDescriptionMode = Query(ManagerServiceDescriptionMode.short),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Project a saved service estimate into collapsed/detailed order-line payloads with
    short/full descriptions. Missing estimate returns 404; inconsistent totals or amounts
    outside the writable service-money range return 409. Discount is distributed so
    projected lines reconcile to the saved total. This only returns a projection and does
    not insert proposal/order lines.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await ServiceEstimateService.get_estimate_order_lines(
        session=session,
        estimate_id=estimate_id,
        mode=mode,
        description_mode=description_mode,
        tenant_scope=tenant_scope,
    )


@router.get("/{estimate_id}", response_model=ManagerServiceEstimateResponse, operation_id=GET_MANAGER_SERVICE_ESTIMATE)
async def get_manager_service_estimate(
    estimate_id: int,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read one saved historical service-estimate snapshot and items. Missing or inaccessible
    estimate returns 404. Changes to tariff definitions and later price-book publication do
    not recalculate its saved amounts.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await ServiceEstimateService.get_estimate_by_id(
        session=session,
        estimate_id=estimate_id,
        tenant_scope=tenant_scope,
    )


@router.delete(
    "/{estimate_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_SERVICE_ESTIMATE,
)
async def delete_manager_service_estimate(
    estimate_id: int,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Permanently delete one saved historical service estimate. Missing or inaccessible
    estimate returns 404, including after deletion. This is a mutation of saved history, not
    cancellation of an accepted typed installation estimate or automatic removal of order
    lines.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await ServiceEstimateService.delete_estimate(
        session=session,
        estimate_id=estimate_id,
        tenant_scope=tenant_scope,
    )
