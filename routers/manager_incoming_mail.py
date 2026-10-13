"""HTTP adapter for existing-mailbox sync and private incoming files."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from routers import manager_operation_ids as mail_operation_ids

from core.command_actor import CommandActor, get_command_idempotency_key
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from schemas_incoming_mail import IncomingMailSyncPayload, IncomingMailSyncResponse
from services.incoming_mail_service import IncomingMailService


router = APIRouter(prefix="/api/manager/mail", tags=["manager/mail"])


@router.post("/sync", response_model=IncomingMailSyncResponse, operation_id=mail_operation_ids.SYNC_MANAGER_MAILBOX)
async def sync_mailbox(payload: IncomingMailSyncPayload,
                       auth: AuthenticatedUser = Depends(require_manager_access),
                       session: AsyncSession = Depends(get_session),
                       idempotency_key: str = Depends(get_command_idempotency_key)):
    """Load a bounded page using the configured IMAP account; never creates CRM requests."""
    try:
        result = await IncomingMailService.sync(session, actor=CommandActor.from_auth(auth),
                                                payload=payload, idempotency_key=idempotency_key)
        return result.value
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        # IMAP diagnostics may contain connection details or provider secrets.
        raise HTTPException(502, "Не удалось обновить почту. Проверьте настройки подключения") from exc


@router.get("/messages/{email_id}/attachments/{attachment_id}", operation_id=mail_operation_ids.DOWNLOAD_MANAGER_INCOMING_MAIL_ATTACHMENT)
async def download_incoming_attachment(email_id: int, attachment_id: int,
                                       auth: AuthenticatedUser = Depends(require_manager_access),
                                       session: AsyncSession = Depends(get_session)):
    """Download only a private attachment of an incoming message accessible to this company."""
    try:
        file = await IncomingMailService.read_attachment(session, actor=CommandActor.from_auth(auth),
                                                         email_id=email_id, attachment_id=attachment_id)
        return Response(file.content, media_type="application/octet-stream", headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file.filename, safe='')}",
            "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        })
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, "Вложение не найдено") from exc
