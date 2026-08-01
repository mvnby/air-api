"""Persistence helpers for supply-request source ownership checks."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models.order import Order, OrderProductLink
from models.tenancy import TenantScope
from services.tenant_scope_service import storefront_scope_clause


class SupplyRequestDAO:
    @staticmethod
    async def get_order_product_links_for_storefront(
        session: AsyncSession,
        *,
        order_product_link_ids: Iterable[int],
        tenant_scope: TenantScope,
    ) -> list[OrderProductLink]:
        normalized_ids = tuple(
            dict.fromkeys(int(value) for value in order_product_link_ids)
        )
        if not normalized_ids:
            return []

        statement = (
            select(OrderProductLink)
            .join(Order, Order.id == OrderProductLink.order_id)
            .where(
                OrderProductLink.id.in_(normalized_ids),
                storefront_scope_clause(Order, tenant_scope),
            )
            .options(selectinload(OrderProductLink.product))
            .order_by(OrderProductLink.id.asc())
        )
        result = await session.execute(statement)
        return list(result.scalars().all())
