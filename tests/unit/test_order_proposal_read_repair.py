"""Proposal IDs returned by a detail request must survive its session closing."""

from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select, text

from models import LeadSource, Order, OrderProposal, OrderStatus
from models.tenancy import TenantScope
from schemas import ManagerOrderUpdatePayload
from services.order_projection_service import OrderProjectionService
from services.order_update.command import OrderUpdateCommandService


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'read_repair.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed_order(sessions, proposal_state=None):
    async with sessions() as session:
        order = Order(
            tenant_id=1, storefront_id=1, status=OrderStatus.NEGOTIATION,
            lead_source=LeadSource.BELZAKUPKI,
        )
        session.add(order)
        await session.flush()
        if proposal_state:
            session.add(OrderProposal(
                order_id=order.id, is_selected=False,
                is_archived=proposal_state == "archived",
            ))
        await session.commit()
        return int(order.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("proposal_state", [None, "archived", "unselected"])
async def test_detail_proposal_survives_read_session_and_can_be_saved(sessions, proposal_state):
    order_id = await _seed_order(sessions, proposal_state)
    async with sessions() as read_session:
        detail = await OrderProjectionService.get_order_detail_for_manager(
            read_session, order_id, tenant_scope=SCOPE,
        )
        proposal_id = next(p["id"] for p in detail["proposals"] if p["is_selected"])

    async with sessions() as save_session:
        saved = await OrderUpdateCommandService.update_order_for_manager(
            save_session, order_id,
            ManagerOrderUpdatePayload(
                line_proposal_id=proposal_id,
                products=[],
                services=[{"title": "Монтаж", "quantity": 1, "price": 450}],
            ),
            tenant_scope=SCOPE,
        )
        assert any(
            p["id"] == proposal_id for p in saved["proposals"]
        )
        assert saved["service_lines"][0]["proposal_id"] == proposal_id
        assert saved["total_amount"] == 450

    async with sessions() as next_read:
        detail = await OrderProjectionService.get_order_detail_for_manager(
            next_read, order_id, tenant_scope=SCOPE,
        )
        assert next(p["id"] for p in detail["proposals"] if p["is_selected"]) == proposal_id
        active = list((await next_read.execute(select(OrderProposal).where(
            OrderProposal.order_id == order_id, OrderProposal.is_archived == False,
        ))).scalars())
        assert len(active) == 1


@pytest.mark.asyncio
async def test_demo_and_foreign_details_do_not_repair_proposals(sessions):
    order_id = await _seed_order(sessions)
    async with sessions() as session:
        demo = await OrderProjectionService.get_order_detail_for_manager(
            session, order_id, tenant_scope=replace(SCOPE, demo_read_only=True),
        )
        assert demo["proposals"] == []
        foreign = await OrderProjectionService.get_order_detail_for_manager(
            session, order_id, tenant_scope=replace(SCOPE, tenant_id=2, storefront_id=2),
        )
        assert foreign is None
        # Commit to catch even uncommitted writes in these read-only paths.
        await session.commit()
    async with sessions() as session:
        assert list((await session.execute(select(OrderProposal))).scalars()) == []


@pytest.mark.asyncio
async def test_detail_repair_respects_explicit_caller_transaction(sessions):
    order_id = await _seed_order(sessions)
    async with sessions() as session:
        await session.begin()
        # sqlite's legacy transaction mode does not begin on SELECT. Make the
        # physical caller transaction explicit before the repair's savepoint.
        await session.execute(text("BEGIN"))
        detail = await OrderProjectionService.get_order_detail_for_manager(
            session, order_id, tenant_scope=SCOPE,
        )
        assert len(detail["proposals"]) == 1
        await session.rollback()
    async with sessions() as session:
        assert list((await session.execute(select(OrderProposal))).scalars()) == []
