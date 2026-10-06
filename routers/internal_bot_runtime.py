"""Private durable runtime primitives for the independently deployed bot."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import (
    BotFsmStateGetRequest,
    BotFsmStateResponse,
    BotFsmStateUpdateRequest,
    BotRuntimeLeaseRequest,
    BotRuntimeLeaseResponse,
)
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from services.bot_runtime_api_service import BotRuntimeApiService


router = APIRouter(
    prefix="/api/internal/bot/v1",
    tags=["internal bot v1 runtime"],
    dependencies=[Depends(require_bot_api_token)],
)


@router.post(
    "/fsm/get",
    response_model=BotFsmStateResponse,
    operation_id="get_internal_bot_fsm_state_v1",
)
async def get_fsm_state(
    payload: BotFsmStateGetRequest,
    session: AsyncSession = Depends(get_session),
) -> BotFsmStateResponse:
    """
    Read durable bot FSM state by service storage_key; missing state is state=null/data={}.
    This service primitive does not authorize a Telegram actor and is not a tenant CRM read.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    result = await BotRuntimeApiService.get_fsm_state(
        session, storage_key=payload.storage_key
    )
    return BotFsmStateResponse.model_validate(result)


@router.post(
    "/fsm/update",
    response_model=BotFsmStateResponse,
    operation_id="update_internal_bot_fsm_state_v1",
)
async def update_fsm_state(
    payload: BotFsmStateUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> BotFsmStateResponse:
    """
    Update the service-owned FSM row under storage_key. write_state and write_data choose
    which parts to replace; data is replaced, not merged. Empty state/data removes the row.
    No Telegram actor check or caller-supplied version precondition is provided.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    result = await BotRuntimeApiService.update_fsm_state(
        session, **payload.model_dump()
    )
    return BotFsmStateResponse.model_validate(result)


async def _lease_response(
    payload: BotRuntimeLeaseRequest, session: AsyncSession
) -> BotRuntimeLeaseResponse:
    result = await BotRuntimeApiService.acquire_lease(
        session, **payload.model_dump()
    )
    return BotRuntimeLeaseResponse.model_validate(result)


@router.post(
    "/runtime-leases/acquire",
    response_model=BotRuntimeLeaseResponse,
    operation_id="acquire_internal_bot_runtime_lease_v1",
)
async def acquire_runtime_lease(
    payload: BotRuntimeLeaseRequest,
    session: AsyncSession = Depends(get_session),
) -> BotRuntimeLeaseResponse:
    """
    Acquire or extend a service process lease by name and owner_id. A different owner with a
    nonexpired lease yields acquired=false rather than 409; same owner or expired lease can
    be acquired for ttl_seconds. This primitive does not authorize a Telegram actor.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    return await _lease_response(payload, session)


@router.post(
    "/runtime-leases/renew",
    response_model=BotRuntimeLeaseResponse,
    operation_id="renew_internal_bot_runtime_lease_v1",
)
async def renew_runtime_lease(
    payload: BotRuntimeLeaseRequest,
    session: AsyncSession = Depends(get_session),
) -> BotRuntimeLeaseResponse:
    """
    Use the same acquire-or-extend semantics as /runtime-leases/acquire. If absent or
    expired the lease can be acquired; it is not restricted to renewing an existing row. A
    different live owner yields acquired=false. No Telegram actor check is performed.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    return await _lease_response(payload, session)


@router.post(
    "/runtime-leases/release",
    response_model=BotRuntimeLeaseResponse,
    operation_id="release_internal_bot_runtime_lease_v1",
)
async def release_runtime_lease(
    payload: BotRuntimeLeaseRequest,
    session: AsyncSession = Depends(get_session),
) -> BotRuntimeLeaseResponse:
    """
    Release a service process lease only when its owner_id matches. Missing lease or another
    owner returns acquired=false; a successful release returns acquired=true. No Telegram
    actor check is performed.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    changed = await BotRuntimeApiService.release_lease(
        session, name=payload.name, owner_id=payload.owner_id
    )
    return BotRuntimeLeaseResponse(
        name=payload.name,
        owner_id=payload.owner_id,
        acquired=changed,
    )
