"""Reliable staff notification outbox endpoints for the autonomous bot."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import (
    BotStaffNotificationAckRequest,
    BotStaffNotificationClaimRequest,
    BotStaffNotificationClaimResponse,
    BotStaffNotificationItem,
    BotStaffNotificationMutationResponse,
    BotStaffNotificationNackRequest,
    BotStaffNotificationRenewRequest,
)
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from services.bot_staff_notification_api_service import (
    BotStaffNotificationApiService,
    BotStaffNotificationLeaseConflictError,
    BotStaffNotificationNotFoundError,
)


router = APIRouter(
    prefix="/api/internal/bot/v1/staff-notifications",
    tags=["internal bot v1 staff notifications"],
    dependencies=[Depends(require_bot_api_token)],
)


def _mutation_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BotStaffNotificationNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/claim",
    response_model=BotStaffNotificationClaimResponse,
    operation_id="claim_internal_bot_staff_notification_v1",
)
async def claim_staff_notification(
    payload: BotStaffNotificationClaimRequest,
    session: AsyncSession = Depends(get_session),
) -> BotStaffNotificationClaimResponse:
    """
    Claim the next eligible staff-bot Telegram outbox delivery for a worker, recovering
    expired leases and materializing pending outbox events. Returns notification=null when
    none is claimable. The service checks recipient/stage freshness; this endpoint uses
    worker identity, not a caller Telegram actor.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    notification = await BotStaffNotificationApiService.claim(
        session,
        **payload.model_dump(),
    )
    return BotStaffNotificationClaimResponse(
        notification=(
            BotStaffNotificationItem.model_validate(notification)
            if notification is not None
            else None
        )
    )


@router.post(
    "/{delivery_id}/renew",
    response_model=BotStaffNotificationMutationResponse,
    operation_id="renew_internal_bot_staff_notification_v1",
)
async def renew_staff_notification(
    delivery_id: str,
    payload: BotStaffNotificationRenewRequest,
    session: AsyncSession = Depends(get_session),
) -> BotStaffNotificationMutationResponse:
    """
    Extend a claimed staff notification lease using the worker identity and lease token.
    Missing delivery returns 404; a lost/mismatched lease returns 409. This does not send or
    acknowledge the Telegram message.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotStaffNotificationApiService.renew(
            session,
            delivery_id=delivery_id,
            **payload.model_dump(),
        )
    except (BotStaffNotificationNotFoundError, BotStaffNotificationLeaseConflictError) as exc:
        raise _mutation_error(exc) from exc
    return BotStaffNotificationMutationResponse.model_validate(result.__dict__)


@router.post(
    "/{delivery_id}/ack",
    response_model=BotStaffNotificationMutationResponse,
    operation_id="ack_internal_bot_staff_notification_v1",
)
async def ack_staff_notification(
    delivery_id: str,
    payload: BotStaffNotificationAckRequest,
    session: AsyncSession = Depends(get_session),
) -> BotStaffNotificationMutationResponse:
    """
    Record successful Telegram delivery under the current worker lease and supplied provider
    result. Missing delivery returns 404; lost/mismatched lease returns 409. The caller
    performs delivery; this HTTP operation updates outbox state.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotStaffNotificationApiService.ack(
            session,
            delivery_id=delivery_id,
            **payload.model_dump(),
        )
    except (BotStaffNotificationNotFoundError, BotStaffNotificationLeaseConflictError) as exc:
        raise _mutation_error(exc) from exc
    return BotStaffNotificationMutationResponse.model_validate(result.__dict__)


@router.post(
    "/{delivery_id}/nack",
    response_model=BotStaffNotificationMutationResponse,
    operation_id="nack_internal_bot_staff_notification_v1",
)
async def nack_staff_notification(
    delivery_id: str,
    payload: BotStaffNotificationNackRequest,
    session: AsyncSession = Depends(get_session),
) -> BotStaffNotificationMutationResponse:
    """
    Record a failed staff Telegram delivery under the current worker lease, applying the
    delivery service retry/failure decision. Missing delivery returns 404; lost/mismatched
    lease returns 409. Inspect returned status/next_attempt_at rather than assuming
    immediate retry.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotStaffNotificationApiService.nack(
            session,
            delivery_id=delivery_id,
            **payload.model_dump(),
        )
    except (BotStaffNotificationNotFoundError, BotStaffNotificationLeaseConflictError) as exc:
        raise _mutation_error(exc) from exc
    return BotStaffNotificationMutationResponse.model_validate(result.__dict__)
