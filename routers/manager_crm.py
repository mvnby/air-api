from fastapi import APIRouter, Depends, Query

from core.manager_telemetry import ManagerTelemetryService
from core.security import get_current_username
from routers.manager_operation_ids import GET_MANAGER_CRM_HEALTH_REPORT
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import ManagerCrmHealthReportResponse


router = APIRouter(
    prefix="/api/manager/crm",
    tags=["manager-crm"],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/health-report",
    response_model=ManagerCrmHealthReportResponse,
    operation_id=GET_MANAGER_CRM_HEALTH_REPORT,
)
async def get_manager_crm_health_report(
    hours: int = Query(24, ge=1, le=24 * 14),
    _user: str = Depends(get_current_username),
):
    """
    Read in-process Manager API error and qualification telemetry over 1 hour–14 days. Route
    policy requires system-tenant Manager access because these aggregates are platform-wide
    rather than tenant CRM records. This is a diagnostic snapshot, not durable business
    history or proof of database health.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return ManagerTelemetryService.get_report(hours=hours)
