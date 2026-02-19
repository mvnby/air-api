from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import GET_MANAGER_CALENDAR_EVENTS
from schemas import CalendarEventResponse
from services.order_service import OrderService

router = APIRouter(prefix="/api/manager/calendar", tags=["manager-calendar"])


@router.get("/events", response_model=List[CalendarEventResponse], operation_id=GET_MANAGER_CALENDAR_EVENTS)
async def get_manager_calendar_events(
    start: datetime = Query(..., description="Start date (ISO format)"),
    end: datetime = Query(..., description="End date (ISO format)"),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    """
    Get calendar events (assessments and installations) within a date range.
    """
    return await OrderService.get_calendar_events(session, start, end)
