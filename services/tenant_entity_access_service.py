"""Central tenant ownership checks for CRM root and child entities.

Manager-facing code must resolve ownership through this module before reading
or mutating an entity by an opaque database id.  Child objects inherit the
security boundary from their Order or Customer; they are never trusted on
their id alone.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Customer,
    CustomerEquipment,
    Lead,
    Order,
    OrderDocument,
    OrderWorkStage,
)
from models.tenancy import TenantScope
from services.tenant_scope_service import (
    storefront_scope_clause,
    tenant_scope_clause,
)


class TenantEntityAccessService:
    """Load tenant-owned CRM entities without leaking foreign existence."""

    @staticmethod
    def order_clause(tenant_scope: TenantScope):
        return storefront_scope_clause(Order, tenant_scope)

    @staticmethod
    def lead_clause(tenant_scope: TenantScope):
        return storefront_scope_clause(Lead, tenant_scope)

    @staticmethod
    def order_customer_clause(tenant_scope: TenantScope):
        return or_(
            Order.customer_id.is_(None),
            tenant_scope_clause(Customer, tenant_scope),
        )

    @staticmethod
    async def get_customer(
        session: AsyncSession,
        customer_id: int,
        *,
        tenant_scope: TenantScope,
        for_update: bool = False,
    ) -> Customer | None:
        statement = select(Customer).where(
            Customer.id == int(customer_id),
            tenant_scope_clause(Customer, tenant_scope),
        )
        if for_update:
            statement = statement.with_for_update(of=Customer)
        return (await session.execute(statement)).scalars().first()

    @classmethod
    async def get_order(
        cls,
        session: AsyncSession,
        order_id: int,
        *,
        tenant_scope: TenantScope,
        options: Iterable[Any] = (),
        for_update: bool = False,
        populate_existing: bool = False,
    ) -> Order | None:
        statement = (
            select(Order)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                Order.id == int(order_id),
                cls.order_clause(tenant_scope),
                cls.order_customer_clause(tenant_scope),
            )
        )
        for option in options:
            statement = statement.options(option)
        if populate_existing:
            statement = statement.execution_options(populate_existing=True)
        if for_update:
            statement = statement.with_for_update(of=Order)
        return (await session.execute(statement)).scalars().first()

    @classmethod
    async def get_lead(
        cls,
        session: AsyncSession,
        lead_id: int,
        *,
        tenant_scope: TenantScope,
        for_update: bool = False,
    ) -> Lead | None:
        statement = select(Lead).where(
            Lead.id == int(lead_id),
            cls.lead_clause(tenant_scope),
        )
        if for_update:
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalars().first()

    @classmethod
    async def get_order_stage(
        cls,
        session: AsyncSession,
        stage_id: int,
        *,
        tenant_scope: TenantScope,
        order_id: int | None = None,
        options: Iterable[Any] = (),
        for_update: bool = False,
    ) -> OrderWorkStage | None:
        statement = (
            select(OrderWorkStage)
            .join(Order, Order.id == OrderWorkStage.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                OrderWorkStage.id == int(stage_id),
                cls.order_clause(tenant_scope),
                cls.order_customer_clause(tenant_scope),
            )
        )
        if order_id is not None:
            statement = statement.where(OrderWorkStage.order_id == int(order_id))
        for option in options:
            statement = statement.options(option)
        if for_update:
            statement = statement.with_for_update(of=(OrderWorkStage, Order))
        return (await session.execute(statement)).scalars().first()

    @staticmethod
    async def get_equipment(
        session: AsyncSession,
        equipment_id: int,
        *,
        tenant_scope: TenantScope,
        options: Iterable[Any] = (),
        for_update: bool = False,
    ) -> CustomerEquipment | None:
        statement = (
            select(CustomerEquipment)
            .join(Customer, Customer.id == CustomerEquipment.customer_id)
            .where(
                CustomerEquipment.id == int(equipment_id),
                tenant_scope_clause(Customer, tenant_scope),
            )
        )
        for option in options:
            statement = statement.options(option)
        if for_update:
            statement = statement.with_for_update(
                of=(CustomerEquipment, Customer)
            )
        return (await session.execute(statement)).scalars().first()

    @classmethod
    async def get_order_document(
        cls,
        session: AsyncSession,
        document_id: int,
        *,
        tenant_scope: TenantScope,
        for_update: bool = False,
    ) -> OrderDocument | None:
        statement = (
            select(OrderDocument)
            .join(Order, Order.id == OrderDocument.order_id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                OrderDocument.id == int(document_id),
                cls.order_clause(tenant_scope),
                cls.order_customer_clause(tenant_scope),
            )
        )
        if for_update:
            statement = statement.with_for_update(of=(OrderDocument, Order))
        return (await session.execute(statement)).scalars().first()
