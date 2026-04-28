from typing import Optional

from fastapi import APIRouter, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from services.admin_schedule_service import AdminScheduleService


router = APIRouter(tags=["admin-schedule"])


@router.get("/api/admin/installers/search")
async def search_installers(
    q: str = "",
    username: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    """
    Search installers for Select2.
    """
    return await AdminScheduleService.search_installers(session, q=q)


@router.get("/calendar/events")
async def get_calendar_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    username: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    """
    Get events for FullCalendar (Orders with Installation or Assessment dates).
    """
    return await AdminScheduleService.get_calendar_events(session, start=start, end=end)
