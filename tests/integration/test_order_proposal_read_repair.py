import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import LeadSource, Order, OrderProposal, OrderStatus
from services.order_projection_service import OrderProjectionService


@pytest.mark.asyncio
async def test_concurrent_legacy_details_return_one_durable_proposal(db_engine, tenant_scope):
    sessions = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as session:
        order = Order(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            status=OrderStatus.NEGOTIATION,
            lead_source=LeadSource.BELZAKUPKI,
        )
        session.add(order)
        await session.commit()
        order_id = int(order.id)

    async def read_detail():
        async with sessions() as session:
            detail = await OrderProjectionService.get_order_detail_for_manager(
                session, order_id, tenant_scope=tenant_scope,
            )
            return next(p["id"] for p in detail["proposals"] if p["is_selected"])

    first_id, second_id = await asyncio.gather(read_detail(), read_detail())
    assert first_id == second_id
    async with sessions() as session:
        proposals = list((await session.execute(select(OrderProposal).where(
            OrderProposal.order_id == order_id,
        ))).scalars())
        assert len(proposals) == 1
        assert proposals[0].id == first_id
        assert proposals[0].is_selected
