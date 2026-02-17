from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import GENERATE_MANAGER_ORDER_DOCUMENT, PATCH_MANAGER_ORDER
from schemas import (
    ManagerOrderDetailResponse,
    ManagerOrderDocumentResponse,
    ManagerOrderUpdatePayload,
)
from services.document_service import DocumentService
from services.order_service import OrderService


router = APIRouter(prefix="/api/manager/orders", tags=["manager-orders"])


@router.patch("/{order_id}", response_model=ManagerOrderDetailResponse, operation_id=PATCH_MANAGER_ORDER)
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
    operation_id=GENERATE_MANAGER_ORDER_DOCUMENT,
)
async def generate_manager_order_document(
    order_id: int,
    doc_type: str,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await DocumentService.generate_manager_order_document(
            session=session,
            order_id=order_id,
            doc_type=doc_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
