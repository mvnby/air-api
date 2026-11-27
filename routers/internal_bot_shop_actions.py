"""Manager commands from the Telegram equipment basket."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot_shop_actions import BotShopOfferRequest, BotShopOfferResponse, BotShopOrderRequest, BotShopOrderResponse
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from services.bot_api_access import BotUseCaseAccessDeniedError, require_bot_manager_actor
from services.bot_business_context import bind_bot_business_context
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable
from services.bot_shop_checkout import create_shop_order, publish_shop_offer


router = APIRouter(
    prefix="/api/internal/bot/v1/shop", tags=["internal bot v1"],
    dependencies=[Depends(require_bot_api_token), Depends(bind_bot_business_context, scope="function")],
)


async def _actor(session, telegram_id):
    try:
        actor, _ = await require_bot_manager_actor(session, telegram_id)
        return actor
    except BotUseCaseAccessDeniedError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/orders", response_model=BotShopOrderResponse, operation_id="create_internal_bot_shop_order_v1")
async def shop_order(payload: BotShopOrderRequest, session: AsyncSession = Depends(get_session)):
    """Create a negotiation order with current storefront prices, quantities and either one proposal or alternatives.
    Requires the Bot service bearer, a live manager and the issued writable company/site version. Replaying the
    same intent for this manager and site returns the original order ID. Unavailable equipment returns 422;
    unauthorized membership and stale context return 403 and 409."""
    actor = await _actor(session, payload.telegram_id)
    try:
        return BotShopOrderResponse(id=await create_shop_order(session, actor.tenant_scope, actor.staff_user_id, payload))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/offers", response_model=BotShopOfferResponse, operation_id="publish_internal_bot_shop_offer_v1")
async def shop_offer(payload: BotShopOfferRequest, session: AsyncSession = Depends(get_session)):
    """Publish a seven-day personal equipment offer only on the selected storefront's verified primary domain.
    Requires the Bot bearer, a live manager and the current writable company/site version. Resolve current prices
    and publication eligibility before creating the immutable public snapshot. A retry returns the original active
    link; withdrawn, expired, unavailable or unpriced selections cannot be republished with that key."""
    actor = await _actor(session, payload.telegram_id)
    try:
        return await publish_shop_offer(session, actor, payload)
    except PublicWriteIdempotencyConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except PublicWriteIdempotencyUnavailable as exc:
        raise HTTPException(503, "Повторите создание ссылки.") from exc
