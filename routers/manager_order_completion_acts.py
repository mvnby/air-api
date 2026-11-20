"""Manager preparation of checked, multi-site commercial completion acts."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.api.managed_documents_artifacts import _legacy_private_storage
from modules.documents.application.errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from modules.documents.application.order_completion_acts import OrderCompletionActService
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from routers import manager_operation_ids as operation_ids
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_connector_mcp import ConnectorWriteResult
from schemas_order_completion_acts import (
    OrderCompletionActPrepared,
    OrderCompletionActSource,
    OrderCompletionActSourceInput,
    PrepareOrderCompletionActInput,
    PrepareOrderCompletionActPayload,
)
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable


router = APIRouter(
    prefix="/api/manager/orders/{order_id}/completion-acts",
    tags=["manager-order-completion-acts"],
    route_class=ManagerPermissionRoute,
    dependencies=[Depends(require_manager_access)],
)


@router.get("/source", response_model=OrderCompletionActSource,
            operation_id=operation_ids.GET_MANAGER_ORDER_COMPLETION_ACT_SOURCE)
async def get_order_completion_act_source(
    order_id: int = Path(gt=0),
    proposal_id: int = Query(gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """Read the current proposal revision before preparing a scoped closing act."""
    data = OrderCompletionActSourceInput(order_id=order_id, proposal_id=proposal_id)
    try:
        return await OrderCompletionActService.source(session, CommandActor.from_auth(auth), data)
    except ManagedDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ManagedDocumentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("", response_model=ConnectorWriteResult[OrderCompletionActPrepared],
             operation_id=operation_ids.PREPARE_MANAGER_ORDER_COMPLETION_ACT)
async def prepare_order_completion_act(
    payload: PrepareOrderCompletionActPayload,
    order_id: int = Path(gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """Prepare a standard closing-act draft using selected sites, one proposal and its basis."""
    data = PrepareOrderCompletionActInput(order_id=order_id, **payload.model_dump())
    try:
        outcome = await OrderCompletionActService.prepare(
            session, CommandActor.from_auth(auth), data,
            template_storage=PrivateTemplateSourceStorage(_legacy_private_storage()),
        )
    except (LookupError, ManagedDocumentNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ManagedDocumentConflictError, PublicWriteIdempotencyConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (PublicWriteIdempotencyUnavailable, OSError) as exc:
        raise HTTPException(status_code=503, detail="Операция временно недоступна. Повторите с тем же ключом.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ConnectorWriteResult(result=outcome.value, replayed=outcome.replayed)
