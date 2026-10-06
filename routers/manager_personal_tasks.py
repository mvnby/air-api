"""Manager HTTP adapter for persistent personal tasks."""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import (
    CommandActor,
    get_command_idempotency_key,
)
from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context
from schemas_personal_tasks import (
    PersonalTaskAssigneeListResponse,
    PersonalTaskCreatePayload,
    PersonalTaskListFilter,
    PersonalTaskListResponse,
    PersonalTaskResponse,
    PersonalTaskStatusPayload,
    PersonalTaskUpdatePayload,
)
from services.personal_task_service import (
    PersonalTaskNotFoundError,
    PersonalTaskService,
    PersonalTaskStatusConflictError,
    PersonalTaskVersionConflictError,
)
from services.public_write_idempotency_service import (
    PublicWriteCommandOutcome,
    PublicWriteIdempotencyConflict,
    PublicWriteIdempotencyUnavailable,
)


router = APIRouter(prefix="/api/manager/personal-tasks", tags=["manager-personal-tasks"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PersonalTaskNotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "personal_task_not_found", "message": str(exc)},
        )
    if isinstance(exc, PersonalTaskVersionConflictError):
        return HTTPException(
            status_code=409,
            detail={
                "code": "personal_task_version_conflict",
                "message": str(exc),
                "current_version": exc.current_version,
            },
        )
    if isinstance(exc, PersonalTaskStatusConflictError):
        return HTTPException(
            status_code=409,
            detail={"code": "personal_task_status_conflict", "message": str(exc)},
        )
    if isinstance(exc, PublicWriteIdempotencyConflict):
        return HTTPException(
            status_code=409,
            detail={
                "code": "idempotency_key_reused",
                "message": "Ключ повтора уже использован с другими данными",
            },
        )
    if isinstance(exc, PublicWriteIdempotencyUnavailable):
        return HTTPException(
            status_code=503,
            detail={
                "code": "idempotency_unavailable",
                "message": "Команда временно занята, повторите запрос",
            },
            headers={"Retry-After": "1"},
        )
    if isinstance(exc, PermissionError):
        return HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": str(exc)},
        )
    return HTTPException(
        status_code=422,
        detail={"code": "personal_task_invalid", "message": str(exc)},
    )


async def _run_command(
    command: Callable[[], Awaitable[PublicWriteCommandOutcome[PersonalTaskResponse]]],
    response: Response,
) -> PersonalTaskResponse:
    try:
        outcome = await command()
    except (
        PersonalTaskNotFoundError,
        PersonalTaskVersionConflictError,
        PersonalTaskStatusConflictError,
        PublicWriteIdempotencyConflict,
        PublicWriteIdempotencyUnavailable,
        PermissionError,
        ValueError,
    ) as exc:
        raise _http_error(exc) from exc
    response.status_code = outcome.status_code
    response.headers["Idempotency-Replayed"] = "true" if outcome.replayed else "false"
    return outcome.value


@router.get(
    "",
    response_model=PersonalTaskListResponse,
    operation_id="list_manager_personal_tasks",
)
async def list_manager_personal_tasks(
    task_filter: PersonalTaskListFilter = Query("active", alias="filter"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    auth: AuthenticatedUser = Depends(get_current_auth_context),
    session: AsyncSession = Depends(get_session),
) -> PersonalTaskListResponse:
    actor = CommandActor.from_auth(auth)
    return await PersonalTaskService.list(
        session,
        actor=actor,
        task_filter=task_filter,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/assignees",
    response_model=PersonalTaskAssigneeListResponse,
    operation_id="list_manager_personal_task_assignees",
)
async def list_manager_personal_task_assignees(
    limit: int = Query(100, ge=1, le=100),
    auth: AuthenticatedUser = Depends(get_current_auth_context),
    session: AsyncSession = Depends(get_session),
) -> PersonalTaskAssigneeListResponse:
    return await PersonalTaskService.list_assignees(
        session,
        actor=CommandActor.from_auth(auth),
        limit=limit,
    )


@router.get(
    "/{task_id}",
    response_model=PersonalTaskResponse,
    operation_id="get_manager_personal_task",
)
async def get_manager_personal_task(
    task_id: int,
    auth: AuthenticatedUser = Depends(get_current_auth_context),
    session: AsyncSession = Depends(get_session),
) -> PersonalTaskResponse:
    try:
        return await PersonalTaskService.get(
            session,
            actor=CommandActor.from_auth(auth),
            task_id=task_id,
        )
    except PersonalTaskNotFoundError as exc:
        raise _http_error(exc) from exc


@router.post(
    "",
    response_model=PersonalTaskResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_manager_personal_task",
)
async def create_manager_personal_task(
    payload: PersonalTaskCreatePayload,
    response: Response,
    idempotency_key: str = Depends(get_command_idempotency_key),
    auth: AuthenticatedUser = Depends(get_current_auth_context),
    session: AsyncSession = Depends(get_session),
) -> PersonalTaskResponse:
    actor = CommandActor.from_auth(auth)
    return await _run_command(
        lambda: PersonalTaskService.create(
            session,
            actor=actor,
            payload=payload,
            idempotency_key=idempotency_key,
        ),
        response,
    )


@router.patch(
    "/{task_id}",
    response_model=PersonalTaskResponse,
    operation_id="patch_manager_personal_task",
)
async def patch_manager_personal_task(
    task_id: int,
    payload: PersonalTaskUpdatePayload,
    response: Response,
    idempotency_key: str = Depends(get_command_idempotency_key),
    auth: AuthenticatedUser = Depends(get_current_auth_context),
    session: AsyncSession = Depends(get_session),
) -> PersonalTaskResponse:
    actor = CommandActor.from_auth(auth)
    return await _run_command(
        lambda: PersonalTaskService.update(
            session,
            actor=actor,
            task_id=task_id,
            payload=payload,
            idempotency_key=idempotency_key,
        ),
        response,
    )


def _status_route(action: str):
    method = getattr(PersonalTaskService, action)

    async def handler(
        task_id: int,
        payload: PersonalTaskStatusPayload,
        response: Response,
        idempotency_key: str = Depends(get_command_idempotency_key),
        auth: AuthenticatedUser = Depends(get_current_auth_context),
        session: AsyncSession = Depends(get_session),
    ) -> PersonalTaskResponse:
        actor = CommandActor.from_auth(auth)
        return await _run_command(
            lambda: method(
                session,
                actor=actor,
                task_id=task_id,
                payload=payload,
                idempotency_key=idempotency_key,
            ),
            response,
        )

    return handler


router.add_api_route(
    "/{task_id}/complete",
    _status_route("complete"),
    methods=["POST"],
    response_model=PersonalTaskResponse,
    operation_id="complete_manager_personal_task",
)
router.add_api_route(
    "/{task_id}/reopen",
    _status_route("reopen"),
    methods=["POST"],
    response_model=PersonalTaskResponse,
    operation_id="reopen_manager_personal_task",
)
router.add_api_route(
    "/{task_id}/cancel",
    _status_route("cancel"),
    methods=["POST"],
    response_model=PersonalTaskResponse,
    operation_id="cancel_manager_personal_task",
)
