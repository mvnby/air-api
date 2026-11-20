"""Versioned order-site commands shared by Manager, MCP and document workflows."""

from collections import defaultdict
from collections.abc import Sequence

from fastapi import HTTPException
from pydantic import BaseModel

from core.command_actor import CommandActor
from core.config import settings
from crud.order_sites import OrderSiteDAO
from models import CustomerEquipment, EquipmentComponent, OrderStatus
from models.order_site import OrderSite, OrderSiteEquipment
from schemas_order_sites import (
    OrderSiteAddPayload,
    OrderSiteEquipmentItem,
    OrderSiteEquipmentLinkPayload,
    OrderSiteEquipmentLinkResult,
    OrderSiteEquipmentList,
    OrderSiteItem,
    OrderSiteLegacyPrimary,
    OrderSiteList,
    OrderSiteNewEquipment,
)
from services.authenticated_command_service import AuthenticatedCommandService
from services.equipment_service import EquipmentService
from services.public_write_idempotency_service import PublicWriteCommandOutcome, PublicWriteCommandResponse
from services.tenant_entity_access_service import TenantEntityAccessService


class OrderSiteVersionConflict(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=409,
            detail={"code": "version_conflict", "message": "Состав объекта изменился. Обновите данные."},
        )


class _EquipmentLinkReceipt(BaseModel):
    site: OrderSiteItem
    equipment_id: int


class OrderSiteService:
    @staticmethod
    async def _order(session, tenant_scope, order_id, *, lock=False):
        order = await TenantEntityAccessService.get_order(
            session, order_id, tenant_scope=tenant_scope,
            for_update=lock, populate_existing=lock,
        )
        if order is None:
            raise LookupError("Заказ не найден")
        return order

    @staticmethod
    async def _site(session, order, site_id, *, lock=False):
        site = await OrderSiteDAO.get_site(session, order, site_id, lock=lock)
        if site is None:
            raise LookupError("Объект заказа не найден")
        return site

    @staticmethod
    def _require_writable(order):
        if order.status == OrderStatus.CLOSED:
            raise HTTPException(status_code=409, detail="Закрытый заказ нельзя изменить")
        if order.customer_id is None:
            raise ValueError("Сначала укажите клиента заказа")

    @staticmethod
    def _site_item(site):
        url = (
            f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/{site.order_id}"
            f"?section=work&orderSiteId={site.id}#order-workspace-sites"
        )
        return OrderSiteItem(
            id=site.id, order_id=site.order_id, customer_branch_id=site.customer_branch_id,
            title=site.title, address=site.address, version=site.version, manager_url=url,
        )

    @staticmethod
    async def _legacy_primary(session, order):
        branch = None
        if order.customer_branch_id is not None:
            branch = await OrderSiteDAO.customer_branch(session, order.customer_id, order.customer_branch_id)
        address = (order.delivery_address or "").strip() or ((branch.delivery_address or "").strip() if branch else "")
        if not address:
            return None
        title = ((branch.name or "").strip() if branch else "") or "Основной объект"
        if branch is not None:
            site = await OrderSiteDAO.by_customer_branch(session, order, branch.id)
        else:
            site = await OrderSiteDAO.find_order_only_site(session, order, title=title, address=address)
        if site is not None:
            return None
        return OrderSiteLegacyPrimary(
            customer_branch_id=branch.id if branch else None, title=title, address=address,
        )

    @classmethod
    async def list_sites(cls, session, actor: CommandActor, order_id: int, *, limit=100, offset=0):
        order = await cls._order(session, actor.tenant_scope, order_id)
        rows, total = await OrderSiteDAO.list_sites(session, order, limit=limit, offset=offset)
        return OrderSiteList(
            items=[cls._site_item(site) for site in rows], total=total, limit=limit, offset=offset,
            legacy_primary=await cls._legacy_primary(session, order),
        )

    @classmethod
    async def add_site(
        cls, session, actor: CommandActor, order_id: int, payload: OrderSiteAddPayload, *, idempotency_key: str,
    ):
        await cls._order(session, actor.tenant_scope, order_id)

        async def operation():
            order = await cls._order(session, actor.tenant_scope, order_id, lock=True)
            cls._require_writable(order)
            branch_id = payload.customer_branch_id
            title, address = payload.title, payload.address
            if branch_id is not None:
                branch = await OrderSiteDAO.customer_branch(session, order.customer_id, branch_id, lock=True)
                if branch is None:
                    raise LookupError("Филиал клиента не найден")
                title = title or ((branch.name or "").strip() or "Объект клиента")
                order_address = (order.delivery_address or "").strip() if branch.id == order.customer_branch_id else ""
                address = address or order_address or (branch.delivery_address or "").strip()
                site = await OrderSiteDAO.by_customer_branch(session, order, branch.id)
            else:
                site = await OrderSiteDAO.find_order_only_site(session, order, title=title, address=address)
            if not address:
                raise ValueError("У объекта должен быть адрес")
            if branch_id is not None and site is not None and (
                (payload.title is not None and site.title != payload.title)
                or (payload.address is not None and site.address.casefold() != payload.address.casefold())
            ):
                raise HTTPException(status_code=409, detail="Объект уже добавлен с другими реквизитами")
            if site is None:
                site = OrderSite(
                    order_id=order.id, customer_id=order.customer_id, customer_branch_id=branch_id,
                    title=title, address=address,
                )
                session.add(site)
                await session.flush()
            return PublicWriteCommandResponse(cls._site_item(site), resource_type="order_site", resource_id=site.id)

        outcome = await AuthenticatedCommandService.execute(
            session, actor=actor, command_name="order_site.add", idempotency_key=idempotency_key,
            payload={"order_id": order_id, "site": payload.model_dump(mode="json")}, response_model=OrderSiteItem,
            operation=operation,
        )
        if outcome.replayed:
            order = await cls._order(session, actor.tenant_scope, order_id)
            await cls._site(session, order, outcome.value.id)
        return outcome

    @staticmethod
    async def _equipment_items(session, tenant_scope, rows):
        if not rows:
            return []
        equipment_ids = [equipment.id for _, equipment in rows]
        components = defaultdict(list)
        for component in await OrderSiteDAO.equipment_components(session, equipment_ids):
            components[component.equipment_id].append(
                EquipmentService._to_component_item(component, tenant_scope=tenant_scope)
            )
        return [
            OrderSiteEquipmentItem(
                equipment_id=equipment.id, site_id=link.site_id, role=link.role,
                equipment={**EquipmentService._to_equipment_item(equipment), "components": components[equipment.id]},
            )
            for link, equipment in rows
        ]

    @classmethod
    async def list_site_equipment(
        cls, session, actor: CommandActor, order_id: int, site_id: int, *, limit=100, offset=0,
    ):
        order = await cls._order(session, actor.tenant_scope, order_id)
        site = await cls._site(session, order, site_id)
        rows, total = await OrderSiteDAO.equipment_for_site(session, site, limit=limit, offset=offset)
        items = await cls._equipment_items(session, actor.tenant_scope, rows)
        return OrderSiteEquipmentList(items=items, total=total, limit=limit, offset=offset)

    @classmethod
    async def resolve_scope(
        cls, session, tenant_scope, order_id: int, site_id: int, equipment_ids: Sequence[int], *, lock=False,
    ) -> tuple[OrderSiteItem, list[OrderSiteEquipmentItem]]:
        """Resolve only equipment assigned to this site, for immutable document snapshots."""
        order = await cls._order(session, tenant_scope, order_id, lock=lock)
        site = await cls._site(session, order, site_id, lock=lock)
        ids = set(equipment_ids)
        if len(ids) != len(equipment_ids):
            raise ValueError("Оборудование указано несколько раз")
        if not ids:
            return cls._site_item(site), []
        rows, _ = await OrderSiteDAO.equipment_for_site(session, site, equipment_ids=equipment_ids, lock=lock)
        if len(rows) != len(ids):
            raise ValueError("Не всё выбранное оборудование относится к этому объекту заказа")
        items = await cls._equipment_items(session, tenant_scope, rows)
        by_id = {item.equipment_id: item for item in items}
        return cls._site_item(site), [by_id[equipment_id] for equipment_id in equipment_ids]

    @staticmethod
    async def _create_equipment(session, site, payload: OrderSiteNewEquipment):
        source = payload.model_dump(exclude={"components", "installed_at"})
        data = {field: EquipmentService._clean_optional_text(value) for field, value in source.items()}
        data["equipment_type"] = data["equipment_type"] or "hvac"
        data["display_name"] = EquipmentService._default_display_name(data)
        equipment = CustomerEquipment(
            customer_id=site.customer_id, customer_branch_id=site.customer_branch_id,
            equipment_source="customer_owned", installed_at=EquipmentService._normalize_naive_datetime(payload.installed_at),
            **data,
        )
        session.add(equipment)
        await session.flush()
        session.add_all([
            EquipmentComponent(
                equipment_id=equipment.id,
                **EquipmentService._component_values_from_payload(component.model_dump()),
            )
            for component in payload.components
        ])
        return equipment

    @classmethod
    async def link_equipment(
        cls, session, actor: CommandActor, order_id: int, site_id: int,
        payload: OrderSiteEquipmentLinkPayload, *, idempotency_key: str,
    ):
        order = await cls._order(session, actor.tenant_scope, order_id)
        await cls._site(session, order, site_id)

        async def operation():
            order = await cls._order(session, actor.tenant_scope, order_id, lock=True)
            cls._require_writable(order)
            site = await cls._site(session, order, site_id, lock=True)
            if site.version != payload.expected_version:
                raise OrderSiteVersionConflict()
            if payload.equipment_id is not None:
                equipment = await cls._existing_equipment(session, actor, order, payload.equipment_id, lock=True)
            else:
                equipment = await cls._create_equipment(session, site, payload.equipment)
            if equipment.customer_branch_id not in {None, site.customer_branch_id}:
                raise ValueError("Оборудование относится к другому филиалу клиента")
            link = await OrderSiteDAO.for_order_equipment(session, order.id, equipment.id)
            if link is not None and (link.site_id != site.id or link.role != payload.role):
                raise HTTPException(status_code=409, detail="Оборудование уже связано с другим объектом или ролью")
            if link is None:
                link = OrderSiteEquipment(order_id=order.id, site_id=site.id, equipment_id=equipment.id, role=payload.role)
                session.add(link)
                site.version += 1
            await EquipmentService._ensure_equipment_order_link(
                session, equipment_id=equipment.id, order_id=order.id, role=payload.role,
            )
            await session.flush()
            receipt = _EquipmentLinkReceipt(site=cls._site_item(site), equipment_id=equipment.id)
            return PublicWriteCommandResponse(receipt, resource_type="order_site_equipment", resource_id=link.id)

        outcome = await AuthenticatedCommandService.execute(
            session, actor=actor, command_name="order_site.equipment.link", idempotency_key=idempotency_key,
            payload={"order_id": order_id, "site_id": site_id, "link": payload.model_dump(mode="json")},
            response_model=_EquipmentLinkReceipt, operation=operation,
        )
        # Resolve the passport through the current scoped association. Durable
        # retry receipts stay small even for complex physical systems.
        _, items = await cls.resolve_scope(
            session, actor.tenant_scope, order_id, site_id, [outcome.value.equipment_id],
        )
        result = OrderSiteEquipmentLinkResult(site=outcome.value.site, equipment=items[0])
        return PublicWriteCommandOutcome(value=result, status_code=outcome.status_code, replayed=outcome.replayed)

    @staticmethod
    async def _existing_equipment(session, actor, order, equipment_id, *, lock=False):
        equipment = await TenantEntityAccessService.get_equipment(
            session, equipment_id, tenant_scope=actor.tenant_scope, for_update=lock,
        )
        if equipment is None:
            raise LookupError("Оборудование не найдено")
        if lock:
            await session.refresh(equipment)
        if equipment.customer_id != order.customer_id:
            raise ValueError("Оборудование относится к другому клиенту")
        if equipment.is_archived:
            raise ValueError("Архивное оборудование нельзя привязать")
        return equipment
