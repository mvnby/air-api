"""Read-only tenant-scoped MCP projections; never repair legacy CRM data."""

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload
from sqlmodel import select

from core.command_actor import CommandActor
from core.config import settings
from models import Customer, Order
from schemas_connector_mcp import (
    ConnectorContext,
    CustomerSearchResult,
    CustomerSummary,
    OrderSearchResult,
    OrderSummary,
)
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import tenant_scope_clause


def _enum_text(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _search_pattern(value: str) -> str:
    # Search text is literal: percent/underscore are not user-supplied wildcards.
    return "%" + value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class ConnectorQueryService:
    @staticmethod
    def context(actor: CommandActor) -> ConnectorContext:
        return ConnectorContext(
            staff_user_id=actor.staff_user_id,
            username=actor.username,
            tenant_id=actor.tenant_scope.tenant_id,
            storefront_id=actor.tenant_scope.storefront_id,
            timezone="Europe/Minsk",
            current_time=datetime.now(timezone.utc),
            manager_url=settings.MANAGER_BASE_URL.rstrip("/"),
        )

    @staticmethod
    def _customer(customer: Customer) -> CustomerSummary:
        return CustomerSummary(
            id=customer.id,
            name=customer.name,
            phone=customer.phone,
            email=customer.email,
            type=_enum_text(customer.type),
            city=customer.city,
            archived=customer.is_archived,
            link=f"{settings.MANAGER_BASE_URL.rstrip('/')}/customers/profile?customerId={customer.id}",
        )

    @staticmethod
    def _order(order: Order, customer_name: str | None) -> OrderSummary:
        return OrderSummary(
            id=order.id,
            title=order.title,
            status=_enum_text(order.status),
            customer_id=order.customer_id,
            customer_name=customer_name,
            delivery_address=order.delivery_address,
            total_amount=order.total_amount,
            balance_due=order.balance_due,
            link=f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/kanban?orderId={order.id}",
        )

    @classmethod
    async def search_customers(
        cls, session: AsyncSession, actor: CommandActor, *, query: str, limit: int = 10
    ) -> CustomerSearchResult:
        pattern = _search_pattern(query)
        statement = (
            select(Customer)
            .options(noload("*"))
            .where(
                tenant_scope_clause(Customer, actor.tenant_scope),
                or_(
                    Customer.name.ilike(pattern, escape="\\"),
                    Customer.phone.ilike(pattern, escape="\\"),
                    Customer.email.ilike(pattern, escape="\\"),
                    Customer.full_legal_name.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(Customer.id)
            .limit(limit + 1)
        )
        customers = (await session.execute(statement)).scalars().all()
        return CustomerSearchResult(
            items=[cls._customer(item) for item in customers[:limit]],
            ambiguous=len(customers) > 1,
            has_more=len(customers) > limit,
        )

    @classmethod
    async def get_customer(
        cls, session: AsyncSession, actor: CommandActor, *, customer_id: int
    ) -> CustomerSummary:
        customer = await TenantEntityAccessService.get_customer(
            session, customer_id, tenant_scope=actor.tenant_scope
        )
        if customer is None:
            raise HTTPException(404, "Customer not found")
        return cls._customer(customer)

    @classmethod
    def _orders_statement(cls, actor: CommandActor):
        # Select columns/entities directly. Manager order detail also creates a
        # default proposal on older orders, so it cannot serve a read-only tool.
        return (
            select(Order, Customer.name)
            .options(noload("*"))
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                TenantEntityAccessService.order_clause(actor.tenant_scope),
                TenantEntityAccessService.order_customer_clause(actor.tenant_scope),
            )
        )

    @classmethod
    async def search_orders(
        cls, session: AsyncSession, actor: CommandActor, *, query: str, limit: int = 10
    ) -> OrderSearchResult:
        pattern = _search_pattern(query)
        matches = [
            Order.title.ilike(pattern, escape="\\"),
            Order.delivery_address.ilike(pattern, escape="\\"),
            Customer.name.ilike(pattern, escape="\\"),
            Customer.phone.ilike(pattern, escape="\\"),
        ]
        if query.strip().lstrip("#").isdigit():
            matches.append(Order.id == int(query.strip().lstrip("#")))
        statement = cls._orders_statement(actor).where(or_(*matches)).order_by(Order.id.desc()).limit(limit + 1)
        orders = (await session.execute(statement)).all()
        return OrderSearchResult(
            items=[cls._order(order, name) for order, name in orders[:limit]],
            ambiguous=len(orders) > 1,
            has_more=len(orders) > limit,
        )

    @classmethod
    async def get_order(
        cls, session: AsyncSession, actor: CommandActor, *, order_id: int
    ) -> OrderSummary:
        row = (await session.execute(cls._orders_statement(actor).where(Order.id == order_id))).first()
        if row is None:
            raise HTTPException(404, "Order not found")
        return cls._order(row[0], row[1])
