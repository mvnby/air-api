from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context, require_manager_access
from routers.manager_operation_ids import GET_MANAGER_CATALOG_USAGE, RECORD_MANAGER_CATALOG_USAGE
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_catalog_usage import (
    CatalogUsageAccepted, CatalogUsageAction, CatalogUsageBatch, CatalogUsageDevice,
    CatalogUsageLayoutVersion, CatalogUsageOutcome, CatalogUsageReport,
)
from services.catalog_workspace_usage_service import CatalogWorkspaceUsageService
from services.manager_content_ai_limiter import ManagerContentAILimiter, ManagerContentAIRateLimitError


router = APIRouter(
    prefix="/api/manager/catalog-usage", tags=["manager-catalog-usage"],
    dependencies=[Depends(require_manager_access)], route_class=ManagerPermissionRoute,
)
_usage_limiter = ManagerContentAILimiter(max_requests=30, max_concurrent=4)


@router.post("/batch", response_model=CatalogUsageAccepted, operation_id=RECORD_MANAGER_CATALOG_USAGE)
async def record_manager_catalog_usage(
    payload: CatalogUsageBatch,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(get_current_auth_context),
) -> CatalogUsageAccepted:
    """
    Add batched UI action counters to platform-wide daily aggregates in Europe/Minsk and
    prune data older than the 90-day retention window. Payload contains action dimensions
    rather than search/product/customer content. No idempotency receipt exists: replay
    counts events again. Per-actor rate/concurrency limits may return 429 with Retry-After.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [catalog
    workspace](https://github.com/mvnby/air-api/blob/main/docs/catalog-management-workspace.md).
    """
    try:
        async with _usage_limiter.limit(f"catalog-usage:{auth.staff_user_id or auth.username}"):
            accepted = await CatalogWorkspaceUsageService.record(session, payload)
    except ManagerContentAIRateLimitError as error:
        raise HTTPException(429, "Слишком частая отправка статистики", headers={"Retry-After": str(error.retry_after)}) from error
    return CatalogUsageAccepted(accepted=accepted)


@router.get("/daily", response_model=CatalogUsageReport, operation_id=GET_MANAGER_CATALOG_USAGE)
async def get_manager_catalog_usage(
    days: int = Query(default=30, ge=1, le=90),
    layout_version: CatalogUsageLayoutVersion | None = None,
    device: CatalogUsageDevice | None = None,
    action: CatalogUsageAction | None = None,
    outcome: CatalogUsageOutcome | None = None,
    session: AsyncSession = Depends(get_session),
) -> CatalogUsageReport:
    """
    Read platform-wide daily catalog-workspace telemetry over 1–90 days, optionally filtered
    by layout, device, action or outcome. Dates use Europe/Minsk; the report is aggregate
    counters, not individual users or recordings. Reading does not enable event collection.

    Access and scope: system-tenant Manager access and analytics.manage capability are
    required; aggregates are platform-wide. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [catalog
    workspace](https://github.com/mvnby/air-api/blob/main/docs/catalog-management-workspace.md).
    """
    return await CatalogWorkspaceUsageService.report(
        session, days=days, layout_version=layout_version, device=device,
        action=action, outcome=outcome,
    )
