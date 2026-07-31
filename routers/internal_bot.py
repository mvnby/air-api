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
    BotQuickOrderParseRequest,
    BotQuickOrderParseResponse,
    BotStaffContextResponse,
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
    "/quick-orders/parse",
    response_model=BotQuickOrderParseResponse,
    operation_id="parse_internal_bot_quick_order_v1",
)
async def parse_internal_bot_quick_order(
    payload: BotQuickOrderParseRequest,
    session: AsyncSession = Depends(get_session),
) -> BotQuickOrderParseResponse:
    try:
        draft = await BotQuickOrderApiService.parse_for_manager(
            session,
            telegram_id=payload.telegram_id,
            text=payload.text,
        )
    except BotQuickOrderAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return BotQuickOrderParseResponse(draft=BotQuickOrderDraft.model_validate(draft))


@router.post(
    "/quick-orders",
    response_model=BotQuickOrderCreateResponse,
    operation_id="create_internal_bot_quick_order_v1",
)
async def create_internal_bot_quick_order(
    payload: BotQuickOrderCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> BotQuickOrderCreateResponse:
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
