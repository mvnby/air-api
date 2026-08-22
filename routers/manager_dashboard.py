from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    GET_DASHBOARD_STATS,
    GET_MANAGER_DASHBOARD_OVERVIEW,
)
from schemas import DashboardStatsResponse
from schemas_dashboard import DashboardOverviewResponse
from services.dashboard_overview_service import DashboardOverviewService
from services.stats_service import StatsService

router = APIRouter(
    prefix="/api/manager/dashboard",
    tags=["manager_dashboard"],
)


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    operation_id=GET_MANAGER_DASHBOARD_OVERVIEW,
)
async def get_dashboard_overview(
    session: AsyncSession = Depends(get_session),
    _: str = Depends(get_current_username),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    return await DashboardOverviewService().get_overview(
        session,
        tenant_scope=tenant_scope,
    )


@router.get(
    "/stats",
    response_model=DashboardStatsResponse,
    operation_id=GET_DASHBOARD_STATS,
)
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_session),
    _: str = Depends(get_current_username),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    service = StatsService()
    return await service.get_dashboard_stats(
        session,
        tenant_scope=tenant_scope,
    )
