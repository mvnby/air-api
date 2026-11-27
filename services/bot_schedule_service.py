"""Read the same appointments and preventive-maintenance reminders as Manager."""

from datetime import datetime, time, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot_schedule import BotScheduleEvent, BotScheduleResponse
from core.config import settings
from schemas_manager_orders import CalendarEventResponse, CalendarEventType
from services.bot_api_access import BotUseCaseAccessDeniedError, require_bot_manager
from services.order_service import OrderService


MINSK = ZoneInfo("Europe/Minsk")


def _schedule_event(event: CalendarEventResponse, company_query: str) -> BotScheduleEvent:
    reminder = event.type == CalendarEventType.EQUIPMENT_MAINTENANCE
    # The maintenance anchor can have a time, but it never books a visit.
    return BotScheduleEvent(
        id=event.id,
        date=event.start.date(),
        time=None if reminder else event.start.strftime("%H:%M"),
        type=event.type.value,
        title=event.title,
        status=event.status,
        customer_name=event.customer_name,
        customer_phone=event.customer_phone,
        address=event.address,
        order_id=event.order_id,
        order_url=(
            f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/{event.order_id}?{company_query}"
            if event.order_id is not None else None
        ),
        due_date=event.date.date() if reminder else None,
    )


async def read_manager_schedule(
    session: AsyncSession, *, telegram_id: int, now: datetime | None = None,
) -> BotScheduleResponse:
    context = await require_bot_manager(session, telegram_id)
    selection = context.selection
    if selection is None:
        raise BotUseCaseAccessDeniedError("A selected staff company/site is required")

    moment = now or datetime.now(MINSK)
    if moment.tzinfo is not None:
        moment = moment.astimezone(MINSK).replace(tzinfo=None)
    today = moment.date()
    tomorrow = today + timedelta(days=1)
    events = await OrderService.get_calendar_events(
        session,
        datetime.combine(today, time.min),
        datetime.combine(tomorrow, time.max),
        tenant_scope=selection.scope,
        now=moment,
    )
    company_query = urlencode({"company": selection.tenant_id, "site": selection.storefront_slug})
    events.sort(key=lambda event: (
        event.start.date(), event.type != CalendarEventType.EQUIPMENT_MAINTENANCE, event.date, event.id,
    ))
    return BotScheduleResponse(
        today=today, tomorrow=tomorrow, events=[_schedule_event(event, company_query) for event in events],
    )
