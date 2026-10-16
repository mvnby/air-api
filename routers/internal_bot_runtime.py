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
    Optional telegram_id and expected_context_version validate the actor's fresh selected
    context. Legacy opaque service keys retain primitive compatibility without CRM grants;
    company-picker ctxcb state remains readable for recovery from an unavailable selection.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    await _bind_fsm_context(session, payload)
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
    Optional telegram_id and expected_context_version fence writes to a fresh selected
    context. Legacy keys cannot write after the actor switches context. Recovery ctxcb
    records permit only company-picker callbacks and never grant access to CRM data.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    await _bind_fsm_context(session, payload)
    result = await BotRuntimeApiService.update_fsm_state(
        session, **payload.model_dump(exclude={"telegram_id", "expected_context_version"})
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


async def _bind_fsm_context(session, payload):
    # Identity proof and leases never use this helper. Legacy raw FSM calls can
    # only write a never-switched context; unknown users receive no business grant.
    import json
    from fastapi import HTTPException
    from services.bot_access_service import BotAccessService
    from services.bot_staff_selection_service import BotStaffSelectionService, context_changed
    actor = payload.telegram_id or getattr(payload, 'user_id', None)
    if actor is None:
        try:
            key = json.loads(payload.storage_key)
            actor = int(key[2]) if isinstance(key, list) and len(key) >= 3 else None
        except (ValueError, TypeError, IndexError):
            actor = None
    if actor is None:
        return
    context = await BotAccessService.get_context(session, actor)
    if context.selection_unavailable and payload.storage_key.startswith('ctxcb:'):
        # Company picker callbacks are recoverable personal UI, not CRM state.
        callbacks = getattr(payload, 'data', {}).get('callbacks', [])
        selector_write = getattr(payload, 'destiny', '') == 'context_callbacks' and callbacks and all(
            str(value).startswith(('company_pick:', 'company_page:')) for value in callbacks)
        if not hasattr(payload, 'write_data') or selector_write:
            if context.selection is None or payload.expected_context_version != context.selection.context_version:
                raise context_changed()
            return
    if payload.telegram_id is not None and (not context.is_staff or context.selection is None):
        raise HTTPException(403, 'Active staff membership is required')
    if context.selection is None:
        return
    if payload.telegram_id is not None and getattr(payload, 'user_id', actor) != actor:
        raise HTTPException(403, 'FSM actor mismatch')
    if payload.expected_context_version is None and context.selection.context_version > 0:
        raise context_changed()
    if payload.expected_context_version is not None:
        await BotStaffSelectionService.bind_request(session, context.selection,
            payload.expected_context_version, mutation=False)
