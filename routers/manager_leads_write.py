from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, LEAD_NOT_FOUND
from core.manager_telemetry import ManagerTelemetryService
from core.security import get_current_manager_tenant_scope, get_current_username
from routers.manager_operation_ids import (
    CREATE_MANAGER_LEAD,
    MARK_MANAGER_LEAD_LOST,
    PATCH_MANAGER_LEAD,
    QUALIFY_MANAGER_LEAD,
)
from schemas import (
    LeadCreatePayload,
    LeadLossPayload,
    LeadQualifyPayload,
    LeadQualifyResponse,
    LeadResponse,
    LeadUpdatePayload,
)
from services.lead_command_service import LeadCommandService
from services.tenant_scope_service import TenantScope


router = APIRouter(prefix="/api/manager/leads", tags=["manager-leads"])


@router.post("", response_model=LeadResponse, operation_id=CREATE_MANAGER_LEAD)
async def create_manager_lead(
    payload: LeadCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Create a raw Lead in new state in the current tenant/storefront, retaining
    contact/source/request/follow-up data without creating a customer/order. Blank request
    or invalid source/segment returns 400. No caller idempotency receipt is provided:
    repeating POST can create another Lead.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await LeadCommandService.create_lead(
            session=session,
            payload=payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_LEAD,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.patch("/{lead_id}", response_model=LeadResponse, operation_id=PATCH_MANAGER_LEAD)
async def patch_manager_lead(
    lead_id: int,
    payload: LeadUpdatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Patch supplied fields of a raw Lead in the current tenant/storefront and increment its
    version. Omitted fields remain unchanged; terminal qualified/lost/spam statuses require
    dedicated commands. Missing Lead returns 404; invalid request/status/source/segment
    returns 400. This patch does not enforce expected_version or provide a replay receipt,
    even though it increments version.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        lead = await LeadCommandService.update_lead(
            session=session,
            lead_id=lead_id,
            payload=payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_LEAD,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if not lead:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_LEAD,
            error_code=LEAD_NOT_FOUND,
        )
    return lead


@router.post("/{lead_id}/qualify", response_model=LeadQualifyResponse, operation_id=QUALIFY_MANAGER_LEAD)
async def qualify_manager_lead(
    lead_id: int,
    payload: LeadQualifyPayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Qualify a raw Lead in the current tenant/storefront by explicitly selecting or safely
    matching/creating a customer and branch, then creating an order and transferring
    applicable lead data. With an explicit scenario the order enters negotiation; otherwise
    it remains new_lead. Archived/lost/spam, ambiguous customer matches or invalid
    branch/scenario return 400; missing Lead 404. An already qualified Lead with its
    accessible converted order returns that order with order_created=false; no generic
    caller receipt is supplied.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    ManagerTelemetryService.record_qualify_attempt(endpoint=QUALIFY_MANAGER_LEAD, payload=payload)
    try:
        result = await LeadCommandService.qualify_lead(
            session=session,
            lead_id=lead_id,
            payload=payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=QUALIFY_MANAGER_LEAD,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if not result:
        raise manager_http_error(
            status_code=404,
            endpoint=QUALIFY_MANAGER_LEAD,
            error_code=LEAD_NOT_FOUND,
        )
    ManagerTelemetryService.record_qualify_success(endpoint=QUALIFY_MANAGER_LEAD, payload=payload)
    return result


@router.post("/{lead_id}/mark-lost", response_model=LeadResponse, operation_id=MARK_MANAGER_LEAD_LOST)
async def mark_manager_lead_lost(
    lead_id: int,
    payload: LeadLossPayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Mark a raw Lead in the current tenant/storefront lost or spam, retain/set loss reason,
    clear the follow-up date and increment version. Missing Lead returns 404; unsupported
    terminal status returns 400. This command has no expected_version precondition or replay
    receipt and does not archive a linked customer or delete source data.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        result = await LeadCommandService.mark_lead_lost(
            session=session,
            lead_id=lead_id,
            payload=payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=MARK_MANAGER_LEAD_LOST,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if not result:
        raise manager_http_error(
            status_code=404,
            endpoint=MARK_MANAGER_LEAD_LOST,
            error_code=LEAD_NOT_FOUND,
        )
    return result
