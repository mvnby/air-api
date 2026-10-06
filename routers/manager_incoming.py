"""Manager transport for the same commands exposed by the connector."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor, get_command_idempotency_key
from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context
from routers import manager_operation_ids as operation_ids
from schemas_incoming import (
    IncomingCreatePayload,
    IncomingListResponse,
    IncomingResponse,
    IncomingUpdatePayload,
)
from services.incoming_command_service import (
    IncomingCommandService,
    IncomingVersionConflict,
)
from services.public_write_idempotency_service import (
    PublicWriteIdempotencyConflict,
    PublicWriteIdempotencyUnavailable,
)

router = APIRouter(prefix="/api/manager/incoming", tags=["manager/incoming"])


def actor(auth: AuthenticatedUser = Depends(get_current_auth_context)) -> CommandActor:
    return CommandActor.from_auth(auth)


async def mutation(call, response: Response):
    try:
        result = await call
    except (IncomingVersionConflict, PublicWriteIdempotencyConflict) as exc:
        raise HTTPException(
            409, detail={"error_code": "conflict", "message": str(exc)}
        ) from exc
    except PublicWriteIdempotencyUnavailable as exc:
        raise HTTPException(
            503,
            detail={
                "error_code": "temporarily_unavailable",
                "message": "Please retry with the same request key",
            },
            headers={"Retry-After": "1"},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            403, detail={"error_code": "forbidden", "message": str(exc)}
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            404, detail={"error_code": "not_found", "message": str(exc)}
        ) from exc
    response.status_code = result.status_code
    response.headers["Idempotency-Replayed"] = str(result.replayed).lower()
    return result.value


@router.post(
    "",
    response_model=IncomingResponse,
    status_code=201,
    operation_id=operation_ids.CREATE_MANAGER_INCOMING,
)
async def create_incoming(
    payload: IncomingCreatePayload,
    response: Response,
    caller: CommandActor = Depends(actor),
    key: str = Depends(get_command_idempotency_key),
    session: AsyncSession = Depends(get_session),
):
    return await mutation(
        IncomingCommandService.create(
            session, actor=caller, payload=payload, idempotency_key=key
        ),
        response,
    )


@router.get(
    "",
    response_model=IncomingListResponse,
    operation_id=operation_ids.LIST_MANAGER_INCOMING,
)
async def list_incoming(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    caller: CommandActor = Depends(actor),
    session: AsyncSession = Depends(get_session),
):
    return await IncomingCommandService.list(
        session, actor=caller, limit=limit, offset=offset
    )


@router.get(
    "/{lead_id}",
    response_model=IncomingResponse,
    operation_id=operation_ids.GET_MANAGER_INCOMING,
)
async def get_incoming(
    lead_id: int,
    caller: CommandActor = Depends(actor),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await IncomingCommandService.get(session, actor=caller, lead_id=lead_id)
    except LookupError as exc:
        raise HTTPException(
            404, detail={"error_code": "not_found", "message": str(exc)}
        ) from exc


@router.patch(
    "/{lead_id}",
    response_model=IncomingResponse,
    operation_id=operation_ids.UPDATE_MANAGER_INCOMING,
)
async def update_incoming(
    lead_id: int,
    payload: IncomingUpdatePayload,
    response: Response,
    caller: CommandActor = Depends(actor),
    key: str = Depends(get_command_idempotency_key),
    session: AsyncSession = Depends(get_session),
):
    return await mutation(
        IncomingCommandService.update(
            session, actor=caller, lead_id=lead_id, payload=payload, idempotency_key=key
        ),
        response,
    )
