"""Private staff call review and explicit commands; no automatic adoption."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from routers.manager_permission_policy import ManagerPermissionRoute
from routers import manager_operation_ids as operation_ids
from schemas_call_recordings import CallAdoptPayload, CallAdoptionResponse, CallDriveStatus, CallFolderPayload, CallPollPayload, CallPollResponse, CallRecordingListResponse, CallRecordingMetadataPayload, CallRecordingResponse, CallRetryPayload
from schemas_document_drive import DocumentDriveAuthorizationUrlResponse
from services.call_drive_connection_service import CallDriveConnectionService, require_live_call_actor
from services.call_drive_provider import get_call_drive_provider
from services.document_drive_contracts import DocumentDriveConnectionError
from services import call_drive_oauth
from services.call_recording_service import CallRecordingService
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable

router = APIRouter(prefix="/api/manager/call-recordings", tags=["manager-call-recordings"], route_class=ManagerPermissionRoute)


def caller(auth: AuthenticatedUser = Depends(require_manager_access)):
    return CommandActor.from_auth(auth)


async def respond(operation):
    try:
        return await operation
    except PermissionError as exc:
        raise HTTPException(403, detail=str(exc)) from exc
    except DocumentDriveConnectionError as exc:
        raise HTTPException(exc.status_code, detail={"error_code": exc.code, "message": str(exc)}) from exc
    except LookupError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except PublicWriteIdempotencyConflict as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except PublicWriteIdempotencyUnavailable as exc:
        raise HTTPException(503, detail="Повторите команду", headers={"Retry-After": "1"}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.get("/connection", response_model=CallDriveStatus, operation_id=operation_ids.GET_MANAGER_CALL_DRIVE_STATUS)
async def connection_status(actor: CommandActor = Depends(caller), session: AsyncSession = Depends(get_session)):
    """Read personal call-Drive connection readiness and fixed processing limits. Requires
    live Manager membership; scope is the current staff user plus tenant/storefront,
    including owners (no access to another user's calls). Returns no credentials. Does
    not contact Drive, poll recordings or charge AI. Default pipeline is disabled.
    [Call contract](https://github.com/mvnby/air-api/blob/main/docs/call-recordings.md).
    """
    return await respond(CallDriveConnectionService.status(session, actor))


@router.get("/authorization-url", response_model=DocumentDriveAuthorizationUrlResponse, operation_id=operation_ids.GET_MANAGER_CALL_DRIVE_AUTHORIZATION_URL)
async def authorization_url(request: Request, auth: AuthenticatedUser = Depends(require_manager_access), session: AsyncSession = Depends(get_session)):
    """Start a separate personal Google Drive readonly OAuth grant for the live staff
    actor/current tenant/storefront. State is one-use, expires after 10 minutes, and
    callback rechecks live role, membership and auth version. Existing document drive.file
    grants cannot read Samsung uploads. No Shared Drive is required. Does not choose a
    folder or enable polling; missing server OAuth configuration returns 503/502.
    [Call contract](https://github.com/mvnby/air-api/blob/main/docs/call-recordings.md).
    """
    actor = CommandActor.from_auth(auth)
    await respond(require_live_call_actor(session, actor, write=True))
    try:
        redirect = call_drive_oauth.callback_uri(request)
        state = call_drive_oauth.start(request, auth, redirect)
        url = await run_in_threadpool(lambda: get_call_drive_provider().authorization_url(redirect_uri=redirect, state=state))
        return DocumentDriveAuthorizationUrlResponse(url=url)
    except DocumentDriveConnectionError as exc:
        request.session.pop(call_drive_oauth.SESSION_KEY, None)
        raise HTTPException(exc.status_code, detail={"error_code": exc.code, "message": str(exc)}) from exc


@router.get("/oauth/callback", include_in_schema=False, name="manager_call_drive_callback")
async def oauth_callback(request: Request, code: str = "", state: str = "", error: str = "", session: AsyncSession = Depends(get_session)):
    pending = call_drive_oauth.consume(request, state)
    success = False
    if pending and code and not error:
        try:
            actor = await call_drive_oauth.pending_actor(session, pending)
            if call_drive_oauth.callback_uri(request) != pending["redirect_uri"]:
                raise PermissionError("Адрес подключения изменился")
            provider = get_call_drive_provider()
            credentials = await run_in_threadpool(lambda: provider.exchange_code(redirect_uri=pending["redirect_uri"], code=code))
            await CallDriveConnectionService.authorize(session, actor, credentials, provider=provider)
            success = True
        except (DocumentDriveConnectionError, PermissionError):
            await session.rollback()
    message = "Личный Google Диск подключён. Выберите папку записей." if success else "Подключение не завершено. Вернитесь в записи звонков и попробуйте снова."
    return HTMLResponse(f'<!doctype html><html lang="ru"><body><p>{message}</p><a href="/manager/calls">Записи звонков</a></body></html>', status_code=200 if success else 400)


@router.put("/connection/folder", response_model=CallDriveStatus, operation_id=operation_ids.CONFIGURE_MANAGER_CALL_DRIVE_FOLDER)
async def configure_folder(payload: CallFolderPayload, actor: CommandActor = Depends(caller), session: AsyncSession = Depends(get_session)):
    """Select an existing accessible folder for this staff user's separate readonly
    Drive grant. Live Manager access and writable tenant required. Personal Drive is
    supported. Verifies folder metadata, never creates a folder or reads audio. Explicit
    auto_poll_enabled opt-in also requires server CALL_RECORDINGS_ENABLED before jobs run;
    default false. Folder changes reset scan cursor and retain existing review material.
    Same payload is safe to repeat. Invalid/unavailable folder returns 422/409/502.
    """
    return await respond(CallDriveConnectionService.configure(session, actor, payload))


@router.delete("/connection", response_model=CallDriveStatus, operation_id=operation_ids.DISCONNECT_MANAGER_CALL_DRIVE)
async def disconnect(actor: CommandActor = Depends(caller), session: AsyncSession = Depends(get_session)):
    """Remove this user's local call-Drive credential and stop automatic polling. Live
    writable Manager membership required. Retains source links, transcripts, proposals and
    accepted actions; does not delete Google files or revoke other integrations. Repeating
    the disconnect is safe. Queued jobs fail closed until explicit reconnection/retry.
    """
    return await respond(CallDriveConnectionService.disconnect(session, actor))


@router.post("/poll", response_model=CallPollResponse, operation_id=operation_ids.POLL_MANAGER_CALL_RECORDINGS)
async def poll(payload: CallPollPayload, actor: CommandActor = Depends(caller), session: AsyncSession = Depends(get_session)):
    """Explicitly observe at most five files from the chosen personal folder (or one
    file_id for a pilot), using metadata only. Live writable Manager access, separate OAuth
    grant, selected folder and server-enabled pipeline required. Two observations at least
    60 seconds apart and stable version/checksum/size enqueue a durable job; this response
    is not successful transcription. New versions keep old material. At most 20 new
    recordings per owner per rolling day. Repeated observations do not duplicate jobs.
    Disabled 503, missing connection/folder or moved/unfinished chosen file 409, rejected
    format/size 422 and Drive failures 502. Job acceptance remains a separate command.
    """
    return await respond(CallRecordingService.poll(session, actor, file_id=payload.file_id))


@router.get("", response_model=CallRecordingListResponse, operation_id=operation_ids.LIST_MANAGER_CALL_RECORDINGS)
async def list_recordings(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), actor: CommandActor = Depends(caller), session: AsyncSession = Depends(get_session)):
    """List private call versions for the live Manager actor/current tenant/storefront,
    newest first; limit <=100 and offset pagination, including total. Other staff users,
    companies and storefronts are invisible. Returns stage, source link, error code and
    paid-stage attempt counts without transcript/audio bytes. Reading never starts work.
    """
    return await respond(CallRecordingService.list(session, actor, limit=limit, offset=offset))


@router.get("/{recording_id}", response_model=CallRecordingResponse, operation_id=operation_ids.GET_MANAGER_CALL_RECORDING)
async def get_recording(recording_id: int, actor: CommandActor = Depends(caller), session: AsyncSession = Depends(get_session)):
    """Read this staff user's scoped source version, transcript, structured review result
    and separately editable proposals with accepted-resource links. Requires live Manager
    role/membership; missing or inaccessible ID returns 404. Source Google link retains
    Google's own access policy. Proposed dates/conditions never confirm visits or facts;
    reading does not accept proposals, send messages or call AI.
    """
    return await respond(CallRecordingService.get(session, actor, recording_id))


@router.patch("/{recording_id}/metadata", response_model=CallRecordingResponse, operation_id=operation_ids.UPDATE_MANAGER_CALL_RECORDING_METADATA)
async def update_metadata(recording_id: int, payload: CallRecordingMetadataPayload, actor: CommandActor = Depends(caller), session: AsyncSession = Depends(get_session)):
    """Explicitly correct/clear source call time and phone for this user's recording.
    Requires live writable Manager access and expected_version; busy/stale version 409,
    missing 404, invalid phone/date 422. Sets time_source=manual (or unknown on null).
    Existing extraction/transcript is preserved; proposal rebuilding needs explicit retry
    and reuses successful paid checkpoints. Retrying a successful write with an old version
    returns 409; read the current version. Never infers time from processing/sync date.
    """
    return await respond(CallRecordingService.metadata(session, actor, recording_id, payload))


@router.post("/{recording_id}/retry", response_model=CallRecordingResponse, operation_id=operation_ids.RETRY_MANAGER_CALL_RECORDING)
async def retry(recording_id: int, payload: CallRetryPayload, actor: CommandActor = Depends(caller), session: AsyncSession = Depends(get_session)):
    """Explicitly resume a failed/reconnect/manual-review recording at the first unfinished
    stage. Requires live writable scoped Manager access, server opt-in and expected_version.
    Retains successful download/transcription/extraction checkpoints and does not recreate
    adopted incoming/tasks. No reset of the three-attempt paid-stage cap. Busy/stale/ready
    or exhausted stage 409; missing 404; disabled 503. Read current state after ambiguous
    response rather than repeating with a stale version. Reconnect OAuth before access retry.
    """
    return await respond(CallRecordingService.retry(session, actor, recording_id, payload))


@router.post("/{recording_id}/proposals/{proposal_id}/adopt", response_model=CallAdoptionResponse, operation_id=operation_ids.ADOPT_MANAGER_CALL_PROPOSAL)
async def adopt(recording_id: int, proposal_id: int, payload: CallAdoptPayload, actor: CommandActor = Depends(caller), session: AsyncSession = Depends(get_session)):
    """Explicitly adopt ONE edited proposal as a persistent Incoming or personal task,
    using the shared authenticated commands. Incoming clarification_requested also creates
    its disclosed linked clarification task. Requires current live writable Manager actor,
    original private source ownership, ready state and expected_version; foreign/missing
    404, stale/busy or changed accepted payload 409, invalid fields 422 and receipt storage
    unavailable 503 with Retry-After. Durable source/action receipt and domain write/audit
    commit atomically. Same adoption replays even beyond the ordinary receipt horizon;
    changed Drive versions cannot reapply accepted actions. Original call time and source
    link are retained. Does not create an order, confirm a visit or send to a customer.
    """
    return await respond(CallRecordingService.adopt(session, actor, recording_id, proposal_id, payload))
