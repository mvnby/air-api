"""Manager transport for standalone findings on open and closed maintenance orders."""
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.maintenance_observations import (
    CreateMaintenanceObservation, MaintenanceObservationDetail, MaintenanceObservationList, UpdateMaintenanceObservation,
    PrepareMaintenanceDefectAct, MaintenanceDefectActItem, MaintenanceDefectActList,
)
from modules.documents.application.maintenance_act_preparation import MaintenanceActPreparationService
from modules.documents.application.errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from modules.documents.api.managed_documents_artifacts import _legacy_private_storage
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username, require_manager_access
from models.tenancy import TenantScope
from routers import manager_operation_ids as operation_ids
from routers.manager_service_attachments import _read_upload_limited
from schemas import ManagerServiceAttachmentItemResponse
from services.maintenance_observation_service import MaintenanceObservationService as Service, ObservationConflict, ObservationNotFound

router = APIRouter(prefix="/api/manager", tags=["manager-maintenance-observations"], dependencies=[Depends(require_manager_access)])


async def command(session, coroutine):
    try:
        return await coroutine
    except (ObservationNotFound, ObservationConflict, ManagedDocumentConflictError, ManagedDocumentNotFoundError, ValueError) as exc:
        await session.rollback()
        code = 404 if isinstance(exc, (ObservationNotFound, ManagedDocumentNotFoundError)) else 409 if isinstance(exc, (ObservationConflict, ManagedDocumentConflictError)) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/orders/{order_id}/maintenance-observations", response_model=MaintenanceObservationList,
            operation_id=operation_ids.LIST_MANAGER_ORDER_MAINTENANCE_OBSERVATIONS)
async def list_order_observations(order_id: int, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                                  session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """List separate findings from this source order, newest first. Manager role and source
    tenant/storefront plus saved customer ownership are required; inaccessible order returns
    404. limit is 1–100 with offset pagination. Reading changes no service or document state.
    See [maintenance findings](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    return await command(session, Service.list(session, order_id=order_id, limit=limit, offset=offset, scope=scope))


@router.get("/equipment/{equipment_id}/maintenance-observations", response_model=MaintenanceObservationList,
            operation_id=operation_ids.LIST_MANAGER_EQUIPMENT_MAINTENANCE_OBSERVATIONS)
async def list_equipment_observations(equipment_id: int, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                                      session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """List findings currently associated with equipment. Manager role, customer tenant and
    each source order's storefront are checked; inaccessible equipment returns 404.
    limit is 1–100 with offset pagination. Unknown equipment findings remain on the source ТО.
    See [maintenance findings](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    return await command(session, Service.list(session, equipment_id=equipment_id, limit=limit, offset=offset, scope=scope))


@router.post("/orders/{order_id}/maintenance-observations", response_model=MaintenanceObservationDetail, status_code=201,
             operation_id=operation_ids.CREATE_MANAGER_MAINTENANCE_OBSERVATION)
async def create_observation(order_id: int, payload: CreateMaintenanceObservation, actor: str = Depends(get_current_username),
                             session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """Save one factual observation from an open or CLOSED maintenance order. The server
    records author, origin, immutable comment and customer/object context. Equipment is
    optional and must match that context. Manager role and tenant/storefront ownership are
    required. Same command_key and content return the existing ID; key reuse with different
    content returns 409, invalid context 400, inaccessible order 404. No order, document,
    executed service event or commercial decision is created or changed.
    See [maintenance findings](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    return await command(session, Service.create(session, order_id=order_id, payload=payload, actor=actor, scope=scope))


@router.get("/maintenance-observations/{observation_id}", response_model=MaintenanceObservationDetail,
            operation_id=operation_ids.GET_MANAGER_MAINTENANCE_OBSERVATION)
async def get_observation(observation_id: int, session: AsyncSession = Depends(get_session),
                          scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """Read original provenance, current facts, revision history and photo metadata. Manager
    role, source order tenant/storefront and saved customer ownership are required;
    inaccessible finding returns 404. Photo bytes use existing short-lived attachment access.
    See [private attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
    """
    async def read():
        observation = await Service.get(session, observation_id, scope)
        return await Service.detail(session, observation, scope)
    return await command(session, read())


@router.patch("/maintenance-observations/{observation_id}", response_model=MaintenanceObservationDetail,
              operation_id=operation_ids.UPDATE_MANAGER_MAINTENANCE_OBSERVATION)
async def update_observation(observation_id: int, payload: UpdateMaintenanceObservation, actor: str = Depends(get_current_username),
                             session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """Correct facts, recommendation or equipment with expected_version. Manager role,
    source order tenant/storefront and saved customer context are required. Stale versions
    return 409; invalid equipment 400; inaccessible finding 404. A new audited revision is
    saved; original comment, origin, order and issued documents remain unchanged, also on CLOSED ТО.
    See [maintenance findings](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    return await command(session, Service.update(session, observation_id=observation_id, payload=payload, actor=actor, scope=scope))


@router.post("/maintenance-observations/{observation_id}/photos", response_model=ManagerServiceAttachmentItemResponse, status_code=201,
             operation_id=operation_ids.UPLOAD_MANAGER_MAINTENANCE_OBSERVATION_PHOTO)
async def upload_photo(observation_id: int, file: UploadFile = File(...), command_key: UUID = Form(...),
                       actor: str = Depends(get_current_username), session: AsyncSession = Depends(get_session),
                       scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """Upload a private photo attached to exactly this observation. Manager role and source
    tenant/storefront plus customer access are required, including CLOSED ТО. Same key and
    file return the same attachment; different file with that key returns 409. Invalid file
    type/size returns 400, inaccessible observation 404. Existing private storage, previews
    and attachment access are reused; no public URL or service event is created.
    See [private attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
    """
    async def upload():
        content = await _read_upload_limited(file)
        return await Service.upload_photo(session, observation_id=observation_id, key=command_key, content=content,
                                          filename=file.filename or "photo", mime_type=file.content_type, actor=actor, scope=scope)
    return await command(session, upload())


@router.post("/orders/{order_id}/maintenance-defect-acts", response_model=MaintenanceDefectActItem, status_code=201,
             operation_id=operation_ids.PREPARE_MANAGER_MAINTENANCE_DEFECT_ACT)
async def prepare_defect_act(order_id: int, payload: PrepareMaintenanceDefectAct, actor: str = Depends(get_current_username),
                             session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """Explicitly prepare a native defect-act draft from current versions of selected
    findings on one open or CLOSED ТО. Manager and tenant/storefront/customer/object
    ownership are required. Same command key/content returns the same document;
    different content or stale versions return 409, mixed context/missing requisites 400,
    inaccessible source/issuer 404. Creates/reuses a linked NEGOTIATION continuation,
    never executable work, scheduling, a contract or customer delivery. Snapshot sources
    are immutable; preview, issue and delivery use the existing document lifecycle.
    See [maintenance acts](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    return await command(session, MaintenanceActPreparationService.prepare(session, source_order_id=order_id,
        payload=payload, actor=actor, scope=scope, storage=PrivateTemplateSourceStorage(_legacy_private_storage())))


@router.get("/orders/{order_id}/maintenance-defect-acts", response_model=MaintenanceDefectActList,
            operation_id=operation_ids.LIST_MANAGER_MAINTENANCE_DEFECT_ACTS)
async def list_defect_acts(order_id: int, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                          session: AsyncSession = Depends(get_session), scope: TenantScope = Depends(get_current_manager_tenant_scope)):
    """List defect-act preparations linked to a scoped source ТО, including CLOSED history.
    Requires Manager tenant/storefront access to the source and continuation. Missing or
    inaccessible context returns 404. limit is 1–100 with offset pagination. Reading does
    not prepare, issue, send or update documents or observations.
    See [maintenance acts](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    return await command(session, MaintenanceActPreparationService.list(session, source_order_id=order_id,
                                                                       scope=scope, limit=limit, offset=offset))
