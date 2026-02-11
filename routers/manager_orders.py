from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from schemas import (
    ManagerOrderDetailResponse,
    ManagerOrderDocumentResponse,
    ManagerOrderListResponse,
    ManagerOrderUpdatePayload,
)
from services.document_service import DocumentService
from services.order_service import OrderService


router = APIRouter(prefix="/api/manager/orders", tags=["manager-orders"])

ALLOWED_DOC_TYPES = {"contract", "invoice", "work_order", "act", "offer", "tn2", "ttn1"}


@router.get("", response_model=ManagerOrderListResponse, operation_id="get_manager_orders")
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


@router.get("/{order_id}", response_model=ManagerOrderDetailResponse, operation_id="get_manager_order_detail")
async def get_manager_order_detail(
    order_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    data = await OrderService.get_order_detail_for_manager(session, order_id)
    if not data:
        raise HTTPException(status_code=404, detail="Order not found")
    return data


@router.patch("/{order_id}", response_model=ManagerOrderDetailResponse, operation_id="patch_manager_order")
async def patch_manager_order(
    order_id: int,
    payload: ManagerOrderUpdatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await OrderService.update_order_for_manager(session, order_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not data:
        raise HTTPException(status_code=404, detail="Order not found")
    return data


@router.post(
    "/{order_id}/documents/{doc_type}",
    response_model=ManagerOrderDocumentResponse,
    operation_id="generate_manager_order_document",
)
async def generate_manager_order_document(
    order_id: int,
    doc_type: str,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    if doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported document type: {doc_type}")
    try:
        doc = await DocumentService.create_or_get_document(session=session, order_id=order_id, doc_type=doc_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "doc_id": doc.id,
        "doc_type": doc.doc_type,
        "edit_url": doc.google_edit_url,
    }
