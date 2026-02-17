from fastapi import APIRouter, Request, Depends
from core.database import async_session_maker
from core.security import check_admin_session
from routers import admin_docs
from routers import admin_import
from routers import admin_media
from routers import admin_orders
from routers import admin_schedule

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(admin_docs.router)
router.include_router(admin_import.router)
router.include_router(admin_media.router)
router.include_router(admin_orders.router)
router.include_router(admin_schedule.router)

@router.get("/stats")
async def get_dashboard_stats(
    request: Request,
    authenticated: bool = Depends(check_admin_session)
):
    """
    Dashboard stats endpoint - uses session-based auth (called from admin panel AJAX).
    """
    from services.analytics_service import AnalyticsService
    async with async_session_maker() as session:
        return await AnalyticsService.get_dashboard_stats(session)
