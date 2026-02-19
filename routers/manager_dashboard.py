from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from schemas import DashboardStatsResponse
from services.stats_service import StatsService

router = APIRouter(
    prefix="/api/manager/dashboard",
    tags=["manager_dashboard"]
)

@router.get("/stats", response_model=DashboardStatsResponse, operation_id="get_dashboard_stats")
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_session),
    _: str = Depends(get_current_username)
):
    service = StatsService()
    return await service.get_dashboard_stats(session)

