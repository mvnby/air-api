"""Read-only B2C document defaults for a scoped order proposal."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.application.consumer_equipment import (
    ConsumerEquipmentDefaultsError,
    resolve_consumer_equipment_defaults_for_order,
)
from routers.manager_operation_ids import GET_MANAGER_CONSUMER_EQUIPMENT_DEFAULTS
from routers.manager_permission_policy import ManagerPermissionRoute


class ConsumerEquipmentDefaultsResponse(BaseModel):
    equipment_brand: str | None = None
    equipment_model: str | None = None
    equipment_serial: str | None = None
    goods_warranty_months: int
    goods_warranty_terms: str | None = None


router = APIRouter(
    prefix="/api/manager/document-system",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/orders/{order_id}/consumer-defaults",
    response_model=ConsumerEquipmentDefaultsResponse,
    operation_id=GET_MANAGER_CONSUMER_EQUIPMENT_DEFAULTS,
)
async def get_manager_consumer_equipment_defaults(
    order_id: int,
    proposal_id: int | None = Query(default=None, gt=0),
    issue_date: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ConsumerEquipmentDefaultsResponse:
    try:
        terms = await resolve_consumer_equipment_defaults_for_order(
            session,
            tenant_scope=auth.tenant_scope(),
            order_id=order_id,
            proposal_id=proposal_id,
            issue_date=issue_date,
        )
    except ConsumerEquipmentDefaultsError as exc:
        status_code = 404 if str(exc) == "Заказ не найден" else 400
        raise manager_http_error(
            status_code=status_code,
            endpoint=GET_MANAGER_CONSUMER_EQUIPMENT_DEFAULTS,
            error_code=(
                "order_not_found"
                if status_code == 404
                else "consumer_defaults_proposal_not_found"
            ),
            message=str(exc),
        ) from exc
    return ConsumerEquipmentDefaultsResponse(
        equipment_brand=terms.equipment_brand,
        equipment_model=terms.equipment_model,
        equipment_serial=terms.equipment_serial,
        goods_warranty_months=terms.goods_warranty_months or 36,
        goods_warranty_terms=terms.goods_warranty_terms,
    )
