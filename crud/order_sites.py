"""Persistence for the order's site snapshots and physical equipment links."""

from collections.abc import Sequence

from sqlalchemy import func
from sqlmodel import select

from models import CustomerBranch, CustomerEquipment, EquipmentComponent
from models.order_site import OrderSite, OrderSiteEquipment


class OrderSiteDAO:
    @staticmethod
    async def list_sites(session, order, *, limit, offset):
        filters = (
            OrderSite.order_id == order.id,
            OrderSite.customer_id == order.customer_id,
        )
        total = await session.scalar(select(func.count()).select_from(OrderSite).where(*filters))
        rows = await session.scalars(
            select(OrderSite).where(*filters).order_by(OrderSite.id).limit(limit).offset(offset)
        )
        return list(rows), total

    @staticmethod
    async def get_site(session, order, site_id, *, lock=False):
        query = select(OrderSite).where(
            OrderSite.order_id == order.id,
            OrderSite.customer_id == order.customer_id,
            OrderSite.id == site_id,
        )
        if lock:
            query = query.with_for_update(of=OrderSite).execution_options(populate_existing=True)
        return await session.scalar(query)

    @staticmethod
    async def customer_branch(session, customer_id, branch_id, *, lock=False):
        query = select(CustomerBranch).where(
            CustomerBranch.customer_id == customer_id,
            CustomerBranch.id == branch_id,
        )
        if lock:
            query = query.with_for_update(of=CustomerBranch, key_share=True).execution_options(populate_existing=True)
        return await session.scalar(query)

    @staticmethod
    async def by_customer_branch(session, order, branch_id):
        return await session.scalar(
            select(OrderSite).where(
                OrderSite.order_id == order.id,
                OrderSite.customer_id == order.customer_id,
                OrderSite.customer_branch_id == branch_id,
            )
        )

    @staticmethod
    async def find_order_only_site(session, order, *, title, address, exclude_site_id=None):
        query = select(OrderSite).where(
            OrderSite.order_id == order.id,
            OrderSite.customer_id == order.customer_id,
            OrderSite.customer_branch_id.is_(None),
            func.lower(OrderSite.title) == func.lower(title),
            func.lower(OrderSite.address) == func.lower(address),
        )
        if exclude_site_id is not None:
            query = query.where(OrderSite.id != exclude_site_id)
        return await session.scalar(query)

    @staticmethod
    async def for_order_equipment(session, order_id, equipment_id):
        return await session.scalar(
            select(OrderSiteEquipment).where(
                OrderSiteEquipment.order_id == order_id,
                OrderSiteEquipment.equipment_id == equipment_id,
            )
        )

    @staticmethod
    async def equipment_for_site(
        session, site, *, equipment_ids: Sequence[int] | None = None,
        limit: int | None = None, offset=0, lock=False,
    ):
        query = (
            select(OrderSiteEquipment, CustomerEquipment)
            .join(CustomerEquipment, CustomerEquipment.id == OrderSiteEquipment.equipment_id)
            .where(
                OrderSiteEquipment.order_id == site.order_id,
                OrderSiteEquipment.site_id == site.id,
                CustomerEquipment.customer_id == site.customer_id,
            )
        )
        if equipment_ids is not None:
            query = query.where(OrderSiteEquipment.equipment_id.in_(equipment_ids))
        if lock:
            query = query.with_for_update(of=CustomerEquipment).execution_options(populate_existing=True)
        total = None
        if limit is not None:
            total = await session.scalar(select(func.count()).select_from(query.subquery()))
            query = query.limit(limit).offset(offset)
        rows = (await session.execute(query.order_by(OrderSiteEquipment.equipment_id))).all()
        return list(rows), total

    @staticmethod
    async def equipment_components(session, equipment_ids):
        query = (
            select(EquipmentComponent)
            .where(
                EquipmentComponent.equipment_id.in_(equipment_ids),
                EquipmentComponent.is_archived.is_(False),
            )
            .order_by(EquipmentComponent.equipment_id, EquipmentComponent.component_type, EquipmentComponent.id)
        )
        return list((await session.scalars(query)).all())
