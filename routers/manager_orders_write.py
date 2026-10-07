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
from services.order_delete_command_service import OrderDeleteCommandService
from services.order_payment_command_service import OrderPaymentCommandService
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_service import OrderService
from services.order_transfer_service import OrderTransferService
from services.order_update.command import OrderUpdateCommandService
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
    """
    Create an order in the current Manager tenant/storefront and return its detailed
    projection. Customer/object/product/service/executor relationships are validated by the
    command service; invalid context returns 400. This legacy creation has no caller
    idempotency receipt; repeating POST can create another order.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Set a scoped stage to canceled without needing order_id and return its stale-stage
    projection. Manager access is required; missing/inaccessible stage returns 404. Enqueues
    a cancellation notification only on a status change; this is distinct from deleting the
    stage.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Hard-delete a work stage accessible in the current tenant/storefront by stage_id and
    return its removed ID. Missing/inaccessible stage returns 404, including a repeat after
    deletion. Does not cancel the stage or use the cancellation notification command.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Patch supplied order/customer/commercial fields in the current Manager tenant/storefront
    and return the refreshed projection. Commercial line arrays replace the targeted
    proposal’s lines; line_proposal_id disambiguates empty arrays, and sent/accepted
    proposal lines cannot be overwritten. A won order cannot close with unpaid balance;
    closing lost can archive an otherwise unused customer. Missing order returns 404;
    invalid relationships/transitions return 400. No expected_version or idempotency receipt
    resolves concurrent field edits. See [order saving and proposal
    scope](https://github.com/mvnby/air-api/blob/main/docs/manager-order-autosave.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        data = await OrderUpdateCommandService.update_order_for_manager(
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
    """
    Validate an order transfer package and resolve customer/product matches in the current
    Manager tenant/storefront without committing imported orders. Inspect can_import and
    unresolved items/warnings; invalid package input returns 400. Product resolution remains
    separate from import commit.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Import a transfer package into the current Manager tenant/storefront after rerunning
    preview validation. Creates orders and related customer/object/line/stage/payment data
    according to service options; inspect warnings/skipped-payments counts. Unresolved
    products or invalid data return 400. No caller idempotency receipt is provided:
    repeating commit can create duplicate orders.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Create a draft proposal under an accessible order in the current Manager
    tenant/storefront, optionally copying an active proposal’s lines. Returns the refreshed
    order and recalculates financial projection. Missing source/order or invalid context
    returns 400; repeating POST can create another proposal.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Copy the selected active proposal into a new draft under its scoped order; the path
    proposal_id supplies the copy source. Returns the refreshed order. Missing/inaccessible
    source/order returns 400. Repeating POST creates another copy rather than replaying a
    receipt.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Patch supplied proposal name/status/order/archive metadata under the current
    tenant/storefront order. Ready-to-send requires nonempty lines and positive total;
    archived selected proposals can select an active replacement. Recalculates order
    financial/status projection. Missing proposal/order or invalid state returns 400.
    Commercial lines are edited through the order command.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Archive a proposal under the current tenant/storefront order. If selected, chooses an
    active replacement when available and refreshes order financial/status projection.
    Missing proposal/order or invalid context returns 400. Archiving retains the proposal
    rather than hard-deleting its history.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Select an active proposal belonging to an accessible scoped order, unselect siblings and
    refresh order status/financial projection. Missing/archived/foreign-order proposal
    returns 400. Selection does not copy or issue a document.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Generate or reuse a legacy Google document for the current tenant/storefront order using
    the selected proposal, template and basis/scope. Closed orders return 409; invalid
    type/basis/line selection/date returns 400 and unexpected generation failure 500.
    Proposal/closing document kinds create new records; eligible legacy records of other
    kinds can be reused by template. Supplied additional_conditions updates order conditions
    and forces a new document. No generic idempotency receipt is provided. Native lifecycle
    endpoints are separate. See the [document lifecycle
    contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Record a payment on an accessible scoped order and refresh financial totals, returning
    its payment list. Non-BYN currency must match the order target currency. Missing order
    returns 404; invalid type/currency returns 400. POST is additive with no caller
    idempotency receipt; reconcile before retrying.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Remove a payment from an accessible scoped order and refresh affected finances. For a
    bank-linked payment, removes all payments from that receipt across accessible orders and
    returns the receipt to requires_review; cross-tenant allocations are refused. Missing
    order returns 404; missing/wrong-order payment or invalid allocation returns 400.
    Returns the selected order’s remaining payment list.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Create a work stage under the current tenant/storefront order, checking executor
    assignment and scheduling and enqueuing relevant staff notification events. Returns the
    refreshed order; invalid/missing order or executor context returns 400. Repeating POST
    can add another stage.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Patch a stage belonging to the specified scoped order. Validates changed executor and
    normalizes times/status; assignment, rescheduling and cancellation can enqueue staff
    notification events. Completion of all stages with outstanding balance can put the order
    on hold. Missing stage or invalid context returns 400; returns the refreshed order.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Hard-delete a stage belonging to the specified order in the current tenant/storefront
    and return the refreshed order projection. Missing/wrong-order stage returns 400,
    including a repeat after deletion. This is not the direct stage-cancellation workflow.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Hard-delete an accessible scoped order together with
    proposal/line/stage/executor/payment/document rows, enqueueing provider document
    cleanup. Bank receipt and outgoing-email histories are detached for audit rather than
    removed. Missing order/service validation returns 400; unexpected deletion failure 500.
    No closed-order document lock is applied by this order-delete command; repeat after
    deletion is not receipt replay.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        await OrderDeleteCommandService.delete_order(
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
