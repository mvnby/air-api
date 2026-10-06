"""Private, versioned use-case API consumed by the Telegram bot service."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import (
    BotApiHealthResponse,
    BotCatalogProductLookupResponse,
    BotCatalogProductResponse,
    BotCatalogSearchRequest,
    BotCatalogSearchResponse,
    BotCustomerRequisitesActionRequest,
    BotCustomerRequisitesActionResponse,
    BotCustomerRequisitesRecognitionResponse,
    BotCustomerRequisitesTextRequest,
    BotQuickOrderCreateRequest,
    BotQuickOrderCreateResponse,
    BotQuickOrderDraft,
    BotQuickOrderDraftStartRequest,
    BotQuickOrderDraftPatchRequest,
    BotQuickOrderDraftActionRequest,
    BotQuickOrderDraftSessionResponse,
    BotQuickOrderCustomerSearchRequest,
    BotQuickOrderCustomerSearchResponse,
    BotQuickOrderParseRequest,
    BotQuickOrderParseResponse,
    BotStaffContextResponse,
    BotTaskAttachmentResponse,
    BotTaskListRequest,
    BotTaskListResponse,
    BotTaskReportSaveRequest,
    BotTaskReportSaveResponse,
    BotTaskResponse,
    BotTaskStatusUpdateRequest,
    BotTaskStatusUpdateResponse,
)
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from core.tenant_scope import get_system_tenant_scope
from models import OrderStageStatus
from models.tenancy import TenantScope
from routers.internal_bot_common import read_bot_upload
from services.bot_access_service import BotAccessService
from services.bot_catalog_service import BotCatalogAccessDeniedError, BotCatalogService
from services.bot_customer_requisites_api_service import (
    BotCustomerRequisitesAccessDeniedError,
    BotCustomerRequisitesApiService,
    BotCustomerRequisitesConflictError,
    BotCustomerRequisitesNotFoundError,
)
from services.bot_quick_order_api_service import (
    BotQuickOrderAccessDeniedError,
    BotQuickOrderApiService,
)
from services.bot_quick_order_draft_service import (
    BotQuickOrderDraftService,
    BotQuickOrderDraftConflictError,
    BotQuickOrderDraftNotFoundError,
)
from services.bot_task_mutation_service import (
    BotTaskMutationAccessDeniedError,
    BotTaskMutationConflictError,
    BotTaskMutationService,
)
from services.bot_task_read_service import BotTaskAccessDeniedError, BotTaskReadService
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService


router = APIRouter(
    prefix="/api/internal/bot/v1",
    tags=["internal bot v1"],
    dependencies=[Depends(require_bot_api_token)],
)


@router.get(
    "/health",
    response_model=BotApiHealthResponse,
    operation_id="get_internal_bot_api_health_v1",
)
async def get_internal_bot_api_health() -> BotApiHealthResponse:
    """
    Check that the authenticated bot API is reachable and report its v1 contract marker.
    Does not check a Telegram actor or database readiness.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    return BotApiHealthResponse()


@router.get(
    "/staff/context/{telegram_id}",
    response_model=BotStaffContextResponse,
    operation_id="get_internal_bot_staff_context_v1",
)
async def get_internal_bot_staff_context(
    telegram_id: int = Path(ge=1),
    session: AsyncSession = Depends(get_session),
) -> BotStaffContextResponse:
    """
    Resolve the active staff context of a Telegram identity, including Manager/executor
    roles and legacy installer linkage. A non-staff identity is represented by
    is_staff=false rather than a business permission grant.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    context = await BotAccessService.get_context(session, telegram_id)
    return BotStaffContextResponse(
        telegram_id=context.telegram_id,
        is_staff=context.is_staff,
        display_name=context.display_name,
        primary_role=context.primary_role,
        roles=context.roles,
        legacy_installer_id=context.legacy_installer_id,
        is_manager=context.is_manager,
        is_executor=context.is_executor,
    )


@router.post(
    "/catalog/search",
    response_model=BotCatalogSearchResponse,
    operation_id="search_internal_bot_catalog_v1",
)
async def search_internal_bot_catalog(
    payload: BotCatalogSearchRequest,
    session: AsyncSession = Depends(get_session),
) -> BotCatalogSearchResponse:
    """
    Search the shared product catalog for an active staff Telegram actor (403 otherwise).
    Returns internal bot product projections, not storefront-only catalog cards.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        products = await BotCatalogService.search_for_staff(
            session,
            telegram_id=payload.telegram_id,
            query=payload.query,
            limit=payload.limit,
        )
    except BotCatalogAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return BotCatalogSearchResponse(
        items=[BotCatalogProductResponse.model_validate(product) for product in products]
    )


@router.get(
    "/catalog/products/{product_id}",
    response_model=BotCatalogProductLookupResponse,
    operation_id="get_internal_bot_catalog_product_v1",
)
async def get_internal_bot_catalog_product(
    product_id: int = Path(ge=1),
    telegram_id: int = Query(ge=1),
    session: AsyncSession = Depends(get_session),
) -> BotCatalogProductLookupResponse:
    """
    Read one shared catalog product for an active staff Telegram actor (403 otherwise). A
    missing product is product=null in a successful lookup response, not 404.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        product = await BotCatalogService.get_product_for_staff(
            session,
            telegram_id=telegram_id,
            product_id=product_id,
        )
    except BotCatalogAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return BotCatalogProductLookupResponse(
        product=BotCatalogProductResponse.model_validate(product) if product else None
    )


@router.post(
    "/tasks/my",
    response_model=BotTaskListResponse,
    operation_id="list_internal_bot_my_tasks_v1",
)
async def list_internal_bot_my_tasks(
    payload: BotTaskListRequest,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_system_tenant_scope),
) -> BotTaskListResponse:
    """
    Read work stages assigned to the actor’s linked installer in the system tenant, with
    optional date/status filters. Active staff access is required (403 otherwise); staff
    without an installer linkage receive an empty list.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        tasks = await BotTaskReadService.list_for_staff(
            session,
            telegram_id=payload.telegram_id,
            limit=payload.limit,
            date_from=payload.date_from,
            date_to=payload.date_to,
            statuses=payload.statuses,
            tenant_scope=tenant_scope,
        )
    except BotTaskAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return BotTaskListResponse(
        items=[BotTaskResponse.model_validate(task) for task in tasks]
    )


@router.post(
    "/tasks/stages/{stage_id}/status",
    response_model=BotTaskStatusUpdateResponse,
    operation_id="update_internal_bot_task_status_v1",
)
async def update_internal_bot_task_status(
    payload: BotTaskStatusUpdateRequest,
    stage_id: int = Path(ge=1),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_system_tenant_scope),
) -> BotTaskStatusUpdateResponse:
    """
    Set the status of a stage assigned to the actor’s installer in the system tenant.
    Missing/inaccessible/unassigned stage returns 403; an invalid state transition returns
    409. changed reports whether a transition occurred; this is not a generic idempotency
    receipt.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotTaskMutationService.update_stage_status(
            session,
            telegram_id=payload.telegram_id,
            stage_id=stage_id,
            status=OrderStageStatus(payload.status),
            tenant_scope=tenant_scope,
        )
    except BotTaskMutationAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except BotTaskMutationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return BotTaskStatusUpdateResponse(
        stage_id=result.stage_id,
        status=result.status.value,
        changed=result.changed,
    )


@router.post(
    "/tasks/stages/{stage_id}/report",
    response_model=BotTaskReportSaveResponse,
    operation_id="save_internal_bot_task_report_v1",
)
async def save_internal_bot_task_report(
    payload: BotTaskReportSaveRequest,
    stage_id: int = Path(ge=1),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_system_tenant_scope),
) -> BotTaskReportSaveResponse:
    """
    Save a normalized installer report on the actor’s assigned stage in the system tenant.
    Missing/inaccessible stage returns 403. Repeating the same normalized report returns
    changed=false.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotTaskMutationService.save_stage_report(
            session,
            telegram_id=payload.telegram_id,
            stage_id=stage_id,
            report=payload.report,
            tenant_scope=tenant_scope,
        )
    except BotTaskMutationAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return BotTaskReportSaveResponse(
        stage_id=result.stage_id,
        changed=result.changed,
    )


@router.post(
    "/tasks/stages/{stage_id}/attachments",
    response_model=BotTaskAttachmentResponse,
    operation_id="attach_internal_bot_task_stage_file_v1",
)
async def attach_internal_bot_task_stage_file(
    stage_id: int = Path(ge=1),
    telegram_id: int = Form(ge=1),
    file_id: str = Form(min_length=1, max_length=255),
    telegram_chat_id: int | None = Form(default=None),
    telegram_message_id: int | None = Form(default=None),
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_system_tenant_scope),
) -> BotTaskAttachmentResponse:
    """
    Attach a nonempty file of at most 10 MB to the actor’s assigned stage in the system
    tenant. Inaccessible stage returns 403, empty content 422 and oversize content 413.
    file_id provides attachment deduplication; inspect already_attached on retries.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    content, filename, mime_type = await read_bot_upload(file)
    try:
        result = await BotTaskMutationService.attach_stage_attachment(
            session,
            telegram_id=telegram_id,
            stage_id=stage_id,
            file_id=file_id,
            filename=filename,
            mime_type=mime_type,
            content=content,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            tenant_scope=tenant_scope,
        )
    except BotTaskMutationAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return BotTaskAttachmentResponse(
        stage_id=result.stage_id,
        order_id=result.order_id,
        already_attached=result.already_attached,
    )


@router.post(
    "/quick-orders/parse",
    response_model=BotQuickOrderParseResponse,
    operation_id="parse_internal_bot_quick_order_v1",
)
async def parse_internal_bot_quick_order(
    payload: BotQuickOrderParseRequest,
    session: AsyncSession = Depends(get_session),
) -> BotQuickOrderParseResponse:
    """
    Parse text into an editable quick-order draft for an active Manager Telegram actor (403
    otherwise). Does not create an order or start a durable draft session.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        draft = await BotQuickOrderApiService.parse_for_manager(
            session,
            telegram_id=payload.telegram_id,
            text=payload.text,
        )
    except BotQuickOrderAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return BotQuickOrderParseResponse(draft=BotQuickOrderDraft.model_validate(draft))


def _draft_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BotQuickOrderAccessDeniedError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, BotQuickOrderDraftNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, BotQuickOrderDraftConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.post("/quick-orders/drafts", response_model=BotQuickOrderDraftSessionResponse,
             operation_id="start_internal_bot_quick_order_draft_v1")
async def start_internal_bot_quick_order_draft(
    payload: BotQuickOrderDraftStartRequest, session: AsyncSession = Depends(get_session)
) -> BotQuickOrderDraftSessionResponse:
    """
    Start a durable quick-order draft owned by the active Manager Telegram actor in the
    system tenant. The response supplies draft_id and version for subsequent edits. Access
    denial returns 403, service draft conflicts 409 and invalid draft input 422.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotQuickOrderDraftService.start(session, **payload.model_dump())
    except (BotQuickOrderAccessDeniedError, BotQuickOrderDraftNotFoundError,
            BotQuickOrderDraftConflictError, ValueError) as exc:
        raise _draft_error(exc) from exc
    return BotQuickOrderDraftSessionResponse.model_validate(result)


@router.post("/quick-orders/customers/search", response_model=BotQuickOrderCustomerSearchResponse,
             operation_id="search_internal_bot_quick_order_customers_v1")
async def search_internal_bot_quick_order_customers(
    payload: BotQuickOrderCustomerSearchRequest, session: AsyncSession = Depends(get_session)
) -> BotQuickOrderCustomerSearchResponse:
    """
    Search customer candidates in the system tenant for an active Manager Telegram actor.
    Access denial returns 403; invalid search input returns 422. Search does not create or
    modify a customer.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotQuickOrderDraftService.search_customers(session, **payload.model_dump())
    except (BotQuickOrderAccessDeniedError, ValueError) as exc:
        raise _draft_error(exc) from exc
    return BotQuickOrderCustomerSearchResponse.model_validate(result)


@router.get("/quick-orders/drafts/{draft_id}", response_model=BotQuickOrderDraftSessionResponse,
            operation_id="get_internal_bot_quick_order_draft_v1")
async def get_internal_bot_quick_order_draft(
    draft_id: str, telegram_id: int = Query(ge=1), session: AsyncSession = Depends(get_session)
) -> BotQuickOrderDraftSessionResponse:
    """
    Read a durable draft belonging to the active Manager Telegram actor. Access denial
    returns 403; unavailable draft returns 404. Read version before issuing an edit or
    action.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotQuickOrderDraftService.get(session, telegram_id=telegram_id, draft_id=draft_id)
    except (BotQuickOrderAccessDeniedError, BotQuickOrderDraftNotFoundError) as exc:
        raise _draft_error(exc) from exc
    return BotQuickOrderDraftSessionResponse.model_validate(result)


@router.patch("/quick-orders/drafts/{draft_id}", response_model=BotQuickOrderDraftSessionResponse,
              operation_id="patch_internal_bot_quick_order_draft_v1")
async def patch_internal_bot_quick_order_draft(
    draft_id: str, payload: BotQuickOrderDraftPatchRequest,
    session: AsyncSession = Depends(get_session)
) -> BotQuickOrderDraftSessionResponse:
    """
    Patch the actor’s active durable draft, checking expected_version and incrementing its
    version. Requires active Manager access (403); missing draft returns 404, stale/inactive
    draft 409 and invalid changes 422. On conflict reread the draft before editing.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotQuickOrderDraftService.patch(session, draft_id=draft_id, **payload.model_dump())
    except (BotQuickOrderAccessDeniedError, BotQuickOrderDraftNotFoundError,
            BotQuickOrderDraftConflictError, ValueError) as exc:
        raise _draft_error(exc) from exc
    return BotQuickOrderDraftSessionResponse.model_validate(result)


@router.post("/quick-orders/drafts/{draft_id}/cancel", response_model=BotQuickOrderDraftSessionResponse,
             operation_id="cancel_internal_bot_quick_order_draft_v1")
async def cancel_internal_bot_quick_order_draft(
    draft_id: str, payload: BotQuickOrderDraftActionRequest,
    session: AsyncSession = Depends(get_session)
) -> BotQuickOrderDraftSessionResponse:
    """
    Cancel the actor’s active durable draft using expected_version. Requires active Manager
    access (403); missing draft returns 404, stale or inactive draft 409 and invalid input
    422. Cancellation increments version.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotQuickOrderDraftService.cancel(session, draft_id=draft_id, **payload.model_dump())
    except (BotQuickOrderAccessDeniedError, BotQuickOrderDraftNotFoundError,
            BotQuickOrderDraftConflictError, ValueError) as exc:
        raise _draft_error(exc) from exc
    return BotQuickOrderDraftSessionResponse.model_validate(result)


@router.post("/quick-orders/drafts/{draft_id}/create", response_model=BotQuickOrderCreateResponse,
             operation_id="create_internal_bot_quick_order_from_draft_v1")
async def create_internal_bot_quick_order_from_draft(
    draft_id: str, payload: BotQuickOrderDraftActionRequest,
    session: AsyncSession = Depends(get_session)
) -> BotQuickOrderCreateResponse:
    """
    Create an order from the Manager actor’s durable draft in the system tenant. Active
    drafts require expected_version; stale/inactive drafts return 409 and missing drafts
    404. A retry after successful creation returns the recorded order/customer with
    created=false, using a draft-derived idempotency key.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotQuickOrderDraftService.create(session, draft_id=draft_id, **payload.model_dump())
    except (BotQuickOrderAccessDeniedError, BotQuickOrderDraftNotFoundError,
            BotQuickOrderDraftConflictError, ValueError) as exc:
        raise _draft_error(exc) from exc
    return BotQuickOrderCreateResponse.model_validate(result)


@router.post(
    "/quick-orders",
    response_model=BotQuickOrderCreateResponse,
    operation_id="create_internal_bot_quick_order_v1",
)
async def create_internal_bot_quick_order(
    payload: BotQuickOrderCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> BotQuickOrderCreateResponse:
    """
    Create a system-tenant order from a submitted quick-order draft for an active Manager
    Telegram actor (403 otherwise). Uses the supplied idempotency_key; retain it when
    repeating the same creation. Service validation errors return 422; inspect created and
    the returned order/customer IDs.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotQuickOrderApiService.create_for_manager(
            session,
            telegram_id=payload.telegram_id,
            idempotency_key=payload.idempotency_key,
            draft=payload.draft,
        )
    except BotQuickOrderAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return BotQuickOrderCreateResponse(
        order_id=result.order_id,
        customer_id=result.customer_id,
        created=result.created,
    )


@router.post(
    "/customers/requisites/recognize-text",
    response_model=BotCustomerRequisitesRecognitionResponse,
    operation_id="recognize_internal_bot_customer_requisites_text_v1",
)
async def recognize_internal_bot_customer_requisites_text(
    payload: BotCustomerRequisitesTextRequest,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_system_tenant_scope),
) -> BotCustomerRequisitesRecognitionResponse:
    """
    Recognize customer requisites from text for an active Manager Telegram actor in the
    system tenant. Returns a recognition for explicit follow-up action; OCR alone does not
    confirm customer creation. Access denial returns 403 and invalid content 422.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        recognition = await BotCustomerRequisitesApiService.recognize_text_for_manager(
            session,
            telegram_id=payload.telegram_id,
            text_value=payload.text,
            telegram_chat_id=payload.telegram_chat_id,
            telegram_message_id=payload.telegram_message_id,
            tenant_scope=tenant_scope,
        )
    except BotCustomerRequisitesAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return BotCustomerRequisitesRecognitionResponse.model_validate(recognition)


@router.post(
    "/customers/requisites/recognize-file",
    response_model=BotCustomerRequisitesRecognitionResponse,
    operation_id="recognize_internal_bot_customer_requisites_file_v1",
)
async def recognize_internal_bot_customer_requisites_file(
    telegram_id: int = Form(ge=1),
    telegram_chat_id: int | None = Form(default=None),
    telegram_message_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_system_tenant_scope),
) -> BotCustomerRequisitesRecognitionResponse:
    """
    Recognize customer requisites from JPG, PNG, WEBP, PDF, DOC or DOCX, at most 10 MB, for
    an active Manager Telegram actor in the system tenant. Oversize returns 413,
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
    try:
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
    except BotCustomerRequisitesAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
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
    tenant_scope: TenantScope = Depends(get_system_tenant_scope),
) -> BotCustomerRequisitesActionResponse:
    """
    Apply the selected action to an existing requisites recognition in the system tenant for
    its authorized Manager actor. Access denial returns 403, missing recognition 404,
    conflicting action/state 409 and invalid input 422. Returns recognition, customer and
    changed so clients can reconcile the action.

    Access: service Bearer BOT_API_TOKEN is required. Operation-specific Telegram actor
    checks are separate. See [bot
    boundary](https://github.com/mvnby/air-api/blob/main/docs/bot-service-boundary.md#ownership).
    """
    try:
        result = await BotCustomerRequisitesApiService.apply_action_for_manager(
            session,
            telegram_id=payload.telegram_id,
            recognition_id=recognition_id,
            action=payload.action,
            tenant_scope=tenant_scope,
        )
    except BotCustomerRequisitesAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except BotCustomerRequisitesNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BotCustomerRequisitesConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return BotCustomerRequisitesActionResponse(
        recognition=BotCustomerRequisitesRecognitionResponse.model_validate(result.recognition),
        customer=result.customer,
        changed=result.changed,
    )
