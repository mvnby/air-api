from datetime import date
from typing import Optional

from api_contracts.order_board import ManagerOrderBoardPage
from services.order_board_projection import OrderBoardProjection

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import (
    AuthenticatedUser, get_current_manager_tenant_scope, get_current_username,
    require_manager_access,
)
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    EXPORT_MANAGER_ORDERS,
    GET_MANAGER_ORDER_DETAIL,
    GET_MANAGER_ORDER_BOARD,
    GET_MANAGER_ORDERS,
    LIST_MANAGER_ORDER_SCENARIOS,
    LIST_MANAGER_STALE_ORDER_STAGES,
)
from schemas import (
    ManagerOrderDetailResponse,
    ManagerOrderExportRequest,
    ManagerOrderListResponse,
    ManagerOrderScenariosResponse,
    ManagerOrderTransferPackage,
    ManagerStaleWorkStageListResponse,
)
from services.order_service import OrderService
from services.order_projection_service import OrderProjectionService
from services.order_transfer_service import OrderTransferService
from services.order_scenarios import SCENARIOS


router = APIRouter(prefix="/api/manager/orders", tags=["manager-orders"])


@router.get(
    "/scenarios",
    response_model=ManagerOrderScenariosResponse,
    operation_id=LIST_MANAGER_ORDER_SCENARIOS,
)
async def list_manager_order_scenarios(
    _: str = Depends(get_current_username),
):
    """
    Read the shared allowed order scenario dictionary. Manager access is required; this
    response is configuration metadata, not a list of tenant orders.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return {"items": [scenario._asdict() for scenario in SCENARIOS]}


@router.get("", response_model=ManagerOrderListResponse, operation_id=GET_MANAGER_ORDERS)
async def get_manager_orders(
    segment: str = Query("b2c", pattern="^(all|b2c|b2b)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    overdue_only: bool = Query(False),
    sort: str = Query("created_at_desc"),
    customer_id: Optional[int] = Query(None, gt=0),
    assigned_to_me: bool = Query(False),
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Page orders accessible in the current Manager tenant/storefront, applying customer
    segment, status/search/overdue/customer, personal assignment and sort filters before
    pagination and count. "assigned_to_me" uses the authenticated staff ID; a legacy
    identity without a staff ID receives an empty personal result. limit is at
    most 100. Invalid business filters/sort return 400; response carries list metadata
    rather than unrestricted platform CRM data.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await OrderProjectionService.get_orders_for_manager(
            session=session,
            customer_segment=segment,
            page=page,
            limit=limit,
            tenant_scope=tenant_scope,
            status=status,
            search=search,
            overdue_only=overdue_only,
            sort=sort,
            customer_id=customer_id,
            assigned_to_me=assigned_to_me,
            staff_user_id=auth.staff_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/work-stages/stale",
    response_model=ManagerStaleWorkStageListResponse,
    operation_id=LIST_MANAGER_STALE_ORDER_STAGES,
)
async def list_manager_stale_order_stages(
    older_than_days: int = Query(7, ge=0, le=365),
    include_unscheduled: bool = Query(True),
    limit: int = Query(100, ge=1, le=100),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    List at most 100 stale work stages in the current Manager tenant/storefront, using the
    age threshold and optional unscheduled stages. Read-only: does not cancel/delete stages
    or notify installers.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await OrderService.list_stale_order_stages(
        session,
        tenant_scope=tenant_scope,
        older_than_days=older_than_days,
        include_unscheduled=include_unscheduled,
        limit=limit,
    )


@router.post("/export", response_model=ManagerOrderTransferPackage, operation_id=EXPORT_MANAGER_ORDERS)
async def export_manager_orders(
    payload: ManagerOrderExportRequest,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Export explicitly selected accessible orders as a transfer package in the current
    Manager tenant/storefront. Missing/inaccessible selections or invalid export input
    return 400. This POST is read-only; it does not transfer documents/provider files or
    write a destination tenant.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await OrderTransferService.export_orders(
            session,
            payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/board", response_model=ManagerOrderBoardPage, operation_id=GET_MANAGER_ORDER_BOARD)
async def get_manager_order_board(
    segment: str = Query("b2c", pattern="^(all|b2c|b2b)$"),
    queue: str = Query("active", pattern="^(active|waiting|history|all)$"),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    assigned_to_me: bool = Query(False),
    customer_id: Optional[int] = Query(None, gt=0),
    work_filter: str = Query("all", pattern="^(all|followup|planning|unpaid)$"),
    result: Optional[str] = Query(None, pattern="^(won|lost|unknown)$"),
    closed_from: Optional[date] = Query(None),
    closed_to: Optional[date] = Query(None),
    include_unknown_date: bool = Query(False),
    group_by_customer: bool = Query(False),
    group_key: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
    column: Optional[str] = Query(None, pattern="^(negotiation|execution)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    sort: str = Query("created_at_desc"),
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """Read bounded scalar cards or exact customer aggregates in the current Manager
    tenant/storefront/customer and assignment scope. Active excludes paused and closed;
    waiting contains paused live orders; history includes every closed order, including
    legacy NULL results/dates and old hold flags. Date bounds use closed_at only; without
    bounds unknown dates are included. include_unknown_date includes them with a range.
    Due contacts span both live queues without resuming an order. Search callers can use
    queue=all. Groups have stable keys and no eager children; group_key pages at most 100
    children through the identical filters. Counts precede pagination, with deterministic
    ID ties. Money is computed from proposal lines and currency payments, including complete group aggregates.
    This read never loads proposal/product/service graphs or modifies orders. Existing
    GET /orders keeps its contract. Invalid filters return 400, invalid bounds 422.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await OrderBoardProjection.page(
            session, tenant_scope=tenant_scope, segment=segment, queue=queue, status=status,
            search=search, assigned_to_me=assigned_to_me, staff_user_id=auth.staff_user_id,
            customer_id=customer_id, work_filter=work_filter, result=result,
            closed_from=closed_from, closed_to=closed_to, include_unknown_date=include_unknown_date,
            group_by_customer=group_by_customer, group_key=group_key, phase=phase, column=column,
            page=page, limit=limit, sort=sort,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{order_id}", response_model=ManagerOrderDetailResponse, operation_id=GET_MANAGER_ORDER_DETAIL)
async def get_manager_order_detail(
    order_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read the current Manager tenant/storefront order projection with proposals, lines,
    stages and payment context. Missing or inaccessible order returns 404. Opening the
    detail does not imply a client may edit another tenant’s IDs.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    data = await OrderProjectionService.get_order_detail_for_manager(
        session,
        order_id,
        tenant_scope=tenant_scope,
    )
    if not data:
        raise HTTPException(status_code=404, detail="Order not found")
    return data
