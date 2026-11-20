"""Versioned equipment inspections that do not create commercial work or service events."""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from crud import order_inspection
from models import OrderStatus
from models.tenancy import TenantScope
from schemas_order_diagnostics import (
    OrderInspectionFacts,
    OrderInspectionReadInput,
    OrderInspectionRevisionItem,
    OrderInspectionSaved,
    OrderInspectionSaveInput,
    OrderInspectionState,
)
from services.authenticated_command_service import AuthenticatedCommandService
from services.public_write_idempotency_service import PublicWriteCommandResponse
from services.tenant_entity_access_service import TenantEntityAccessService

if TYPE_CHECKING:
    from schemas_order_sites import OrderSiteEquipmentItem, OrderSiteItem


class OrderInspectionConflict(ValueError):
    pass


async def resolve_inspection_scope(
    session: AsyncSession, scope: TenantScope, order_id: int, site_id: int,
    equipment_ids: Sequence[int], *, write: bool = False,
) -> tuple["OrderSiteItem", list["OrderSiteEquipmentItem"]]:
    from services.order_site_service import OrderSiteService

    site, equipment = await OrderSiteService.resolve_scope(
        session, scope, order_id, site_id, list(equipment_ids), lock=write,
    )
    if write:
        order = await TenantEntityAccessService.get_order(session, order_id, tenant_scope=scope, populate_existing=True)
        if order is None:
            raise LookupError("Заказ не найден")
        if order.status == OrderStatus.CLOSED:
            raise OrderInspectionConflict("Заказ завершён: осмотры доступны только для просмотра")
        if any(item.equipment.is_archived for item in equipment):
            raise OrderInspectionConflict("Оборудование в архиве: сохранённые осмотры доступны только для просмотра")
        if order.workflow_type not in {"service_work", "repair"}:
            raise ValueError("Осмотр оборудования доступен в заказе на сервисные работы или ремонт")
    return site, equipment


def inspection_item(row) -> OrderInspectionRevisionItem:
    return OrderInspectionRevisionItem(
        revision_id=row.id, version=row.version, recorded_at=row.recorded_at, recorded_by=row.recorded_by, **row.facts,
    )


class OrderInspectionService:
    @staticmethod
    async def read(
        session: AsyncSession, actor: CommandActor, data: OrderInspectionReadInput,
    ) -> OrderInspectionState:
        target = dict(order_id=data.order_id, site_id=data.site_id, equipment_id=data.equipment_id)
        await resolve_inspection_scope(
            session, actor.tenant_scope, data.order_id, data.site_id, [data.equipment_id],
        )
        latest = (await order_inspection.latest_inspections(
            session, order_id=data.order_id, site_id=data.site_id, equipment_ids=[data.equipment_id],
        )).get(data.equipment_id)
        current_version = latest.version if latest is not None else 0
        row = latest
        if data.version is not None and data.version != current_version:
            row = await order_inspection.get_inspection(session, version=data.version, **target)
            if row is None:
                raise LookupError("Версия осмотра не найдена")
        return OrderInspectionState(
            **target, current_version=current_version, inspection=inspection_item(row) if row is not None else None,
        )

    @staticmethod
    async def save(session: AsyncSession, actor: CommandActor, data: OrderInspectionSaveInput):
        target = dict(order_id=data.order_id, site_id=data.site_id, equipment_id=data.equipment_id)
        await resolve_inspection_scope(
            session, actor.tenant_scope, data.order_id, data.site_id, [data.equipment_id],
        )

        async def save_revision() -> PublicWriteCommandResponse[OrderInspectionSaved]:
            await resolve_inspection_scope(
                session, actor.tenant_scope, data.order_id, data.site_id, [data.equipment_id], write=True,
            )
            previous = (await order_inspection.latest_inspections(
                session, order_id=data.order_id, site_id=data.site_id, equipment_ids=[data.equipment_id],
            )).get(data.equipment_id)
            current_version = previous.version if previous is not None else 0
            if current_version != data.expected_version:
                raise OrderInspectionConflict("Осмотр уже изменён. Перечитайте его актуальную версию.")
            row = await order_inspection.append_inspection(
                session, **target, version=current_version + 1,
                staff_user_id=actor.staff_user_id, username=actor.username,
                facts=data.model_dump(mode="json", include=set(OrderInspectionFacts.model_fields)),
            )
            result = OrderInspectionSaved(**target, revision_id=row.id, version=row.version)
            return PublicWriteCommandResponse(result, resource_type="order_inspection_revision", resource_id=row.id)

        return await AuthenticatedCommandService.execute(
            session, actor=actor, command_name="order_inspection.save", idempotency_key=data.idempotency_key,
            payload=data.model_dump(mode="json", exclude={"idempotency_key"}),
            response_model=OrderInspectionSaved, operation=save_revision,
        )
