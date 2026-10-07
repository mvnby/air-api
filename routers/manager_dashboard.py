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
    """
    Build the current storefront's Manager dashboard for the current month and comparable
    previous-month window. Includes canonical Lead counts, revenue, sales, installation stages,
    funnel and configured external marketing/search indicators. Follow-ups and receivables are
    current-state snapshots without previous-period values. Tenant/storefront scope comes from
    authenticated Manager access; provider availability is represented in the dashboard result.
    This is an aggregate report, not a ledger export.
    """
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
    """
    Read the legacy Manager dashboard summary scoped to the current storefront and accessible
    tenant customers. Closed-deal amount and new-lead counts use Order rows created since the
    start of the current month; these differ from the canonical Lead funnel in /overview. Also
    returns bounded follow-up and tenant contract-expiry summaries; platform-wide bank-receipt
    review appears only for system-tenant access. Requires Manager access; does not modify
    orders or allocate payments.
    """
    service = StatsService()
    return await service.get_dashboard_stats(
        session,
        tenant_scope=tenant_scope,
    )
