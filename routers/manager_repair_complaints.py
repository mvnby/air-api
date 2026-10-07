import httpx
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username, require_system_manager_tenant_scope
from routers.manager_operation_ids import (
    CREATE_MANAGER_REPAIR_COMPLAINT_PRESET,
    DELETE_MANAGER_REPAIR_COMPLAINT_PRESET,
    GENERATE_MANAGER_REPAIR_ACT_AI_DRAFT,
    LIST_MANAGER_REPAIR_COMPLAINT_PRESETS,
    UPDATE_MANAGER_REPAIR_COMPLAINT_PRESET,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    ManagerActionMessageResponse,
    ManagerRepairActAiDraftPayload,
    ManagerRepairActAiDraftResponse,
    ManagerRepairComplaintPresetCreatePayload,
    ManagerRepairComplaintPresetListResponse,
    ManagerRepairComplaintPresetResponse,
    ManagerRepairComplaintPresetUpdatePayload,
)
from core.config import settings
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST
from services.defect_act_ai_service import DefectActAIService
from services.repair_complaint_service import RepairComplaintService


router = APIRouter(
    prefix="/api/manager/repair-complaints",
    tags=["manager/repair-complaints"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)


@router.get("", response_model=ManagerRepairComplaintPresetListResponse, operation_id=LIST_MANAGER_REPAIR_COMPLAINT_PRESETS)
async def list_manager_repair_complaint_presets(
    q: str = Query(""),
    complaint_group: str | None = Query(None),
    include_inactive: bool = Query(False),
    favorites_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """
    Read shared complaint presets filtered by text, group and favorite status; inactive
    presets are excluded by default. limit is 1–200, default 100; results follow
    favorite/sort/group/name ordering. No repair order or diagnostic statement is saved.

    Access and scope: Manager access is required; these definitions are shared across
    tenants. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    items = await RepairComplaintService.list_presets(
        session=session,
        q=q,
        complaint_group=complaint_group,
        include_inactive=include_inactive,
        favorites_only=favorites_only,
        limit=limit,
    )
    return ManagerRepairComplaintPresetListResponse(items=items)


@router.post(
    "",
    response_model=ManagerRepairComplaintPresetResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_REPAIR_COMPLAINT_PRESET,
)
async def create_manager_repair_complaint_preset(
    payload: ManagerRepairComplaintPresetCreatePayload,
    session: AsyncSession = Depends(get_session),
):
    """
    Create a shared complaint preset after cleaning whitespace. Empty phrase returns 400 and
    an existing normalized group/phrase returns 409. This defines reusable text without
    modifying repair orders; repeated creation is subject to duplicate detection rather than
    an idempotency receipt.

    Access and scope: system-tenant Manager access is required; these are shared platform
    definitions. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await RepairComplaintService.create_preset(session=session, payload=payload)


@router.post(
    "/ai-draft",
    response_model=ManagerRepairActAiDraftResponse,
    operation_id=GENERATE_MANAGER_REPAIR_ACT_AI_DRAFT,
    dependencies=[Depends(require_system_manager_tenant_scope)],
)
async def generate_manager_repair_act_ai_draft(payload: ManagerRepairActAiDraftPayload):
    """
    Generate structured repair diagnostic metadata using the configured DeepSeek provider
    and local defect templates. The response is a draft; no order, diagnosis or act document
    is saved. Value/input errors and HTTP provider failures caught by this route return 400.
    Repeats call the provider again and may produce different text.

    Access and scope: system-tenant Manager access is required; these are shared platform
    definitions. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        repair_meta = await DefectActAIService.generate_repair_meta(payload)
    except (ValueError, httpx.HTTPError) as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=GENERATE_MANAGER_REPAIR_ACT_AI_DRAFT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    return ManagerRepairActAiDraftResponse(repair_meta=repair_meta, model=settings.DEEPSEEK_MODEL)


@router.put(
    "/{preset_id}",
    response_model=ManagerRepairComplaintPresetResponse,
    operation_id=UPDATE_MANAGER_REPAIR_COMPLAINT_PRESET,
)
async def update_manager_repair_complaint_preset(
    preset_id: int,
    payload: ManagerRepairComplaintPresetUpdatePayload,
    session: AsyncSession = Depends(get_session),
):
    """
    Update submitted preset fields after cleaning text. Missing preset returns 404, empty
    phrase 400 and conflicting normalized group/phrase 409. Changes affect future selection
    and do not rewrite text already saved in repair orders.

    Access and scope: system-tenant Manager access is required; these are shared platform
    definitions. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await RepairComplaintService.update_preset(session=session, preset_id=preset_id, payload=payload)


@router.delete(
    "/{preset_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_REPAIR_COMPLAINT_PRESET,
)
async def delete_manager_repair_complaint_preset(
    preset_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Permanently delete a shared complaint preset. Missing preset returns 404, including
    repeats. This does not remove complaint text already copied into repair orders.

    Access and scope: system-tenant Manager access is required; these are shared platform
    definitions. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    await RepairComplaintService.delete_preset(session=session, preset_id=preset_id)
    return ManagerActionMessageResponse(message="Repair complaint preset deleted successfully")
