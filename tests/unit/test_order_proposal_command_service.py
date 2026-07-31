from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Customer, Order, OrderProposal, OrderStatus
from models.tenancy import TenantScope
from schemas import OrderProposalCreatePayload, OrderProposalUpdatePayload
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_service import OrderService


TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def proposal_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'order_proposal_commands.db'}",
        echo=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _create_order(session: AsyncSession) -> int:
    customer = Customer(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        name="Proposal transaction customer",
        phone="+375290000001",
    )
    session.add(customer)
    await session.flush()
    order = Order(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        storefront_id=TEST_TENANT_SCOPE.storefront_id,
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
    )
    session.add(order)
    await session.commit()
    return int(order.id)


async def _fail_after_proposal_flush(
    _session: AsyncSession,
    _order: Order,
) -> None:
    raise RuntimeError("injected final-step failure")


@pytest.mark.asyncio
async def test_create_proposal_rolls_back_default_and_new_proposal_together(
    proposal_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id = await _create_order(proposal_session)
    monkeypatch.setattr(
        OrderService,
        "_refresh_order_financials",
        _fail_after_proposal_flush,
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderProposalCommandService.create_order_proposal(
            proposal_session,
            order_id,
            OrderProposalCreatePayload(name="Новый вариант"),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    proposals = list(
        (
            await proposal_session.execute(
                select(OrderProposal).where(OrderProposal.order_id == order_id)
            )
        )
        .scalars()
        .all()
    )
    assert proposals == []


@pytest.mark.asyncio
async def test_update_proposal_rolls_back_flushed_fields(
    proposal_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id = await _create_order(proposal_session)
    proposal = OrderProposal(
        order_id=order_id,
        name="Исходный вариант",
        status="draft",
        is_selected=True,
        sort_order=0,
    )
    proposal_session.add(proposal)
    await proposal_session.commit()
    proposal_id = int(proposal.id)
    monkeypatch.setattr(
        OrderService,
        "_refresh_order_financials",
        _fail_after_proposal_flush,
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderProposalCommandService.update_order_proposal(
            proposal_session,
            order_id,
            proposal_id,
            OrderProposalUpdatePayload(name="Не должно сохраниться"),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    stored = await proposal_session.get(OrderProposal, proposal_id)
    assert stored is not None
    assert stored.name == "Исходный вариант"


@pytest.mark.asyncio
async def test_select_proposal_rolls_back_all_selection_changes(
    proposal_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id = await _create_order(proposal_session)
    first = OrderProposal(
        order_id=order_id,
        name="Первый",
        status="draft",
        is_selected=True,
        sort_order=0,
    )
    second = OrderProposal(
        order_id=order_id,
        name="Второй",
        status="draft",
        is_selected=False,
        sort_order=10,
    )
    proposal_session.add_all([first, second])
    await proposal_session.commit()
    first_id = int(first.id)
    second_id = int(second.id)
    monkeypatch.setattr(
        OrderService,
        "_refresh_order_financials",
        _fail_after_proposal_flush,
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderProposalCommandService.select_order_proposal(
            proposal_session,
            order_id,
            second_id,
            tenant_scope=TEST_TENANT_SCOPE,
        )

    stored = list(
        (
            await proposal_session.execute(
                select(OrderProposal)
                .where(OrderProposal.order_id == order_id)
                .order_by(OrderProposal.sort_order)
            )
        )
        .scalars()
        .all()
    )
    assert [(item.id, item.is_selected) for item in stored] == [
        (first_id, True),
        (second_id, False),
    ]
