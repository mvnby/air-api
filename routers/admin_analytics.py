from fastapi import APIRouter, Depends, Request

from core.database import async_session_maker
from core.security import check_admin_session


router = APIRouter(tags=["admin-analytics"])


@router.get("/stats")
async def get_dashboard_stats(
    request: Request,
    authenticated: bool = Depends(check_admin_session),
):
    """
    Dashboard stats endpoint - uses session-based auth (called from admin panel AJAX).
    """
    from services.analytics_service import AnalyticsService

    async with async_session_maker() as session:
        return await AnalyticsService.get_dashboard_stats(session)
