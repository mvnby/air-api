from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from routers.manager_operation_ids import (
    CREATE_MANAGER_ORDER_EQUIPMENT_LINK,
    DELETE_MANAGER_ORDER_EQUIPMENT_LINK,
    LIST_MANAGER_ORDER_EQUIPMENT_LINKS,
)
from schemas import (
    ManagerOrderEquipmentLinkCreatePayload,
    ManagerOrderEquipmentLinkItemResponse,
    ManagerOrderEquipmentLinkListResponse,
)
from services.equipment_link_service import EquipmentLinkService
from services.tenant_scope_service import TenantScope


router = APIRouter(prefix="/api/manager/orders/{order_id}/equipment-links", tags=["manager-equipment-links"])


@router.get("", response_model=ManagerOrderEquipmentLinkListResponse, operation_id=LIST_MANAGER_ORDER_EQUIPMENT_LINKS)
async def list_manager_order_equipment_links(
    order_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read equipment associated with a scoped order, including legacy source-order
    associations without duplicate equipment entries. Missing or inaccessible order returns
    404. This does not create missing explicit links.

    Access and scope: Manager access is required; the order and its children are restricted
    to the authenticated tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    data = await EquipmentLinkService.list_for_order(
        session,
        order_id=order_id,
        tenant_scope=tenant_scope,
    )
    if data is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return data


@router.post(
    "",
    response_model=ManagerOrderEquipmentLinkItemResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_ORDER_EQUIPMENT_LINK,
)
async def create_manager_order_equipment_link(
    order_id: int,
    payload: ManagerOrderEquipmentLinkCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Associate existing customer equipment with an order after checking customer/branch
    compatibility and link role. Missing order/equipment returns 404 and incompatible
    relationships or role returns 400. An existing order/equipment pair is reused and its
    role may be updated; this does not create an equipment unit.

    Access and scope: Manager access is required; the order and its children are restricted
    to the authenticated tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        data = await EquipmentLinkService.link_existing(
            session,
            order_id=order_id,
            equipment_id=payload.equipment_id,
            role=payload.role,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if data is None:
        raise HTTPException(status_code=404, detail="Order or equipment not found")
    return data


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id=DELETE_MANAGER_ORDER_EQUIPMENT_LINK)
async def delete_manager_order_equipment_link(
    order_id: int,
    link_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Delete one equipment/order association and return 204, clearing matching legacy
    source_order_id when necessary. Equipment, warranty snapshots and service history are
    retained. Missing/inaccessible order/link/equipment returns 404, including after prior
    deletion.

    Access and scope: Manager access is required; the order and its children are restricted
    to the authenticated tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    if not await EquipmentLinkService.unlink(
        session,
        order_id=order_id,
        link_id=link_id,
        tenant_scope=tenant_scope,
    ):
        raise HTTPException(status_code=404, detail="Equipment link not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
