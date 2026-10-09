"""Manager business stages and manual price-enquiry/publication relationships."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username, require_manager_access
from models.tenancy import TenantScope
from schemas_leads_inbox import TenderWorkflowIdentity, TenderWorkflowLinkPayload, TenderWorkflowPayload, TenderWorkflowResponse
from services.leads_inbox_service import InboxError
from services.tender_workflow_service import TenderWorkflowService
from routers.manager_permission_policy import ManagerPermissionRoute

router = APIRouter(prefix="/api/manager/orders", tags=["manager-tender-workflow"],
    dependencies=[Depends(require_manager_access)], route_class=ManagerPermissionRoute)


async def _call(session, callback, **kwargs):
    try:
        return await callback(session, **kwargs)
    except InboxError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/{order_id}/tender-workflow", response_model=TenderWorkflowResponse, operation_id="get_manager_tender_workflow")
async def get_workflow(order_id: int, session: AsyncSession = Depends(get_session),
        tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """Read manual tender stage/current deadline and associated distinct Orders in the current tenant/storefront,
    including qualified and archived email/Bel tender sources. Source external IDs, statuses, archives,
    documents and proposals remain independent. Returns at most 100 latest stage/link audit events;
    reading neither marks an inbox record read nor creates associations. Missing/ineligible or foreign
    Order returns 404; a continuation email already linked to another Order returns 409.

    Requires authenticated Manager session/JWT, live membership and scoped order-read permission; see
    [Manager access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await _call(session, TenderWorkflowService.read, order_id=order_id, tenant_scope=tenant_scope)


@router.patch("/{order_id}/tender-workflow", response_model=TenderWorkflowResponse, operation_id="set_manager_tender_workflow")
async def set_workflow(order_id: int, payload: TenderWorkflowPayload, session: AsyncSession = Depends(get_session),
        tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope), username: str = Depends(get_current_username)):
    """Set the business stage and current stage deadline for an email/Bel tender Order in the current
    tenant/storefront, including qualified/archived sources. Audit author/time and before/after values;
    the importer cannot overwrite this separate manual context. Explicit null clears the current
    deadline; omission preserves it on the same stage and clears it on a stage change. Does not submit
    to a procurement platform or change Order status/archive. Missing/foreign Order returns 404,
    stage-role conflict on an existing association returns 409, demo mutation 403 and invalid stage
    or timezone-less deadline 422. Same-value repeat is idempotent; no replay receipt is provided.

    Requires authenticated Manager session/JWT, live membership and scoped order-update permission; see
    [Manager access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await _call(session, TenderWorkflowService.update, order_id=order_id, tenant_scope=tenant_scope, username=username, payload=payload)


@router.get("/{order_id}/tender-workflow/price-enquiries", response_model=list[TenderWorkflowIdentity], operation_id="list_manager_tender_price_enquiries")
async def candidates(order_id: int, search: str | None = Query(None, max_length=200), limit: int = Query(20, ge=1, le=100),
        session: AsyncSession = Depends(get_session), tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """Search previous email/Bel tender Orders only within the current tenant/storefront, including
    qualified and archived records. Include unmarked sources and explicitly marked price_request/
    price_sent sources; selecting an unmarked candidate requires an explicit stage command before
    association. Buyer/title similarity never creates a match. Search is at most 200 characters;
    limit is 1..100 (default 20), ordered newest first. Missing/foreign current Order returns 404,
    ineligible continuation email 409 and invalid query 422. Read-only and does not mark read.

    Requires authenticated Manager session/JWT, live membership and scoped order-read permission; see
    [Manager access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await _call(session, TenderWorkflowService.candidates, order_id=order_id, tenant_scope=tenant_scope, search=search, limit=limit)


@router.put("/{order_id}/tender-workflow/price-enquiry", response_model=TenderWorkflowResponse, operation_id="link_manager_tender_price_enquiry")
async def associate(order_id: int, payload: TenderWorkflowLinkPayload, session: AsyncSession = Depends(get_session),
        tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope), username: str = Depends(get_current_username)):
    """Associate a later email/Bel tender publication with one manually marked price_request/price_sent
    Order in the same tenant/storefront, including qualified/archived enquiries with different external
    IDs. Audit both identities and preserve their independent documents/proposals/status/archive.
    An unmarked publication gains announced stage and retains its source deadline. No automatic
    match or platform submission. Missing/foreign endpoint returns 404; self-link, role conflict,
    cycles/chains or replacing another link returns 409; demo mutation 403 and invalid payload 422.
    Repeating the same pair is idempotent without a replay receipt; remove the current link before
    selecting another price enquiry.

    Requires authenticated Manager session/JWT, live membership and scoped order-update permission; see
    [Manager access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await _call(session, TenderWorkflowService.associate, order_id=order_id, price_order_id=payload.price_order_id, tenant_scope=tenant_scope, username=username)


@router.delete("/{order_id}/tender-workflow/price-enquiry", response_model=TenderWorkflowResponse, operation_id="unlink_manager_tender_price_enquiry")
async def dissociate(order_id: int, session: AsyncSession = Depends(get_session),
        tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope), username: str = Depends(get_current_username)):
    """Remove only the publication's manual price-enquiry association in the current tenant/storefront.
    Audit both records and retain original identities, stages/deadlines, documents, proposals, status,
    archives and earlier history. Missing/foreign Order returns 404; ineligible continuation email or
    concurrently replaced association 409 and demo mutation 403. Repeating an already removed link
    is idempotent without a replay receipt.

    Requires authenticated Manager session/JWT, live membership and scoped order-update permission; see
    [Manager access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await _call(session, TenderWorkflowService.dissociate, order_id=order_id, tenant_scope=tenant_scope, username=username)
