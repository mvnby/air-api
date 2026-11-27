"""Telegram Manager requisites recognition, draft review and confirmation."""

from contextlib import contextmanager

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import (
    BotCustomerRequisitesActionRequest,
    BotCustomerRequisitesActionResponse,
    BotCustomerRequisitesEditRequest,
    BotCustomerRequisitesRecognitionResponse,
    BotCustomerRequisitesReviewRequest,
    BotCustomerRequisitesTextRequest,
)
from core.database import get_session
from models.tenancy import TenantScope
from services.bot_business_context import get_bot_request_scope
from services.bot_customer_requisites_api_service import (
    BotCustomerRequisitesAccessDeniedError,
    BotCustomerRequisitesApiService,
    BotCustomerRequisitesConflictError,
    BotCustomerRequisitesNotFoundError,
)
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService


router = APIRouter()


@contextmanager
def _requisites_errors():
    try:
        yield
    except BotCustomerRequisitesAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except BotCustomerRequisitesNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BotCustomerRequisitesConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post(
    "/customers/requisites/recognize-text",
    response_model=BotCustomerRequisitesRecognitionResponse,
    operation_id="recognize_internal_bot_customer_requisites_text_v1",
)
async def recognize_internal_bot_customer_requisites_text(
    payload: BotCustomerRequisitesTextRequest,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_bot_request_scope),
) -> BotCustomerRequisitesRecognitionResponse:
    """
    Recognize customer requisites from text for an active Manager Telegram actor in the
    selected tenant. Returns a recognition for explicit follow-up action; OCR alone does not
    confirm customer creation. Access denial returns 403 and invalid content 422.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    with _requisites_errors():
        recognition = await BotCustomerRequisitesApiService.recognize_text_for_manager(
            session,
            telegram_id=payload.telegram_id,
            text_value=payload.text,
            telegram_chat_id=payload.telegram_chat_id,
            telegram_message_id=payload.telegram_message_id,
            tenant_scope=tenant_scope,
        )
    return BotCustomerRequisitesRecognitionResponse.model_validate(recognition)


@router.post(
    "/customers/requisites/recognize-file",
    response_model=BotCustomerRequisitesRecognitionResponse,
    operation_id="recognize_internal_bot_customer_requisites_file_v1",
)
async def recognize_internal_bot_customer_requisites_file(
    expected_context_version: int | None = Form(default=None, ge=0),
    telegram_id: int = Form(ge=1),
    telegram_chat_id: int | None = Form(default=None),
    telegram_message_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_bot_request_scope),
) -> BotCustomerRequisitesRecognitionResponse:
    """
    Recognize customer requisites from JPG, PNG, WEBP, PDF, DOC or DOCX, at most 10 MB, for
    an active Manager Telegram actor in the selected tenant. Oversize returns 413,
    invalid/unsupported content 422, denied access 403. Returns a recognition for a later
    explicit action.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    max_bytes = CustomerRequisitesRecognitionService.MAX_FILE_SIZE_BYTES
    content = await file.read(max_bytes + 1)
    await file.close()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Файл слишком большой. Максимальный размер: 10 МБ",
        )
    with _requisites_errors():
        recognition = await BotCustomerRequisitesApiService.recognize_file_for_manager(
            session,
            telegram_id=telegram_id,
            content=content,
            filename=file.filename or "telegram-requisites",
            mime_type=file.content_type or "application/octet-stream",
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            tenant_scope=tenant_scope,
        )
    return BotCustomerRequisitesRecognitionResponse.model_validate(recognition)


@router.post(
    "/customers/requisites/{recognition_id}/review",
    response_model=BotCustomerRequisitesRecognitionResponse,
    operation_id="review_internal_bot_customer_requisites_v1",
)
async def review_internal_bot_customer_requisites(
    payload: BotCustomerRequisitesReviewRequest,
    recognition_id: int = Path(ge=1),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_bot_request_scope),
) -> BotCustomerRequisitesRecognitionResponse:
    """Read a Telegram requisites draft, field validation, current same-tenant INN match
    and opaque revision. Requires the service bearer and the originating active Manager
    in the selected company. Safe to repeat. Unauthorized actors get 403, missing drafts
    return 404 and a stale expected company context returns 409.
    """
    with _requisites_errors():
        recognition = await BotCustomerRequisitesApiService.review_for_manager(
            session, telegram_id=payload.telegram_id, recognition_id=recognition_id,
            tenant_scope=tenant_scope,
        )
    return BotCustomerRequisitesRecognitionResponse.model_validate(recognition)


@router.post(
    "/customers/requisites/{recognition_id}/edit",
    response_model=BotCustomerRequisitesRecognitionResponse,
    operation_id="edit_internal_bot_customer_requisites_v1",
)
async def edit_internal_bot_customer_requisites(
    payload: BotCustomerRequisitesEditRequest,
    recognition_id: int = Path(ge=1),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_bot_request_scope),
) -> BotCustomerRequisitesRecognitionResponse:
    """Correct supplied fields on an open Telegram draft using its expected revision.
    Returns validation feedback and a fresh duplicate preview. Changes apply only to
    the draft. Requires the service bearer and originating Manager in the selected company.
    Access denial returns 403, missing drafts 404, completed or stale drafts 409 and
    malformed patches 422. After a conflict, read the draft again before retrying.
    """
    with _requisites_errors():
        recognition = await BotCustomerRequisitesApiService.edit_for_manager(
            session, telegram_id=payload.telegram_id, recognition_id=recognition_id,
            tenant_scope=tenant_scope, fields=payload.fields, expected_revision=payload.expected_revision,
        )
    return BotCustomerRequisitesRecognitionResponse.model_validate(recognition)


@router.post(
    "/customers/requisites/{recognition_id}/action",
    response_model=BotCustomerRequisitesActionResponse,
    operation_id="apply_internal_bot_customer_requisites_action_v1",
)
async def apply_internal_bot_customer_requisites_action(
    payload: BotCustomerRequisitesActionRequest,
    recognition_id: int = Path(ge=1),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_bot_request_scope),
) -> BotCustomerRequisitesActionResponse:
    """
    Apply create, update, use or cancel to the originating Manager's draft in the selected
    tenant. Send the revision shown in the preview. Edited drafts require a revision.
    Repeating the accepted action and revision returns changed=false. Foreign actors get
    403, missing drafts 404, stale revisions or incompatible actions 409, invalid fields
    422. Only create and update write a customer.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    with _requisites_errors():
        result = await BotCustomerRequisitesApiService.apply_action_for_manager(
            session,
            telegram_id=payload.telegram_id,
            recognition_id=recognition_id,
            action=payload.action,
            expected_revision=payload.expected_revision,
            tenant_scope=tenant_scope,
        )
    return BotCustomerRequisitesActionResponse(
        recognition=BotCustomerRequisitesRecognitionResponse.model_validate(result.recognition),
        customer=result.customer,
        changed=result.changed,
    )
