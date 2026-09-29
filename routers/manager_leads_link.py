"""Explicit Manager resolution of follow-up email leads."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import AuthenticatedUser, get_current_manager_tenant_scope, require_manager_access
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    LINK_MANAGER_EMAIL_LEAD_TO_ORDER,
    PREVIEW_MANAGER_EMAIL_LEAD_LINK_TARGET,
    UNLINK_MANAGER_EMAIL_LEAD_FROM_ORDER,
)
from schemas_email_lead_link import (
    EmailLeadLinkPayload,
    EmailLeadLinkResult,
    EmailLeadLinkTarget,
    EmailLeadUnlinkResult,
)
from services.email_lead_order_link_service import EmailLeadLinkError, EmailLeadOrderLinkService


router = APIRouter(prefix="/api/manager/leads/inbox", tags=["manager-leads-inbox"])


@router.get(
    "/{source_order_id}/link-target/{target_order_id}",
    response_model=EmailLeadLinkTarget,
    operation_id=PREVIEW_MANAGER_EMAIL_LEAD_LINK_TARGET,
)
async def preview_manager_email_lead_link_target(
    source_order_id: int,
    target_order_id: int,
    _: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> EmailLeadLinkTarget:
    try:
        target = await EmailLeadOrderLinkService.preview_target(
            session,
            source_order_id=source_order_id,
            target_order_id=target_order_id,
            tenant_scope=tenant_scope,
        )
    except EmailLeadLinkError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return EmailLeadLinkTarget.model_validate(target)


@router.post(
    "/{source_order_id}/link-to-order",
    response_model=EmailLeadLinkResult,
    operation_id=LINK_MANAGER_EMAIL_LEAD_TO_ORDER,
)
async def link_manager_email_lead_to_order(
    source_order_id: int,
    payload: EmailLeadLinkPayload,
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> EmailLeadLinkResult:
    try:
        result = await EmailLeadOrderLinkService.link(
            session,
            source_order_id=source_order_id,
            target_order_id=payload.target_order_id,
            linked_by=auth.username,
            tenant_scope=tenant_scope,
        )
    except EmailLeadLinkError as exc:
        await session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return EmailLeadLinkResult.model_validate(result)


@router.delete(
    "/{source_order_id}/linked-order",
    response_model=EmailLeadUnlinkResult,
    operation_id=UNLINK_MANAGER_EMAIL_LEAD_FROM_ORDER,
)
async def unlink_manager_email_lead_from_order(
    source_order_id: int,
    _: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
) -> EmailLeadUnlinkResult:
    try:
        target_order_id = await EmailLeadOrderLinkService.unlink(
            session, source_order_id=source_order_id, tenant_scope=tenant_scope,
        )
    except EmailLeadLinkError as exc:
        await session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return EmailLeadUnlinkResult(
        source_order_id=source_order_id, previous_target_order_id=target_order_id,
    )
