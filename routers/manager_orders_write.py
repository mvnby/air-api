from typing import List, Optional
from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, DOCUMENT_GENERATION_FAILED, ORDER_DOCUMENTS_LOCKED, ORDER_NOT_FOUND
from core.security import get_current_manager_tenant_scope, get_current_username
from routers.manager_operation_ids import (
    CREATE_MANAGER_ORDER,
    CREATE_MANAGER_ORDER_PROPOSAL,
    DUPLICATE_MANAGER_ORDER_PROPOSAL,
    GENERATE_MANAGER_ORDER_DOCUMENT,
    PATCH_MANAGER_ORDER,
    PATCH_MANAGER_ORDER_PROPOSAL,
    ARCHIVE_MANAGER_ORDER_PROPOSAL,
    SELECT_MANAGER_ORDER_PROPOSAL,
    DELETE_MANAGER_ORDER,
    ADD_MANAGER_ORDER_PAYMENT,
    DELETE_MANAGER_ORDER_PAYMENT,
    CREATE_MANAGER_ORDER_STAGE,
    UPDATE_MANAGER_ORDER_STAGE,
    DELETE_MANAGER_ORDER_STAGE,
    CANCEL_MANAGER_ORDER_STAGE_DIRECT,
    DELETE_MANAGER_ORDER_STAGE_DIRECT,
    IMPORT_MANAGER_ORDERS,
    PREVIEW_IMPORT_MANAGER_ORDERS,
)
from schemas import (
    ManagerOrderImportCommitRequest,
    ManagerOrderImportCommitResponse,
    ManagerOrderImportPreviewRequest,
    ManagerOrderImportPreviewResponse,
    ManagerOrderCreatePayload,
    ManagerOrderDetailResponse,
    ManagerOrderDocumentGeneratePayload,
    ManagerOrderDocumentResponse,
    ManagerOrderUpdatePayload,
    OrderProposalCreatePayload,
    OrderProposalUpdatePayload,
    PaymentCreatePayload,
    PaymentResponse,
    OrderWorkStageCreatePayload,
    OrderWorkStageUpdatePayload,
    ManagerStaleWorkStageItem,
)
from services.document_service import DocumentService, OrderDocumentsLockedError
from services.order_create_command_service import OrderCreateCommandService
from services.order_payment_command_service import OrderPaymentCommandService
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_service import OrderService
from services.order_transfer_service import OrderTransferService
from services.order_work_stage_command_service import OrderWorkStageCommandService
from services.tenant_scope_service import TenantScope


router = APIRouter(prefix="/api/manager/orders", tags=["manager-orders"])


@router.post("", response_model=ManagerOrderDetailResponse, operation_id=CREATE_MANAGER_ORDER)
async def create_manager_order(
    payload: ManagerOrderCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        data = await OrderCreateCommandService.create_manager_order(
            session=session,
            payload=payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_ORDER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    return data


@router.patch(
    "/work-stages/{stage_id}/cancel",
    response_model=ManagerStaleWorkStageItem,
    operation_id=CANCEL_MANAGER_ORDER_STAGE_DIRECT,
)
async def cancel_manager_order_stage_direct(
    stage_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderWorkStageCommandService.cancel_order_stage_direct(
            session,
            stage_id,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=CANCEL_MANAGER_ORDER_STAGE_DIRECT,
            error_code=ORDER_NOT_FOUND,
            message=str(exc),
        ) from exc


@router.delete(
    "/work-stages/{stage_id}",
    response_model=dict,
    operation_id=DELETE_MANAGER_ORDER_STAGE_DIRECT,
)
async def delete_manager_order_stage_direct(
    stage_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderWorkStageCommandService.delete_order_stage_direct(
            session,
            stage_id,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=DELETE_MANAGER_ORDER_STAGE_DIRECT,
            error_code=ORDER_NOT_FOUND,
            message=str(exc),
        ) from exc


@router.patch("/{order_id}", response_model=ManagerOrderDetailResponse, operation_id=PATCH_MANAGER_ORDER)
async def patch_manager_order(
    order_id: int,
    payload: ManagerOrderUpdatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        data = await OrderService.update_order_for_manager(
            session,
            order_id,
            payload,
            tenant_scope=tenant_scope,
        )
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
    "/import/preview",
    response_model=ManagerOrderImportPreviewResponse,
    operation_id=PREVIEW_IMPORT_MANAGER_ORDERS,
)
async def preview_import_manager_orders(
    payload: ManagerOrderImportPreviewRequest,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderTransferService.preview_import(
            session,
            payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PREVIEW_IMPORT_MANAGER_ORDERS,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/import",
    response_model=ManagerOrderImportCommitResponse,
    operation_id=IMPORT_MANAGER_ORDERS,
)
async def import_manager_orders(
    payload: ManagerOrderImportCommitRequest,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderTransferService.import_orders(
            session,
            payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=IMPORT_MANAGER_ORDERS,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/{order_id}/proposals",
    response_model=ManagerOrderDetailResponse,
    operation_id=CREATE_MANAGER_ORDER_PROPOSAL,
)
async def create_manager_order_proposal(
    order_id: int,
    payload: OrderProposalCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderProposalCommandService.create_order_proposal(
            session,
            order_id,
            payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(status_code=400, endpoint=CREATE_MANAGER_ORDER_PROPOSAL, error_code=BAD_REQUEST, message=str(exc)) from exc


@router.post(
    "/{order_id}/proposals/{proposal_id}/duplicate",
    response_model=ManagerOrderDetailResponse,
    operation_id=DUPLICATE_MANAGER_ORDER_PROPOSAL,
)
async def duplicate_manager_order_proposal(
    order_id: int,
    proposal_id: int,
    payload: OrderProposalCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    duplicate_payload = OrderProposalCreatePayload(
        name=payload.name,
        duplicate_from_proposal_id=proposal_id,
    )
    try:
        return await OrderProposalCommandService.create_order_proposal(
            session,
            order_id,
            duplicate_payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(status_code=400, endpoint=DUPLICATE_MANAGER_ORDER_PROPOSAL, error_code=BAD_REQUEST, message=str(exc)) from exc


@router.patch(
    "/{order_id}/proposals/{proposal_id}",
    response_model=ManagerOrderDetailResponse,
    operation_id=PATCH_MANAGER_ORDER_PROPOSAL,
)
async def patch_manager_order_proposal(
    order_id: int,
    proposal_id: int,
    payload: OrderProposalUpdatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderProposalCommandService.update_order_proposal(
            session,
            order_id,
            proposal_id,
            payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(status_code=400, endpoint=PATCH_MANAGER_ORDER_PROPOSAL, error_code=BAD_REQUEST, message=str(exc)) from exc


@router.post(
    "/{order_id}/proposals/{proposal_id}/archive",
    response_model=ManagerOrderDetailResponse,
    operation_id=ARCHIVE_MANAGER_ORDER_PROPOSAL,
)
async def archive_manager_order_proposal(
    order_id: int,
    proposal_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderProposalCommandService.update_order_proposal(
            session,
            order_id,
            proposal_id,
            OrderProposalUpdatePayload(is_archived=True),
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(status_code=400, endpoint=ARCHIVE_MANAGER_ORDER_PROPOSAL, error_code=BAD_REQUEST, message=str(exc)) from exc


@router.post(
    "/{order_id}/proposals/{proposal_id}/select",
    response_model=ManagerOrderDetailResponse,
    operation_id=SELECT_MANAGER_ORDER_PROPOSAL,
)
async def select_manager_order_proposal(
    order_id: int,
    proposal_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderProposalCommandService.select_order_proposal(
            session,
            order_id,
            proposal_id,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(status_code=400, endpoint=SELECT_MANAGER_ORDER_PROPOSAL, error_code=BAD_REQUEST, message=str(exc)) from exc


@router.post(
    "/{order_id}/documents/{doc_type}",
    response_model=ManagerOrderDocumentResponse,
    operation_id=GENERATE_MANAGER_ORDER_DOCUMENT,
)
async def generate_manager_order_document(
    order_id: int,
    doc_type: str,
    payload: Optional[ManagerOrderDocumentGeneratePayload] = Body(None),
    document_template_id: Optional[int] = Query(None, description="Managed document template ID"),
    template_id: Optional[str] = Query(None, description="Google Drive template file ID"),
    contract_date: Optional[str] = Query(None, description="Document/contract date as ISO datetime"),
    proposal_id: Optional[int] = Query(None, description="Order proposal ID for generated commercial offer"),
    base_document_id: Optional[int] = Query(None, description="Order document ID used as basis for closing documents; 0 means selected open customer contract"),
    scope_customer_branch_id: Optional[int] = Query(None, description="Customer branch/object for scoped closing document"),
    scope_title: Optional[str] = Query(None, description="Human-readable object title for scoped closing document"),
    scope_address: Optional[str] = Query(None, description="Object address override for scoped closing document"),
    scope_service_line_ids: Optional[List[int]] = Query(None, description="Order service line IDs included in scoped closing document"),
    scope_service_line_quantities: Optional[str] = Query(None, description="JSON map/list of service line quantities included in scoped closing document"),
    scope_product_line_ids: Optional[List[int]] = Query(None, description="Order product line IDs included in scoped closing document"),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    draft_conditions_requested = payload is not None and payload.additional_conditions is not None
    try:
        parsed_contract_date = None
        if contract_date:
            from datetime import datetime
            parsed_contract_date = datetime.fromisoformat(contract_date.replace("Z", "+00:00"))
        return await DocumentService.generate_manager_order_document(
            session=session,
            order_id=order_id,
            doc_type=doc_type,
            document_template_id=document_template_id,
            template_id=template_id,
            contract_date=parsed_contract_date,
            proposal_id=proposal_id,
            base_document_id=base_document_id,
            scope_customer_branch_id=scope_customer_branch_id,
            scope_title=scope_title,
            scope_address=scope_address,
            scope_service_line_ids=scope_service_line_ids,
            scope_service_line_quantities=scope_service_line_quantities,
            scope_product_line_ids=scope_product_line_ids,
            additional_conditions=payload.additional_conditions if payload else None,
            tenant_scope=tenant_scope,
        )
    except OrderDocumentsLockedError as exc:
        raise manager_http_error(
            status_code=409,
            endpoint=GENERATE_MANAGER_ORDER_DOCUMENT,
            error_code=ORDER_DOCUMENTS_LOCKED,
            message=str(exc),
        ) from exc
    except ValueError as exc:
        if draft_conditions_requested:
            await session.rollback()
        raise manager_http_error(
            status_code=400,
            endpoint=GENERATE_MANAGER_ORDER_DOCUMENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    except Exception as exc:
        await session.rollback()
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderPaymentCommandService.add_payment(
            session,
            order_id,
            payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        is_not_found = str(exc) == "Order not found"
        raise manager_http_error(
            status_code=404 if is_not_found else 400,
            endpoint=ADD_MANAGER_ORDER_PAYMENT,
            error_code=ORDER_NOT_FOUND if is_not_found else BAD_REQUEST,
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderPaymentCommandService.delete_payment(
            session,
            order_id,
            payment_id,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        is_not_found = str(exc) == "Order not found"
        raise manager_http_error(
            status_code=404 if is_not_found else 400,
            endpoint=DELETE_MANAGER_ORDER_PAYMENT,
            error_code=ORDER_NOT_FOUND if is_not_found else BAD_REQUEST,
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderWorkStageCommandService.add_order_stage(
            session,
            order_id,
            payload,
            tenant_scope=tenant_scope,
        )
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderWorkStageCommandService.update_order_stage(
            session,
            order_id,
            stage_id,
            payload,
            tenant_scope=tenant_scope,
        )
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await OrderWorkStageCommandService.delete_order_stage(
            session,
            order_id,
            stage_id,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(status_code=400, endpoint=DELETE_MANAGER_ORDER_STAGE, error_code=BAD_REQUEST, message=str(exc)) from exc


@router.delete(
    "/{order_id}",
    response_model=dict,
    operation_id=DELETE_MANAGER_ORDER,
)
async def delete_manager_order(
    order_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        await OrderService.delete_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        return {"ok": True}
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=DELETE_MANAGER_ORDER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    except Exception as exc:
        raise manager_http_error(
            status_code=500,
            endpoint=DELETE_MANAGER_ORDER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
