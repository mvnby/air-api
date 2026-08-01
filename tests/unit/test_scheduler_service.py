import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import (
    Customer,
    IntegrationOutboxEvent,
    Order,
    OrderStatus,
    Product,
    Storefront,
    Tenant,
)
import services.scheduler_service as scheduler_module
from services.scheduler_service import SchedulerService


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scheduler.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            Tenant(
                id=1,
                slug="mvn",
                display_name="MVN",
                status="active",
                is_system=True,
            )
        )
        await session.flush()
        session.add(
            Storefront(
                id=1,
                tenant_id=1,
                slug="main",
                display_name="MVN",
                status="active",
                is_default=True,
            )
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_check_stalled_deals_marks_old_negotiations_for_follow_up(sqlite_session):
    customer = Customer(tenant_id=1, name="Scheduler Customer", phone="+375290000000")
    sqlite_session.add(customer)
    await sqlite_session.flush()

    old_order = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
        negotiation_status="awaiting_offer",
        updated_at=datetime.now() - timedelta(days=16),
        technical_meta={"source": "test"},
    )
    recent_order = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
        negotiation_status="awaiting_offer",
        updated_at=datetime.now() - timedelta(days=2),
    )
    execution_order = Order(
        tenant_id=1,
        storefront_id=1,
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


@pytest.mark.asyncio
async def test_start_loop_cancels_child_tasks(monkeypatch):
    service = SchedulerService()
    monkeypatch.setattr(scheduler_module.settings, "ENVIRONMENT", "development", raising=False)
    started = 0
    cancelled = 0

    async def child_loop():
        nonlocal started, cancelled
        started += 1
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled += 1
            raise

    for method_name in (
        "_price_sync_loop",
        "_stalled_deal_loop",
        "_lead_archive_loop",
        "_supplier_sync_loop",
        "_bank_mail_import_loop",
        "_email_lead_import_loop",
    ):
        monkeypatch.setattr(service, method_name, lambda *args: child_loop())

    task = asyncio.create_task(service.start_loop(interval_hours=1))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert started == 6
    assert cancelled == 6


@pytest.mark.asyncio
async def test_daily_backup_rejects_skipped_result(monkeypatch):
    service = SchedulerService()
    monkeypatch.setattr(
        scheduler_module.backup_service,
        "perform_backup",
        lambda cleanup=True: False,
    )

    with pytest.raises(RuntimeError, match="skipped or did not complete"):
        await service._run_daily_backup()


@pytest.mark.asyncio
async def test_scheduled_price_change_uses_durable_catalog_invalidation(
    sqlite_session,
    monkeypatch,
):
    product = Product(
        title="Scheduled price model",
        slug="scheduled-price-model",
        price=1000,
        source_url="https://supplier.example/model",
    )
    sqlite_session.add(product)
    await sqlite_session.commit()
    product_id = int(product.id)
    factory = sessionmaker(
        bind=sqlite_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr(scheduler_module, "async_session_maker", factory)

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(scheduler_module.asyncio, "sleep", no_sleep)
    service = SchedulerService()

    async def parse(_url):
        return {"price": 1250}

    service.parser.parse = parse

    await service.update_all_prices()

    sqlite_session.expire_all()
    stored_product = await sqlite_session.get(Product, product_id)
    event = (
        await sqlite_session.execute(select(IntegrationOutboxEvent))
    ).scalar_one()
    assert stored_product is not None
    assert stored_product.price == 1250
    assert event.payload["reason"] == "scheduled_product_price_sync"
    assert "/product/scheduled-price-model/" in event.payload["paths"]
