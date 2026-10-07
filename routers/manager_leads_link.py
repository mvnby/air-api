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
    """
    Preview the selected existing order as a link target for an accessible email new_lead in
    the current tenant/storefront. Does not link, copy attachments or run the full
    unworked-source checks used by commit. Missing source/target returns 404,
    invalid/self/new-lead target 422 and another existing link 409. See the [incoming triage
    contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Link an unworked email new_lead to an existing accessible order in the current
    tenant/storefront, recording actor/time and mirroring private attachment links while
    retaining the source. Paid or previously sent sources are rejected (422); missing
    context returns 404, different existing link 409 and unavailable needed mailbox original
    503. Same target can reuse the existing link result; no caller replay key is supplied.
    The target may be closed. See the [incoming triage
    contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Remove an accessible email lead’s link in the current tenant/storefront and archive only
    attachment links mirrored from that source into the target. Source files and target
    business record remain. Returns the former target ID; missing source/link returns 404,
    including repeated unlink. Does not delete original attachments or restore a separate
    manual archive decision. See the [incoming triage
    contract](https://github.com/mvnby/air-api/blob/main/docs/incoming-triage-workspace.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
