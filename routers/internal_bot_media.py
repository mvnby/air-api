"""Private Telegram bot API for order files and equipment nameplates."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import (
    BotNameplateApplyResponse,
    BotNameplateRecognitionResponse,
    BotOrderAttachmentResponse,
    BotOrderBriefResponse,
    BotOrderListRequest,
    BotOrderListResponse,
)
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from routers.internal_bot_common import parse_json_object, read_bot_upload
from services.bot_api_access import BotUseCaseAccessDeniedError
from services.bot_media_api_service import BotMediaApiService


router = APIRouter(
    prefix="/api/internal/bot/v1",
    tags=["internal bot v1 media"],
    dependencies=[Depends(require_bot_api_token)],
)


def _deny(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


def _missing() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order is not available")


@router.post(
    "/orders/recent",
    response_model=BotOrderListResponse,
    operation_id="list_internal_bot_recent_orders_v1",
)
async def list_recent_orders(
    payload: BotOrderListRequest,
    session: AsyncSession = Depends(get_session),
) -> BotOrderListResponse:
    """
    List recent system-tenant orders for an active Manager Telegram actor (403 otherwise).
    Uses the requested response bound; it is not a storefront catalog or a general tenant
    selector.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        orders = await BotMediaApiService.list_recent_orders(
            session, telegram_id=payload.telegram_id, limit=payload.limit
        )
    except BotUseCaseAccessDeniedError as exc:
        raise _deny(exc) from exc
    return BotOrderListResponse(
        items=[BotOrderBriefResponse.model_validate(order) for order in orders]
    )


@router.post(
    "/orders/{order_id}/attachments",
    response_model=BotOrderAttachmentResponse,
    operation_id="attach_internal_bot_order_file_v1",
)
async def attach_order_file(
    order_id: int = Path(ge=1),
    telegram_id: int = Form(ge=1),
    file_id: str = Form(min_length=1, max_length=500),
    telegram_chat_id: int | None = Form(default=None),
    telegram_message_id: int | None = Form(default=None),
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
) -> BotOrderAttachmentResponse:
    """
    Attach a nonempty file (at most 10 MB) to an accessible system-tenant order. Requires
    active staff; Managers can attach beyond their own assigned execution. Access denial
    returns 403 and unavailable order 404. Empty/oversize uploads return 422/413. file_id
    deduplicates attachments; inspect already_attached.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    content, filename, mime_type = await read_bot_upload(file)
    try:
        result = await BotMediaApiService.attach_to_order(
            session,
            telegram_id=telegram_id,
            order_id=order_id,
            content=content,
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
        )
    except BotUseCaseAccessDeniedError as exc:
        raise _deny(exc) from exc
    if result is None:
        raise _missing()
    return BotOrderAttachmentResponse(
        order_id=order_id,
        already_attached=bool(result.get("already_attached")),
    )


@router.post(
    "/repair-nameplates/orders",
    response_model=BotOrderListResponse,
    operation_id="list_internal_bot_repair_nameplate_orders_v1",
)
async def list_repair_nameplate_orders(
    payload: BotOrderListRequest,
    session: AsyncSession = Depends(get_session),
) -> BotOrderListResponse:
    """
    List repair orders in the system tenant available to the staff actor under repair-order
    access rules. Managers may access beyond assigned execution; non-staff return 403.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        orders = await BotMediaApiService.list_repair_orders(
            session, telegram_id=payload.telegram_id, limit=payload.limit
        )
    except BotUseCaseAccessDeniedError as exc:
        raise _deny(exc) from exc
    return BotOrderListResponse(
        items=[BotOrderBriefResponse.model_validate(order) for order in orders]
    )


@router.post(
    "/repair-nameplates/recognize",
    response_model=BotNameplateRecognitionResponse,
    operation_id="recognize_internal_bot_repair_nameplate_v1",
)
async def recognize_repair_nameplate(
    telegram_id: int = Form(ge=1),
    order_id: int = Form(ge=1),
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
) -> BotNameplateRecognitionResponse:
    """
    Recognize an equipment nameplate for a repair order accessible to the staff actor in the
    system tenant. Does not apply the recognized data. Non-staff return 403, unavailable
    order 404, empty/oversize upload 422/413; file must be at most 10 MB.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    content, filename, mime_type = await read_bot_upload(file)
    try:
        result = await BotMediaApiService.recognize_repair_nameplate(
            session,
            telegram_id=telegram_id,
            order_id=order_id,
            content=content,
            filename=filename,
            mime_type=mime_type,
        )
    except BotUseCaseAccessDeniedError as exc:
        raise _deny(exc) from exc
    if result is None:
        raise _missing()
    return BotNameplateRecognitionResponse.model_validate(result)


@router.post(
    "/repair-nameplates/apply",
    response_model=BotNameplateApplyResponse,
    operation_id="apply_internal_bot_repair_nameplate_v1",
)
async def apply_repair_nameplate(
    telegram_id: int = Form(ge=1),
    order_id: int = Form(ge=1),
    file_id: str = Form(min_length=1, max_length=500),
    raw_text: str = Form(max_length=50_000),
    extracted_json: str = Form(max_length=100_000),
    validation_json: str = Form(max_length=100_000),
    telegram_chat_id: int | None = Form(default=None),
    telegram_message_id: int | None = Form(default=None),
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
) -> BotNameplateApplyResponse:
    """
    Apply submitted recognition data and attach its file to an accessible repair order in
    the system tenant. Requires active staff with order access (403/404 otherwise).
    extracted_json and validation_json must be JSON objects; invalid JSON/empty file returns
    422 and file above 10 MB returns 413. Telegram file_id participates in attachment
    reconciliation.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    content, filename, mime_type = await read_bot_upload(file)
    try:
        result = await BotMediaApiService.apply_repair_nameplate(
            session,
            telegram_id=telegram_id,
            order_id=order_id,
            content=content,
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            raw_text=raw_text,
            extracted=parse_json_object(extracted_json, field_name="extracted_json"),
            validation_flags=parse_json_object(validation_json, field_name="validation_json"),
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
        )
    except BotUseCaseAccessDeniedError as exc:
        raise _deny(exc) from exc
    if result is None:
        raise _missing()
    return BotNameplateApplyResponse(result=result)


@router.post(
    "/warranty-nameplates/orders",
    response_model=BotOrderListResponse,
    operation_id="list_internal_bot_warranty_nameplate_orders_v1",
)
async def list_warranty_nameplate_orders(
    payload: BotOrderListRequest,
    session: AsyncSession = Depends(get_session),
) -> BotOrderListResponse:
    """
    List warranty orders available to the staff actor in the system tenant and return the
    service’s execution/Manager scope marker. Non-staff return 403; access is checked before
    listing.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotMediaApiService.list_warranty_orders(
            session, telegram_id=payload.telegram_id, limit=payload.limit
        )
    except BotUseCaseAccessDeniedError as exc:
        raise _deny(exc) from exc
    return BotOrderListResponse(
        items=[BotOrderBriefResponse.model_validate(order) for order in result.get("items", [])],
        scope=str(result.get("scope") or "execution"),
    )


@router.post(
    "/warranty-nameplates/recognize",
    response_model=BotNameplateRecognitionResponse,
    operation_id="recognize_internal_bot_warranty_nameplate_v1",
)
async def recognize_warranty_nameplate(
    telegram_id: int = Form(ge=1),
    order_id: int = Form(ge=1),
    unit_type: str = Form(pattern=r"^(indoor_unit|outdoor_unit)$"),
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
) -> BotNameplateRecognitionResponse:
    """
    Recognize the selected indoor/outdoor unit nameplate for an accessible warranty order in
    the system tenant, without applying it. Requires active staff (403); unavailable order
    returns 404. Empty/oversize upload returns 422/413; file must be at most 10 MB.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    content, filename, mime_type = await read_bot_upload(file)
    try:
        result = await BotMediaApiService.recognize_warranty_nameplate(
            session,
            telegram_id=telegram_id,
            order_id=order_id,
            unit_type=unit_type,
            content=content,
            filename=filename,
            mime_type=mime_type,
        )
    except BotUseCaseAccessDeniedError as exc:
        raise _deny(exc) from exc
    if result is None:
        raise _missing()
    return BotNameplateRecognitionResponse.model_validate(result)


@router.post(
    "/warranty-nameplates/apply",
    response_model=BotNameplateApplyResponse,
    operation_id="apply_internal_bot_warranty_nameplate_v1",
)
async def apply_warranty_nameplate(
    telegram_id: int = Form(ge=1),
    order_id: int = Form(ge=1),
    unit_type: str = Form(pattern=r"^(indoor_unit|outdoor_unit)$"),
    file_id: str = Form(min_length=1, max_length=500),
    raw_text: str = Form(max_length=50_000),
    extracted_json: str = Form(max_length=100_000),
    validation_json: str = Form(max_length=100_000),
    telegram_chat_id: int | None = Form(default=None),
    telegram_message_id: int | None = Form(default=None),
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
) -> BotNameplateApplyResponse:
    """
    Apply submitted indoor/outdoor nameplate data and attach its file to an accessible
    warranty order in the system tenant. Requires active staff (403); unavailable order
    returns 404. JSON object parsing and empty file validation return 422; file above 10 MB
    returns 413. Telegram file_id is passed to the attachment workflow.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    content, filename, mime_type = await read_bot_upload(file)
    try:
        result = await BotMediaApiService.apply_warranty_nameplate(
            session,
            telegram_id=telegram_id,
            order_id=order_id,
            unit_type=unit_type,
            content=content,
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            raw_text=raw_text,
            extracted=parse_json_object(extracted_json, field_name="extracted_json"),
            validation_flags=parse_json_object(validation_json, field_name="validation_json"),
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
        )
    except BotUseCaseAccessDeniedError as exc:
        raise _deny(exc) from exc
    if result is None:
        raise _missing()
    return BotNameplateApplyResponse(result=result)
