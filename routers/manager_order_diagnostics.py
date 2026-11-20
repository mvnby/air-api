"""Manager equipment inspections and native technical acts for one order site."""

from collections.abc import Awaitable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.api.managed_documents_artifacts import _legacy_private_storage
from modules.documents.application.errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from modules.documents.application.order_technical_acts import OrderTechnicalActService
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from routers import manager_operation_ids as operation_ids
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_connector_mcp import ConnectorWriteResult
from schemas_order_diagnostics import (
    OrderInspectionReadInput,
    OrderInspectionSaved,
    OrderInspectionSaveInput,
    OrderInspectionSavePayload,
    OrderInspectionState,
    OrderTechnicalActPrepared,
    PrepareOrderTechnicalActInput,
    PrepareOrderTechnicalActPayload,
)
from services.order_inspection_service import OrderInspectionConflict, OrderInspectionService
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable


router = APIRouter(
    prefix="/api/manager/orders/{order_id}/sites/{site_id}",
    tags=["manager-order-diagnostics"],
    route_class=ManagerPermissionRoute,
    dependencies=[Depends(require_manager_access)],
)
T = TypeVar("T")


async def run_order_diagnostic_command(command: Awaitable[T]) -> T:
    try:
        return await command
    except (LookupError, ManagedDocumentNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (OrderInspectionConflict, ManagedDocumentConflictError, PublicWriteIdempotencyConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (PublicWriteIdempotencyUnavailable, OSError) as exc:
        raise HTTPException(status_code=503, detail="Операция временно недоступна. Повторите с тем же ключом.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/equipment/{equipment_id}/inspection", response_model=OrderInspectionState,
            operation_id=operation_ids.GET_MANAGER_ORDER_INSPECTION)
async def get_order_inspection(
    order_id: int = Path(gt=0),
    site_id: int = Path(gt=0),
    equipment_id: int = Path(gt=0),
    version: int | None = Query(default=None, gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """Read the current inspection or one immutable version for scoped equipment."""
    data = OrderInspectionReadInput(order_id=order_id, site_id=site_id, equipment_id=equipment_id, version=version)
    return await run_order_diagnostic_command(OrderInspectionService.read(session, CommandActor.from_auth(auth), data))


@router.put("/equipment/{equipment_id}/inspection", response_model=ConnectorWriteResult[OrderInspectionSaved],
            operation_id=operation_ids.SAVE_MANAGER_ORDER_INSPECTION)
async def save_order_inspection(
    payload: OrderInspectionSavePayload,
    order_id: int = Path(gt=0),
    site_id: int = Path(gt=0),
    equipment_id: int = Path(gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """Record a new version with checked facts, recommendations and performed actions kept separately."""
    data = OrderInspectionSaveInput(order_id=order_id, site_id=site_id, equipment_id=equipment_id, **payload.model_dump())
    outcome = await run_order_diagnostic_command(OrderInspectionService.save(session, CommandActor.from_auth(auth), data))
    return ConnectorWriteResult(result=outcome.value, replayed=outcome.replayed)


@router.post("/technical-acts", response_model=ConnectorWriteResult[OrderTechnicalActPrepared],
             operation_id=operation_ids.PREPARE_MANAGER_ORDER_TECHNICAL_ACT)
async def prepare_order_technical_act(
    payload: PrepareOrderTechnicalActPayload,
    order_id: int = Path(gt=0),
    site_id: int = Path(gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """Prepare a native draft for the chosen scope and basis without reserving an official number."""
    data = PrepareOrderTechnicalActInput(order_id=order_id, site_id=site_id, **payload.model_dump())
    outcome = await run_order_diagnostic_command(OrderTechnicalActService.prepare(
        session, CommandActor.from_auth(auth), data, template_storage=PrivateTemplateSourceStorage(_legacy_private_storage()),
    ))
    return ConnectorWriteResult(result=outcome.value, replayed=outcome.replayed)
