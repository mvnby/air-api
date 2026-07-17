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
    changed = await BotRuntimeApiService.release_lease(
        session, name=payload.name, owner_id=payload.owner_id
    )
    return BotRuntimeLeaseResponse(
        name=payload.name,
        owner_id=payload.owner_id,
        acquired=changed,
    )
