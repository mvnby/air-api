from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Customer, Order, OrderProductLink, OrderProposal, OrderStatus, Product
from models.tenancy import TenantScope
from schemas import ManagerOrderUpdatePayload
from services.order_service import OrderService
from services.order_update.command import OrderUpdateCommandService
from services.staff_task_notification_event_service import (
    StaffTaskNotificationEventService,
)


TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def update_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'order_update_commands.db'}",
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


async def _create_order(session: AsyncSession) -> tuple[int, int]:
    customer = Customer(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        name="Исходный клиент",
        phone="+375290000004",
    )
    session.add(customer)
    await session.flush()
    order = Order(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        storefront_id=TEST_TENANT_SCOPE.storefront_id,
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
        title="Исходный заказ",
        delivery_address="Старый адрес",
    )
    session.add(order)
    await session.commit()
    return int(order.id), int(customer.id)


@pytest.mark.asyncio
async def test_update_rolls_back_order_and_customer_when_outbox_enqueue_fails(
    update_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id, customer_id = await _create_order(update_session)
    monkeypatch.setattr(
        StaffTaskNotificationEventService,
        "enqueue_address_changes",
        AsyncMock(side_effect=RuntimeError("injected final-step failure")),
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderUpdateCommandService.update_order_for_manager(
            update_session,
            order_id,
            ManagerOrderUpdatePayload(
                title="Не должно сохраниться",
                customer_name="Не должен измениться",
                customer_delivery_address="Новый адрес",
            ),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    stored_order = await update_session.get(Order, order_id)
    stored_customer = await update_session.get(Customer, customer_id)
    assert stored_order is not None
    assert stored_order.title == "Исходный заказ"
    assert stored_order.delivery_address == "Старый адрес"
    assert stored_customer is not None
    assert stored_customer.name == "Исходный клиент"


@pytest.mark.asyncio
async def test_update_rolls_back_default_proposal_and_product_lines(
    update_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id, _ = await _create_order(update_session)
    product = Product(
        title="Тестовый товар",
        slug="transactional-order-update-product",
        price=500,
    )
    update_session.add(product)
    await update_session.commit()
    product_id = int(product.id)

    async def fail_financial_refresh(
        _session: AsyncSession,
        _order: Order,
    ) -> None:
        raise RuntimeError("injected final-step failure")

    monkeypatch.setattr(
        OrderService,
        "_refresh_order_financials",
        fail_financial_refresh,
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderUpdateCommandService.update_order_for_manager(
            update_session,
            order_id,
            ManagerOrderUpdatePayload(
                products=[
                    {
                        "product_id": product_id,
                        "quantity": 1,
                        "price": 500,
                    }
                ]
            ),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    proposals = list(
        (
            await update_session.execute(
                select(OrderProposal).where(OrderProposal.order_id == order_id)
            )
        ).scalars()
    )
    product_lines = list(
        (
            await update_session.execute(
                select(OrderProductLink).where(OrderProductLink.order_id == order_id)
            )
        ).scalars()
    )
    assert proposals == []
    assert product_lines == []


@pytest.mark.asyncio
async def test_lost_order_does_not_archive_shared_customer_with_active_other_storefront_order(
    update_session: AsyncSession,
):
    order_id, customer_id = await _create_order(update_session)
    other_storefront_order = Order(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        storefront_id=2,
        customer_id=customer_id,
        status=OrderStatus.NEGOTIATION,
        title="Активный заказ другого storefront",
    )
    update_session.add(other_storefront_order)
    await update_session.commit()

    result = await OrderUpdateCommandService.update_order_for_manager(
        update_session,
        order_id,
        ManagerOrderUpdatePayload(
            status="closed",
            closing_result="lost",
            reject_reason="Тест межвитринного архива",
        ),
        tenant_scope=TEST_TENANT_SCOPE,
    )

    stored_customer = await update_session.get(Customer, customer_id)
    assert result is not None
    assert stored_customer is not None
    assert stored_customer.is_archived is False
