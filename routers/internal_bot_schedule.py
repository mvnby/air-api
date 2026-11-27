"""Read-only calendar for Telegram staff managers."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot_schedule import BotScheduleRequest, BotScheduleResponse
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from services.bot_api_access import BotUseCaseAccessDeniedError
from services.bot_business_context import bind_bot_business_context
from services.bot_schedule_service import read_manager_schedule


router = APIRouter(
    prefix="/api/internal/bot/v1",
    tags=["internal bot v1"],
    dependencies=[Depends(require_bot_api_token), Depends(bind_bot_business_context, scope="function")],
)


@router.post("/calendar/schedule", response_model=BotScheduleResponse, operation_id="get_internal_bot_schedule_v1")
async def get_internal_bot_schedule(
    payload: BotScheduleRequest,
    session: AsyncSession = Depends(get_session),
) -> BotScheduleResponse:
    """
    Read today and tomorrow in Europe/Minsk for the authenticated bot's Telegram
    manager. Order appointments use the selected storefront. Maintenance reminders
    belong to the customer's tenant and move to today when overdue. Both days are
    returned even when empty. The call requires an active manager membership (403)
    and the current company/site version (409 on a switch).

    Access: service Bearer BOT_API_TOKEN and the operation-specific Telegram actor
    checks are required. See the [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        return await read_manager_schedule(session, telegram_id=payload.telegram_id)
    except BotUseCaseAccessDeniedError as exc:
        raise HTTPException(403, str(exc)) from exc
