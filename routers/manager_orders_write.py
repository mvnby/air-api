from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, DOCUMENT_GENERATION_FAILED, ORDER_NOT_FOUND
from core.security import get_current_username
from routers.manager_operation_ids import (
    CREATE_MANAGER_ORDER,
    GENERATE_MANAGER_ORDER_DOCUMENT,
    PATCH_MANAGER_ORDER,
    ADD_MANAGER_ORDER_PAYMENT,
    DELETE_MANAGER_ORDER_PAYMENT,
    CREATE_MANAGER_ORDER_STAGE,
    UPDATE_MANAGER_ORDER_STAGE,
    DELETE_MANAGER_ORDER_STAGE,
)
from schemas import (
    ManagerOrderCreatePayload,
    ManagerOrderDetailResponse,
    ManagerOrderDocumentResponse,
    ManagerOrderUpdatePayload,
    PaymentCreatePayload,
    PaymentResponse,
    OrderWorkStageCreatePayload,
    OrderWorkStageUpdatePayload,
)
from services.document_service import DocumentService
from services.order_service import OrderService


router = APIRouter(prefix="/api/manager/orders", tags=["manager-orders"])


@router.post("", response_model=ManagerOrderDetailResponse, operation_id=CREATE_MANAGER_ORDER)
async def create_manager_order(
    payload: ManagerOrderCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        from models import LeadSource
        source_enum = LeadSource(payload.source) if payload.source else LeadSource.MANAGER
        order = await OrderService.create_from_website(
            session=session,
            customer_name=payload.name or "Новый клиент",
            customer_phone=payload.phone or "",
            customer_email=None,
            customer_address=None,
            items=[],
            lead_source=source_enum,
            comment=payload.request_text,
        )
        # Save optional service_type into technical_meta
        if payload.service_type:
            from sqlalchemy.orm import Session
            from sqlalchemy.orm.attributes import flag_modified
            raw_order = await session.get(type(order), order.id)
            if raw_order is not None:
                raw_order.technical_meta = dict(raw_order.technical_meta or {})
                raw_order.technical_meta["service_type"] = payload.service_type
                flag_modified(raw_order, "technical_meta")
                session.add(raw_order)
                await session.commit()
                await session.refresh(raw_order)
                order = raw_order
        data = await OrderService.get_order_detail_for_manager(session, order.id)
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_ORDER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    return data


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
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_ORDER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc

    if not data:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_ORDER,
            error_code=ORDER_NOT_FOUND,
        )
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
        raise manager_http_error(
            status_code=400,
            endpoint=GENERATE_MANAGER_ORDER_DOCUMENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    except Exception as exc:
        raise manager_http_error(
            status_code=500,
            endpoint=GENERATE_MANAGER_ORDER_DOCUMENT,
            error_code=DOCUMENT_GENERATION_FAILED,
            message=str(exc),
        ) from exc


@router.post(
    "/{order_id}/payments",
    response_model=List[PaymentResponse],
    operation_id=ADD_MANAGER_ORDER_PAYMENT,
)
async def add_manager_order_payment(
    order_id: int,
    payload: PaymentCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await OrderService.add_payment(session, order_id, payload)
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=ADD_MANAGER_ORDER_PAYMENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.delete(
    "/{order_id}/payments/{payment_id}",
    response_model=List[PaymentResponse],
    operation_id=DELETE_MANAGER_ORDER_PAYMENT,
)
async def delete_manager_order_payment(
    order_id: int,
    payment_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await OrderService.delete_payment(session, order_id, payment_id)
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=DELETE_MANAGER_ORDER_PAYMENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc



@router.post(
    "/{order_id}/stages",
    response_model=ManagerOrderDetailResponse,
    operation_id=CREATE_MANAGER_ORDER_STAGE,
)
async def create_manager_order_stage(
    order_id: int,
    payload: OrderWorkStageCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await OrderService.add_order_stage(session, order_id, payload)
    except ValueError as exc:
        raise manager_http_error(status_code=400, endpoint=CREATE_MANAGER_ORDER_STAGE, error_code=BAD_REQUEST, message=str(exc)) from exc


@router.patch(
    "/{order_id}/stages/{stage_id}",
    response_model=ManagerOrderDetailResponse,
    operation_id=UPDATE_MANAGER_ORDER_STAGE,
)
async def update_manager_order_stage(
    order_id: int,
    stage_id: int,
    payload: OrderWorkStageUpdatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await OrderService.update_order_stage(session, order_id, stage_id, payload)
    except ValueError as exc:
        raise manager_http_error(status_code=400, endpoint=UPDATE_MANAGER_ORDER_STAGE, error_code=BAD_REQUEST, message=str(exc)) from exc


@router.delete(
    "/{order_id}/stages/{stage_id}",
    response_model=ManagerOrderDetailResponse,
    operation_id=DELETE_MANAGER_ORDER_STAGE,
)
async def delete_manager_order_stage(
    order_id: int,
    stage_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await OrderService.delete_order_stage(session, order_id, stage_id)
    except ValueError as exc:
        raise manager_http_error(status_code=400, endpoint=DELETE_MANAGER_ORDER_STAGE, error_code=BAD_REQUEST, message=str(exc)) from exc


