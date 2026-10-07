"""Manager transport for the same commands exposed by the connector."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor, get_command_idempotency_key
from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context
from routers import manager_operation_ids as operation_ids
from schemas_incoming import (
    IncomingCreatePayload,
    IncomingClarificationPayload,
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
    except ValueError as exc:
        raise HTTPException(400, detail={"error_code": "invalid_input", "message": str(exc)}) from exc
    response.status_code = result.status_code
    response.headers["Idempotency-Replayed"] = str(result.replayed).lower()
    return result.value


@router.post(
    "/{lead_id}/clarification", response_model=IncomingResponse,
    operation_id=operation_ids.CREATE_MANAGER_INCOMING_CLARIFICATION,
)
async def create_clarification(
    lead_id: int, payload: IncomingClarificationPayload, response: Response,
    caller: CommandActor = Depends(actor),
    key: str = Depends(get_command_idempotency_key),
    session: AsyncSession = Depends(get_session),
):
    """Explicitly create one linked address/call clarification task from the known
    incoming context for the authenticated Manager actor's tenant/storefront. The
    task is assigned to the caller without a deadline or reminder; a customer wish
    never becomes a callback deadline or booked visit. Requires expected_version
    and Idempotency-Key. Same command/key replays; changed payload/key, stale version
    or terminal incoming returns 409, missing/inaccessible intake 404, demo 403,
    invalid input/key 400/422 and unavailable receipt 503 with Retry-After: 1.
    A new intentional command on the current version returns the existing link.
    Task read/edit visibility remains the PersonalTask author/assignee contract.

    Access requires an authenticated Manager session/JWT and live membership; see
    [Manager access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await mutation(IncomingCommandService.create_clarification(
        session, actor=caller, lead_id=lead_id, payload=payload, idempotency_key=key,
    ), response)


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
    """
    Save an incomplete incoming request as a Lead in the authenticated staff actor’s
    tenant/storefront, retaining original text/source time and reporting missing
    contact/address data. Does not create a customer/order or reserve a work slot; inferred
    phone/date remain suggestions. Requires Idempotency-Key: same actor/key/payload replays
    with Idempotency-Replayed; changed key payload or reused source event with different
    content returns 409. Invalid key returns 400, demo mutation 403, unavailable receipt
    storage 503 with Retry-After: 1. Retry the unchanged command/key.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    List unconverted, unarchived incoming requests in new/contacted state for the
    authenticated staff actor’s tenant/storefront, newest first. Uses limit/offset with
    limit at most 100 and returns total. Does not mark personal read state, qualify a lead
    or schedule requested time.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Read an incoming request with saved intake metadata in the authenticated staff actor’s
    tenant/storefront, including current version, original text and missing-data state.
    Missing/inaccessible or non-intake Lead returns 404. Reading does not mark the triage
    card read or change its workflow.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Correct an active incoming request in the authenticated staff actor’s tenant/storefront
    using expected_version and Idempotency-Key. Increments version, preserves omitted fields
    and clears explicitly null optional fields; a changed time wish is reinterpreted only
    against the retained source clock. Archived/qualified or changed-version request and
    changed replay payload return 409; missing intake 404, demo mutation 403, invalid key
    400 and receipt storage unavailable 503 with Retry-After: 1. Same successful command/key
    replays with Idempotency-Replayed; it does not reserve calendar time.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await mutation(
        IncomingCommandService.update(
            session, actor=caller, lead_id=lead_id, payload=payload, idempotency_key=key
        ),
        response,
    )
