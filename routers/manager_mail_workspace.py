"""Manager adapter for the same persisted mail commands used by MCP."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from routers import manager_operation_ids as mail_operation_ids

from core.command_actor import CommandActor, get_command_idempotency_key
from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context
from schemas_mail import (
    MailAccountListResponse, MailConfirmPayload, MailDraftCreatePayload,
    MailDraftUpdatePayload, MailMessageListResponse, MailMessageResponse, MailVersionPayload, MailTextSuggestionResponse,
)
from services.connector_auth_policy import ConnectorAuthError, csrf_token, validate_csrf
from services.mail_smtp_service import MAX_ORDER_EMAIL_ATTACHMENT_BYTES
from services.mail_workspace_access import MailNotFoundError, MailStateConflictError, MailVersionConflictError
from services.mail_workspace_service import MailWorkspaceService
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable

router = APIRouter(prefix="/api/manager/mail", tags=["manager-mail-workspace"])
NO_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff"}


def _credential(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    token = request.cookies.get("access_token", "")
    return token[7:].strip() if token.lower().startswith("bearer ") else token


def require_mail_approval(request: Request) -> None:
    """Explicit Manager action with a credential-bound token; JSON booleans are not consent."""
    if request.headers.get("X-Kitlane-Mail-Approval") != "manager-review":
        raise HTTPException(status_code=403, detail={"code": "mail_approval_required", "message": "Подтвердите письмо в Manager"})
    try:
        validate_csrf(request.headers.get("X-CSRF-Token", ""), _credential(request))
    except ConnectorAuthError as exc:
        raise HTTPException(status_code=403, detail={"code": "mail_approval_csrf", "message": "Обновите предпросмотр письма"}) from exc


def _http_error(exc):
    if isinstance(exc, LookupError):
        return HTTPException(404, detail={"code": "mail_not_found", "message": str(exc)})
    if isinstance(exc, MailVersionConflictError):
        return HTTPException(409, detail={"code": "mail_version_conflict", "message": str(exc), "current_version": exc.current_version})
    if isinstance(exc, (MailStateConflictError, PublicWriteIdempotencyConflict)):
        return HTTPException(409, detail={"code": "mail_state_conflict" if isinstance(exc, MailStateConflictError) else "idempotency_key_reused", "message": str(exc)})
    if isinstance(exc, PublicWriteIdempotencyUnavailable):
        return HTTPException(503, detail={"code": "idempotency_unavailable", "message": "Команда временно занята, повторите запрос"}, headers={"Retry-After": "1"})
    return HTTPException(403 if isinstance(exc, PermissionError) else 422,
        detail={"code": "forbidden" if isinstance(exc, PermissionError) else "mail_invalid", "message": str(exc)})


ERRORS = (LookupError, MailVersionConflictError, MailStateConflictError,
    PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable, PermissionError, ValueError)


async def _read(coro, response):
    try:
        result = await coro
    except ERRORS as exc:
        raise _http_error(exc) from exc
    response.headers.update(NO_CACHE)
    return result


async def _write(coro, response):
    outcome = await _read(coro, response)
    response.status_code = outcome.status_code
    response.headers["Idempotency-Replayed"] = str(outcome.replayed).lower()
    return outcome.value


@router.get("/accounts", response_model=MailAccountListResponse, operation_id=mail_operation_ids.LIST_MANAGER_MAIL_ACCOUNTS)
async def mail_accounts(response: Response, auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """List configured mail accounts available to the current company and live staff identity. Partner companies never borrow the platform SMTP account. No credentials are returned."""
    return await _read(MailWorkspaceService.get_accounts(session, actor=CommandActor.from_auth(auth)), response)


@router.get("/messages", response_model=MailMessageListResponse, operation_id=mail_operation_ids.LIST_MANAGER_MAIL_MESSAGES)
async def mail_messages(response: Response, folder: str = Query("outbox", pattern="^(inbox|outbox|drafts)$"),
    q: str | None = Query(None, max_length=500), status: str | None = None, order_id: int | None = Query(None, ge=1),
    customer_id: int | None = Query(None, ge=1), page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=100),
    auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Search saved company mail in inbox, outbox or drafts; pagination is capped at 100. Linked order/customer filters require access. Inbox IDs are negative to keep one opaque message namespace."""
    return await _read(MailWorkspaceService.list_messages(session, actor=CommandActor.from_auth(auth),
        folder=folder, q=q, status=status, order_id=order_id, customer_id=customer_id, page=page, limit=limit), response)


@router.get("/messages/{message_id}", response_model=MailMessageResponse, operation_id=mail_operation_ids.GET_MANAGER_MAIL_MESSAGE)
async def mail_message(message_id: int, response: Response, auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Read saved company mail with private attachment download references. Sent/failed/unknown history is immutable; unknown does not authorize a retry. A stale interrupted send is marked unknown."""
    return await _read(MailWorkspaceService.get_message(session, actor=CommandActor.from_auth(auth), message_id=message_id), response)


@router.post("/drafts", response_model=MailMessageResponse, status_code=201, operation_id=mail_operation_ids.CREATE_MANAGER_MAIL_DRAFT)
async def create_mail_draft(payload: MailDraftCreatePayload, response: Response,
    idempotency_key: str = Depends(get_command_idempotency_key), auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Persist an incomplete draft without sending. Order/customer and recipient are optional. Requires a configured account, live staff membership and Idempotency-Key; replay returns the stored result."""
    return await _write(MailWorkspaceService.create_draft(session, actor=CommandActor.from_auth(auth), payload=payload, idempotency_key=idempotency_key), response)


@router.get("/drafts/{draft_id}", response_model=MailMessageResponse, operation_id=mail_operation_ids.GET_MANAGER_MAIL_DRAFT)
async def get_mail_draft(draft_id: int, response: Response, auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Read the current server-saved outgoing message version. Access requires live staff membership and available linked objects."""
    return await _read(MailWorkspaceService.get_message(session, actor=CommandActor.from_auth(auth), message_id=draft_id), response)


@router.post("/drafts/{draft_id}/suggest", response_model=MailTextSuggestionResponse, operation_id=mail_operation_ids.SUGGEST_MANAGER_MAIL_DRAFT_TEXT)
async def suggest_mail_draft_text(draft_id: int, payload: MailVersionPayload, response: Response,
    auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Suggest safe wording for the accessible saved draft version using DeepSeek.
    Does not modify or approve mail. Provider failure returns the saved text immediately
    after a bounded attempt. Facts, signature and next steps stay server-owned.
    """
    from services.mail_wording_service import MailWordingService

    return await _read(MailWordingService.suggest(session, actor=CommandActor.from_auth(auth),
        draft_id=draft_id, expected_version=payload.expected_version), response)


@router.patch("/drafts/{draft_id}", response_model=MailMessageResponse, operation_id=mail_operation_ids.PATCH_MANAGER_MAIL_DRAFT)
async def patch_mail_draft(draft_id: int, payload: MailDraftUpdatePayload, response: Response,
    idempotency_key: str = Depends(get_command_idempotency_key), auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Save supplied fields of a draft using expected_version and Idempotency-Key. A conflicting edit returns 409/current_version. Every edit invalidates approval; sent history cannot be edited."""
    return await _write(MailWorkspaceService.update_draft(session, actor=CommandActor.from_auth(auth), draft_id=draft_id, payload=payload, idempotency_key=idempotency_key), response)


@router.delete("/drafts/{draft_id}", response_model=MailMessageResponse, operation_id=mail_operation_ids.DELETE_MANAGER_MAIL_DRAFT)
async def delete_mail_draft(draft_id: int, payload: MailVersionPayload, response: Response,
    idempotency_key: str = Depends(get_command_idempotency_key), auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Delete only the current draft and its private files. Requires expected_version and Idempotency-Key. History of sending, sent, failed or unknown messages cannot be deleted."""
    return await _write(MailWorkspaceService.delete_draft(session, actor=CommandActor.from_auth(auth), draft_id=draft_id, payload=payload, idempotency_key=idempotency_key), response)


@router.post("/messages/{message_id}/copy", response_model=MailMessageResponse, status_code=201, operation_id=mail_operation_ids.COPY_MANAGER_MAIL_MESSAGE)
async def copy_mail_message(message_id: int, payload: MailVersionPayload, response: Response,
    idempotency_key: str = Depends(get_command_idempotency_key), auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Create a new editable draft using the exact stored files of a sent or definitively failed message. Unknown/pending/sending messages and legacy metadata-only attachments require manual verification instead of blind resend."""
    return await _write(MailWorkspaceService.copy_message(session, actor=CommandActor.from_auth(auth), message_id=message_id, payload=payload, idempotency_key=idempotency_key), response)


@router.post("/drafts/{draft_id}/attachments", response_model=MailMessageResponse, operation_id=mail_operation_ids.UPLOAD_MANAGER_MAIL_DRAFT_ATTACHMENT)
async def upload_mail_attachment(draft_id: int, response: Response, expected_version: int = Form(..., ge=1), file: UploadFile = File(...),
    idempotency_key: str = Depends(get_command_idempotency_key), auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Save private file bytes on the current draft without sending. At most 10 files, 10 MiB each and 20 MiB total; upload increments version and invalidates approval. Requires Idempotency-Key."""
    actor = CommandActor.from_auth(auth)
    # Authorize before reading the upload into memory.
    await _read(MailWorkspaceService.get_message(session, actor=actor, message_id=draft_id), response)
    content = await file.read(MAX_ORDER_EMAIL_ATTACHMENT_BYTES + 1)
    return await _write(MailWorkspaceService.upload_attachment(session, actor=actor, draft_id=draft_id,
        expected_version=expected_version, idempotency_key=idempotency_key, filename=file.filename or "file",
        mime_type=file.content_type or "application/octet-stream", content=content), response)


@router.get("/drafts/{draft_id}/attachments/{attachment_id}", operation_id=mail_operation_ids.DOWNLOAD_MANAGER_MAIL_ATTACHMENT)
async def download_mail_attachment(draft_id: int, attachment_id: int,
    auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Download private immutable attachment bytes after company and message/link checks. Returns no-store/nosniff with attachment disposition; public object paths are never exposed."""
    try:
        file = await MailWorkspaceService.get_attachment(session, actor=CommandActor.from_auth(auth), draft_id=draft_id, attachment_id=attachment_id)
    except ERRORS as exc:
        raise _http_error(exc) from exc
    return Response(content=file.content, media_type=file.mime_type, headers={**NO_CACHE,
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file.filename)}"})


@router.delete("/drafts/{draft_id}/attachments/{attachment_id}", response_model=MailMessageResponse, operation_id=mail_operation_ids.DELETE_MANAGER_MAIL_DRAFT_ATTACHMENT)
async def delete_mail_attachment(draft_id: int, attachment_id: int, response: Response, expected_version: int = Query(..., ge=1),
    idempotency_key: str = Depends(get_command_idempotency_key), auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Remove a private file only from the current draft, incrementing version and invalidating approval. Requires expected_version and Idempotency-Key; sent files stay immutable."""
    return await _write(MailWorkspaceService.delete_attachment(session, actor=CommandActor.from_auth(auth), draft_id=draft_id,
        attachment_id=attachment_id, expected_version=expected_version, idempotency_key=idempotency_key), response)


@router.get("/drafts/{draft_id}/preview", response_model=MailMessageResponse, operation_id=mail_operation_ids.PREVIEW_MANAGER_MAIL_DRAFT)
async def preview_mail_draft(draft_id: int, request: Request, response: Response,
    auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Return the full saved sender, all recipients, text, private files and content hash for Manager review. A short-lived CSRF token is bound to this Manager credential; MCP never receives approval authority."""
    result = await _read(MailWorkspaceService.preview(session, actor=CommandActor.from_auth(auth), draft_id=draft_id), response)
    return result.model_copy(update={"csrf_token": csrf_token(_credential(request))})


@router.post("/drafts/{draft_id}/confirm", response_model=MailMessageResponse, operation_id=mail_operation_ids.CONFIRM_MANAGER_MAIL_DRAFT)
async def confirm_mail_draft(draft_id: int, payload: MailConfirmPayload, request: Request, response: Response,
    idempotency_key: str = Depends(get_command_idempotency_key), auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Explicitly approve reviewed content_hash/expected_version as the authenticated Manager actor. Requires preview X-CSRF-Token and X-Kitlane-Mail-Approval: manager-review. Approval does not send and cannot be created by MCP."""
    require_mail_approval(request)
    return await _write(MailWorkspaceService.confirm(session, actor=CommandActor.from_auth(auth), draft_id=draft_id, payload=payload, idempotency_key=idempotency_key), response)


@router.post("/drafts/{draft_id}/send", response_model=MailMessageResponse, operation_id=mail_operation_ids.SEND_MANAGER_MAIL_DRAFT)
async def send_mail_draft(draft_id: int, payload: MailVersionPayload, request: Request, response: Response,
    idempotency_key: str = Depends(get_command_idempotency_key), auth: AuthenticatedUser = Depends(get_current_auth_context), session: AsyncSession = Depends(get_session)):
    """Send the saved, approved exact version once. The committed sending claim fences parallel requests and different keys before SMTP. Sent means SMTP accepted; ambiguous failures return unknown with no blind retry. Requires preview CSRF/approval headers and Idempotency-Key."""
    require_mail_approval(request)
    return await _write(MailWorkspaceService.send(session, actor=CommandActor.from_auth(auth), draft_id=draft_id, payload=payload, idempotency_key=idempotency_key), response)
