from fastapi import APIRouter, Depends, Query

from core.manager_telemetry import ManagerTelemetryService
from core.security import get_current_username
from routers.manager_operation_ids import GET_MANAGER_CRM_HEALTH_REPORT
from schemas import ManagerCrmHealthReportResponse


router = APIRouter(prefix="/api/manager/crm", tags=["manager-crm"])


@router.get(
    "/health-report",
    response_model=ManagerCrmHealthReportResponse,
    operation_id=GET_MANAGER_CRM_HEALTH_REPORT,
)
async def get_manager_crm_health_report(
    hours: int = Query(24, ge=1, le=24 * 14),
    _user: str = Depends(get_current_username),
):
    return ManagerTelemetryService.get_report(hours=hours)

