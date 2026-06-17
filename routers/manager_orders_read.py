from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    EXPORT_MANAGER_ORDERS,
    GET_MANAGER_ORDER_DETAIL,
    GET_MANAGER_ORDERS,
    LIST_MANAGER_STALE_ORDER_STAGES,
)
from schemas import (
    ManagerOrderDetailResponse,
    ManagerOrderExportRequest,
    ManagerOrderListResponse,
    ManagerOrderTransferPackage,
    ManagerStaleWorkStageListResponse,
)
from services.order_service import OrderService
from services.order_transfer_service import OrderTransferService


router = APIRouter(prefix="/api/manager/orders", tags=["manager-orders"])


@router.get("", response_model=ManagerOrderListResponse, operation_id=GET_MANAGER_ORDERS)
async def get_manager_orders(
    segment: str = Query("b2c", pattern="^(b2c|b2b)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    overdue_only: bool = Query(False),
    sort: str = Query("created_at_desc"),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await OrderService.get_orders_for_manager(
            session=session,
            customer_segment=segment,
            page=page,
            limit=limit,
            status=status,
            search=search,
            overdue_only=overdue_only,
            sort=sort,
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
):
    return await OrderService.list_stale_order_stages(
        session,
        older_than_days=older_than_days,
        include_unscheduled=include_unscheduled,
        limit=limit,
    )


@router.post("/export", response_model=ManagerOrderTransferPackage, operation_id=EXPORT_MANAGER_ORDERS)
async def export_manager_orders(
    payload: ManagerOrderExportRequest,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await OrderTransferService.export_orders(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{order_id}", response_model=ManagerOrderDetailResponse, operation_id=GET_MANAGER_ORDER_DETAIL)
async def get_manager_order_detail(
    order_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    data = await OrderService.get_order_detail_for_manager(session, order_id)
    if not data:
        raise HTTPException(status_code=404, detail="Order not found")
    return data
