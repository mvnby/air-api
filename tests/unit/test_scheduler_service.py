from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Customer, Order, OrderStatus
from services.scheduler_service import SchedulerService


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scheduler.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_check_stalled_deals_marks_old_negotiations_for_follow_up(sqlite_session):
    customer = Customer(name="Scheduler Customer", phone="+375290000000")
    sqlite_session.add(customer)
    await sqlite_session.flush()

    old_order = Order(
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
        negotiation_status="awaiting_offer",
        updated_at=datetime.now() - timedelta(days=16),
        technical_meta={"source": "test"},
    )
    recent_order = Order(
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
        negotiation_status="awaiting_offer",
        updated_at=datetime.now() - timedelta(days=2),
    )
    execution_order = Order(
        customer_id=customer.id,
        status=OrderStatus.EXECUTION,
        negotiation_status="awaiting_offer",
        updated_at=datetime.now() - timedelta(days=16),
    )
    sqlite_session.add_all([old_order, recent_order, execution_order])
    await sqlite_session.commit()

    await SchedulerService().check_stalled_deals(sqlite_session)

    rows = (
        await sqlite_session.execute(select(Order).order_by(Order.id))
    ).scalars().all()
    old_order, recent_order, execution_order = rows

    assert old_order.status == OrderStatus.NEGOTIATION
    assert old_order.negotiation_status == "follow_up"
    assert old_order.next_followup_date is not None
    assert old_order.technical_meta["source"] == "test"
    assert old_order.technical_meta["stalled_follow_up_reason"]

    assert recent_order.negotiation_status == "awaiting_offer"
    assert recent_order.next_followup_date is None
    assert execution_order.status == OrderStatus.EXECUTION
    assert execution_order.negotiation_status == "awaiting_offer"

    first_followup = old_order.next_followup_date
    await SchedulerService().check_stalled_deals(sqlite_session)
    await sqlite_session.refresh(old_order)

    assert old_order.next_followup_date == first_followup
