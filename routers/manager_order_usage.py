from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context, require_manager_access
from routers.manager_operation_ids import RECORD_MANAGER_ORDER_USAGE, GET_MANAGER_ORDER_USAGE
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_order_usage import (
    OrderUsageAccepted, OrderUsageBatch, OrderUsageParty, OrderUsageReport,
    OrderUsageViewport, OrderUsageWorkflow,
)
from services.manager_content_ai_limiter import ManagerContentAILimiter, ManagerContentAIRateLimitError
from services.order_workspace_usage_service import OrderWorkspaceUsageService

router = APIRouter(
    prefix="/api/manager/order-workspace-usage", tags=["manager-order-usage"],
    dependencies=[Depends(require_manager_access)], route_class=ManagerPermissionRoute,
)
# A separate instance reuses the existing bounded request/concurrency guard;
# usage reporting never consumes the content-AI quota.
_usage_limiter = ManagerContentAILimiter(max_requests=30, max_concurrent=4)


@router.post("/batch", response_model=OrderUsageAccepted, operation_id=RECORD_MANAGER_ORDER_USAGE)
async def record_manager_order_usage(
    payload: OrderUsageBatch,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> OrderUsageAccepted:
    """
    Add a bounded batch of order-workspace UX aggregate events in the current
    tenant/storefront. Manager access is required. Aggregates contain permitted event labels
    rather than customer/order field content. In-process rate/concurrency protection returns
    429 with Retry-After. This is additive and has no replay receipt: blindly retrying can
    double-count. See [usage
    boundaries](https://github.com/mvnby/air-api/blob/main/docs/order-workspace-usability.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    scope = auth.tenant_scope()
    try:
        async with _usage_limiter.limit(f"{scope.tenant_id}:{auth.staff_user_id or auth.username}"):
            accepted = await OrderWorkspaceUsageService.record(session, scope, payload)
    except ManagerContentAIRateLimitError as error:
        raise HTTPException(429, "Слишком частая отправка статистики", headers={"Retry-After": str(error.retry_after)}) from error
    return OrderUsageAccepted(accepted=accepted)


@router.get("/daily", response_model=OrderUsageReport, operation_id=GET_MANAGER_ORDER_USAGE)
async def get_manager_order_usage(
    days: int = Query(default=30, ge=1, le=90),
    workflow: OrderUsageWorkflow | None = None,
    party_kind: OrderUsageParty | None = None,
    viewport: OrderUsageViewport | None = None,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> OrderUsageReport:
    """
    Read daily aggregate UX counts for the current tenant/storefront over 1–90 days and
    optional workflow/party/viewport filters. Requires owner/admin access via route policy.
    Returns aggregated counters, not individual employee click histories. See [usage
    boundaries](https://github.com/mvnby/air-api/blob/main/docs/order-workspace-usability.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await OrderWorkspaceUsageService.report(
        session, auth.tenant_scope(), days=days,
        workflow=workflow, party_kind=party_kind, viewport=viewport,
    )
