"""Private, versioned use-case API consumed by the Telegram bot service."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import (
    BotApiHealthResponse,
    BotCatalogProductLookupResponse,
    BotCatalogProductResponse,
    BotCatalogSearchRequest,
    BotCatalogSearchResponse,
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
from models import OrderStageStatus
from services.bot_access_service import BotAccessService
from services.bot_catalog_service import BotCatalogAccessDeniedError, BotCatalogService
from services.bot_task_mutation_service import (
    BotTaskMutationAccessDeniedError,
    BotTaskMutationConflictError,
    BotTaskMutationService,
)
from services.bot_task_read_service import BotTaskAccessDeniedError, BotTaskReadService


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
) -> BotTaskListResponse:
    try:
        tasks = await BotTaskReadService.list_for_staff(
            session,
            telegram_id=payload.telegram_id,
            limit=payload.limit,
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
) -> BotTaskStatusUpdateResponse:
    try:
        result = await BotTaskMutationService.update_stage_status(
            session,
            telegram_id=payload.telegram_id,
            stage_id=stage_id,
            status=OrderStageStatus(payload.status),
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
) -> BotTaskReportSaveResponse:
    try:
        result = await BotTaskMutationService.save_stage_report(
            session,
            telegram_id=payload.telegram_id,
            stage_id=stage_id,
            report=payload.report,
        )
    except BotTaskMutationAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return BotTaskReportSaveResponse(
        stage_id=result.stage_id,
        changed=result.changed,
    )
