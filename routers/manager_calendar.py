from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read assessment, installation and work-stage events for orders accessible in the current
    Manager tenant/storefront, plus tenant-scoped equipment-maintenance reminders without a
    storefront filter (type=equipment_maintenance, order_id=null). Overdue maintenance is
    displayed today in start while date retains the original due date; the requested range
    filters its display start. start and end are required ISO datetimes; boundaries are
    inclusive and the response is an unpaginated list. Current implementation strips timezone
    offsets without converting wall-clock values, so send dates in the stored scheduling time
    convention. start greater than end returns 400. This does not include personal tasks or
    modify schedules.
    """
    try:
        return await OrderService.get_calendar_events(
            session,
            start,
            end,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=GET_MANAGER_CALENDAR_EVENTS,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
