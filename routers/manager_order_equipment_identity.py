"""Physical order equipment, with the same version/retry rules as MCP."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from routers.manager_operation_ids import GET_MANAGER_ORDER_EQUIPMENT_IDENTITIES, SAVE_MANAGER_ORDER_EQUIPMENT_IDENTITY
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_connector_mcp import ConnectorWriteResult
from schemas_order_equipment_identity import OrderEquipmentSaveInput, OrderEquipmentSavePayload, OrderEquipmentSaveResult, OrderEquipmentState
from services.order_equipment_identity_service import OrderEquipmentIdentityService
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict, PublicWriteIdempotencyUnavailable


router = APIRouter(prefix="/api/manager/orders/{order_id}/equipment-identities", tags=["manager-order-equipment"],
                   route_class=ManagerPermissionRoute, dependencies=[Depends(require_manager_access)])


@router.get("", response_model=OrderEquipmentState, operation_id=GET_MANAGER_ORDER_EQUIPMENT_IDENTITIES)
async def get_manager_order_equipment_identities(order_id: int,
    equipment_id: int | None = Query(None, gt=0), limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access)):
    """Read saved physical units and their version in the accessible order.

    An optional existing candidate must belong to the same customer/object. This
    never creates a unit or refreshes a document snapshot. Inaccessible records
    return 404; an incompatible customer/object returns 400. Manager membership
    and tenant/storefront isolation apply to the order and equipment.
    """
    try:
        return await OrderEquipmentIdentityService.read(session, CommandActor.from_auth(auth), order_id,
            equipment_id=equipment_id, limit=limit, offset=offset)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", response_model=ConnectorWriteResult[OrderEquipmentSaveResult], operation_id=SAVE_MANAGER_ORDER_EQUIPMENT_IDENTITY)
async def save_manager_order_equipment_identity(order_id: int, payload: OrderEquipmentSavePayload,
    session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_manager_access)):
    """Save a confirmed physical unit or associate an existing unit with this order.

    Reuse the exact idempotency key and payload after a timeout. The order version
    prevents stale saves; editing an existing identity also requires its own
    version. Omitted identity fields survive. A source document supplies saved
    snapshot facts and is never rewritten; repeated adoption reuses its unit.
    Missing records return 404, stale versions or changed key payloads 409,
    invalid fields/relationships 400 and temporary receipt contention 503.
    Requires an active Manager staff membership in the scoped tenant/storefront.
    """
    try:
        data = OrderEquipmentSaveInput(order_id=order_id, **payload.model_dump(exclude_unset=True))
        outcome = await OrderEquipmentIdentityService.save(session, CommandActor.from_auth(auth), data)
        return {"result": outcome.value, "replayed": outcome.replayed}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PublicWriteIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail="This key was already used with another payload") from exc
    except PublicWriteIdempotencyUnavailable as exc:
        raise HTTPException(status_code=503, detail="Retry with the same key and payload") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
