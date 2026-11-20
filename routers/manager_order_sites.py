"""Manager access to order locations and assigned physical equipment."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from routers.manager_operation_ids import (
    MANAGER_ADD_ORDER_SITE,
    MANAGER_LINK_ORDER_SITE_EQUIPMENT,
    MANAGER_LIST_ORDER_SITE_EQUIPMENT,
    MANAGER_LIST_ORDER_SITES,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_connector_mcp import ConnectorWriteResult
from schemas_order_sites import (
    OrderSiteAddRequest,
    OrderSiteEquipmentLinkRequest,
    OrderSiteEquipmentLinkResult,
    OrderSiteEquipmentList,
    OrderSiteItem,
    OrderSiteList,
)
from services.order_site_service import OrderSiteService
from services.public_write_idempotency_service import (
    PublicWriteIdempotencyConflict,
    PublicWriteIdempotencyUnavailable,
)


router = APIRouter(
    prefix="/api/manager/orders/{order_id}/sites",
    tags=["manager-order-sites"],
    route_class=ManagerPermissionRoute,
    dependencies=[Depends(require_manager_access)],
)


async def _call(operation):
    try:
        return await operation
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PublicWriteIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PublicWriteIdempotencyUnavailable as exc:
        raise HTTPException(status_code=503, detail="Повторите с тем же ключом и данными") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=OrderSiteList, operation_id=MANAGER_LIST_ORDER_SITES)
async def manager_list_order_sites(
    order_id: int = Path(gt=0),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """List saved sites and the legacy primary address of an accessible order."""
    return await _call(OrderSiteService.list_sites(
        session, CommandActor.from_auth(auth), order_id, limit=limit, offset=offset,
    ))


@router.post("", response_model=ConnectorWriteResult[OrderSiteItem], operation_id=MANAGER_ADD_ORDER_SITE)
async def manager_add_order_site(
    request: OrderSiteAddRequest,
    order_id: int = Path(gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """Add a site from the order customer's branch or from an order-specific address."""
    outcome = await _call(OrderSiteService.add_site(
        session, CommandActor.from_auth(auth), order_id, request.payload,
        idempotency_key=request.idempotency_key,
    ))
    return {"result": outcome.value, "replayed": outcome.replayed}


@router.get("/{site_id}/equipment", response_model=OrderSiteEquipmentList, operation_id=MANAGER_LIST_ORDER_SITE_EQUIPMENT)
async def manager_list_order_site_equipment(
    order_id: int = Path(gt=0),
    site_id: int = Path(gt=0),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """List equipment explicitly assigned to the site's order and its active components."""
    return await _call(OrderSiteService.list_site_equipment(
        session, CommandActor.from_auth(auth), order_id, site_id, limit=limit, offset=offset,
    ))


@router.post(
    "/{site_id}/equipment",
    response_model=ConnectorWriteResult[OrderSiteEquipmentLinkResult],
    operation_id=MANAGER_LINK_ORDER_SITE_EQUIPMENT,
)
async def manager_link_order_site_equipment(
    request: OrderSiteEquipmentLinkRequest,
    order_id: int = Path(gt=0),
    site_id: int = Path(gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """Link an existing unit or create it atomically with its site assignment and components."""
    outcome = await _call(OrderSiteService.link_equipment(
        session, CommandActor.from_auth(auth), order_id, site_id, request.payload,
        idempotency_key=request.idempotency_key,
    ))
    return {"result": outcome.value, "replayed": outcome.replayed}
