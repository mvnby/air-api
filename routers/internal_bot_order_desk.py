"""Private manager actions on existing orders after equipment selection."""

from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot_order_desk import BotOrderCommandRequest, BotOrderDesk, BotOrderQuote, BotOrderRevision
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from modules.documents.application.errors import (
    ManagedDocumentConflictError, ManagedDocumentGenerationError, ManagedDocumentNotFoundError,
)
from modules.documents.application.facsimile_context import MAX_PDF_BYTES
from services.bot_business_context import bind_bot_business_context
from services.bot_order_desk import change_order, get_order_desk, quote
from services.bot_order_documents import draft_pdf
from services.bot_order_issuance import issued_pdf
from services.bot_workspace_service import workspace_for
from services.customer_creation_service import CustomerAlreadyExistsError
from services.order_waiting_service import OrderWaitingError
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable


router = APIRouter(
    prefix="/api/internal/bot/v1/order-desk", tags=["internal bot v1"],
    dependencies=[Depends(require_bot_api_token), Depends(bind_bot_business_context, scope="function")],
)
OrderId = Annotated[int, Path(gt=0, le=2**31 - 1)]
Session = Annotated[AsyncSession, Depends(get_session)]
Telegram = Annotated[int, Query(gt=0)]
ContextVersion = Annotated[int, Query(ge=0)]


@contextmanager
def order_errors():
    try:
        yield
    except ManagedDocumentNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ManagedDocumentConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ManagedDocumentGenerationError as exc:
        raise HTTPException(503, str(exc)) from exc
    except OrderWaitingError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except CustomerAlreadyExistsError as exc:
        raise HTTPException(422, f"{exc}. Выберите существующего клиента.") from exc
    except PublicWriteIdempotencyConflict as exc:
        raise HTTPException(409, "Ключ этой операции уже использован с другими данными.") from exc
    except PublicWriteIdempotencyUnavailable as exc:
        raise HTTPException(503, "Повторите сохранение.", headers={"Retry-After": "1"}) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, "Запись недоступна.") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{order_id}", response_model=BotOrderDesk, operation_id="get_internal_bot_order_desk_v1")
async def get_desk(order_id: OrderId, session: Session, telegram_id: Telegram, expected_context_version: ContextVersion):
    """Read a saved order, proposals, follow-up, equipment reservations, payment history and document capabilities.
    Requires the service bearer, a current Telegram manager and company/site version. Reads do not repair legacy
    rows. An inaccessible order returns 404, invalid access 403 and a stale selection 409."""
    with order_errors():
        return await get_order_desk(session, await workspace_for(session, telegram_id), order_id)


@router.post("/{order_id}/commands", response_model=BotOrderDesk, operation_id="apply_internal_bot_order_change_v1",
             responses={503: {"description": "Temporary failure while applying or completing the order command.",
                              "headers": {"X-Kitlane-Document-State": {
                                  "description": "Set when final document generation failed after a durable number reservation.",
                                  "schema": {"type": "string", "enum": ["number-reserved"]},
                              }}}})
async def apply_change(order_id: OrderId, payload: BotOrderCommandRequest, session: Session):
    """Apply a scoped order change, including equipment reservations, manual payment records or document issuance.
    Requires a live writable membership and company context. A scoped idempotency key retries the same change;
    a stale order revision or reused key with a different command returns 409. A draft preserves one proposal's
    saved prices. Payment entry and document issuance require explicit confirmation. Inaccessible records return
    404, invalid fields 422 and temporary document generation failures 503."""
    with order_errors():
        return await change_order(session, await workspace_for(session, payload.telegram_id), order_id, payload)


@router.get("/{order_id}/quote", response_model=BotOrderQuote, operation_id="get_internal_bot_order_quote_v1")
async def get_quote(order_id: OrderId, session: Session, telegram_id: Telegram, expected_context_version: ContextVersion,
                    expected_revision: BotOrderRevision, proposal_id: int | None = Query(None, gt=0)):
    """Build client-facing text for precisely one active saved variant, including work and agreed sale prices.
    Requires the service token, a scoped manager and current order/company revisions (409 if stale).
    Omit proposal_id for a legacy ungrouped order. Missing orders or alternatives return 404."""
    with order_errors():
        return await quote(session, await workspace_for(session, telegram_id), order_id, proposal_id, expected_revision)


@router.get("/{order_id}/documents/{document_id}/preview", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}}, operation_id="preview_internal_bot_order_document_v1")
async def preview(order_id: OrderId, document_id: OrderId, session: Session, telegram_id: Telegram,
                  expected_context_version: ContextVersion):
    """Render a saved native document draft for the authenticated manager. Verifies order/document
    binding, tenant, storefront and company selection. Preview does not issue or send. Returns a private PDF,
    403 for demo, 404 outside scope, 409 for a non-draft and 503 when rendering is unavailable."""
    with order_errors():
        ws = await workspace_for(session, telegram_id)
        content = await draft_pdf(session, ws.scope, order_id, document_id)
        if len(content) > MAX_PDF_BYTES:
            raise HTTPException(413, "Файл слишком большой для предпросмотра.")
        return Response(content, media_type="application/pdf", headers={"Cache-Control": "private, no-store"})


@router.get("/{order_id}/documents/{document_id}/pdf", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}}, operation_id="get_internal_bot_issued_document_pdf_v1")
async def get_issued_pdf(order_id: OrderId, document_id: OrderId, session: Session, telegram_id: Telegram,
                         expected_context_version: ContextVersion):
    """Fetch the stored official PDF of this order for the authenticated manager. Requires a service bearer,
    current manager membership, tenant, storefront and company version. Returns 404 for an inaccessible document,
    409 for an ineligible status, 413 for an oversized PDF and 503 for unavailable private storage. The response
    must not be cached."""
    with order_errors():
        ws = await workspace_for(session, telegram_id)
        content = await issued_pdf(session, ws.scope, order_id, document_id)
        if len(content) > MAX_PDF_BYTES:
            raise HTTPException(413, "Файл слишком большой для Telegram.")
        return Response(content, media_type="application/pdf", headers={"Cache-Control": "private, no-store"})
