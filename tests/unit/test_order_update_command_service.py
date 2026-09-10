from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import (
    Customer,
    CustomerType,
    Order,
    OrderProductLink,
    OrderProposal,
    OrderServiceLink,
    OrderStatus,
    Product,
)
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


@pytest.mark.asyncio
async def test_manager_order_update_sets_individual_entrepreneur_and_self_signing(
    update_session: AsyncSession,
):
    order_id, customer_id = await _create_order(update_session)

    await OrderUpdateCommandService.update_order_for_manager(
        update_session,
        order_id,
        ManagerOrderUpdatePayload(customer_type="individual_entrepreneur"),
        tenant_scope=TEST_TENANT_SCOPE,
    )

    customer = await update_session.get(Customer, customer_id)
    assert customer is not None
    assert customer.type == CustomerType.individual_entrepreneur
    assert customer.signing_mode == "self"


@pytest.mark.asyncio
async def test_explicit_line_proposal_scope_clears_empty_alternative_without_touching_selected(
    update_session: AsyncSession,
):
    order_id, _ = await _create_order(update_session)
    selected_product = Product(
        title="Выбранный товар",
        slug="selected-product-line-scope",
        price=500,
    )
    alternative_product = Product(
        title="Товар альтернативы",
        slug="alternative-product-line-scope",
        price=700,
    )
    update_session.add_all([selected_product, alternative_product])
    await update_session.flush()

    selected_proposal = OrderProposal(
        order_id=order_id,
        name="Выбранный вариант",
        is_selected=True,
    )
    alternative_proposal = OrderProposal(
        order_id=order_id,
        name="Альтернативный вариант",
    )
    update_session.add_all([selected_proposal, alternative_proposal])
    await update_session.flush()
    update_session.add_all(
        [
            OrderProductLink(
                order_id=order_id,
                proposal_id=selected_proposal.id,
                product_id=selected_product.id,
                quantity=1,
                price=500,
            ),
            OrderProductLink(
                order_id=order_id,
                proposal_id=alternative_proposal.id,
                product_id=alternative_product.id,
                quantity=1,
                price=700,
            ),
            OrderServiceLink(
                order_id=order_id,
                proposal_id=selected_proposal.id,
                title="Выбранная услуга",
                quantity=1,
                price=100,
            ),
            OrderServiceLink(
                order_id=order_id,
                proposal_id=alternative_proposal.id,
                title="Услуга альтернативы",
                quantity=1,
                price=200,
            ),
        ]
    )
    await update_session.commit()

    await OrderUpdateCommandService.update_order_for_manager(
        update_session,
        order_id,
        ManagerOrderUpdatePayload(
            line_proposal_id=alternative_proposal.id,
            products=[],
            services=[],
        ),
        tenant_scope=TEST_TENANT_SCOPE,
    )

    selected_product_links = list(
        (
            await update_session.execute(
                select(OrderProductLink).where(
                    OrderProductLink.proposal_id == selected_proposal.id
                )
            )
        ).scalars()
    )
    selected_service_links = list(
        (
            await update_session.execute(
                select(OrderServiceLink).where(
                    OrderServiceLink.proposal_id == selected_proposal.id
                )
            )
        ).scalars()
    )
    alternative_product_links = list(
        (
            await update_session.execute(
                select(OrderProductLink).where(
                    OrderProductLink.proposal_id == alternative_proposal.id
                )
            )
        ).scalars()
    )
    alternative_service_links = list(
        (
            await update_session.execute(
                select(OrderServiceLink).where(
                    OrderServiceLink.proposal_id == alternative_proposal.id
                )
            )
        ).scalars()
    )
    assert [line.product_id for line in selected_product_links] == [selected_product.id]
    assert [line.title for line in selected_service_links] == ["Выбранная услуга"]
    assert alternative_product_links == []
    assert alternative_service_links == []


@pytest.mark.asyncio
async def test_explicit_line_proposal_scope_rejects_conflicting_line_ids(
    update_session: AsyncSession,
):
    order_id, _ = await _create_order(update_session)
    product = Product(
        title="Товар для проверки области",
        slug="line-scope-conflicting-id-product",
        price=500,
    )
    selected_proposal = OrderProposal(order_id=order_id, is_selected=True)
    alternative_proposal = OrderProposal(order_id=order_id, name="Альтернатива")
    update_session.add_all([product, selected_proposal, alternative_proposal])
    await update_session.commit()

    with pytest.raises(
        ValueError,
        match="Line proposal scope must match every line proposal_id",
    ):
        await OrderUpdateCommandService.update_order_for_manager(
            update_session,
            order_id,
            ManagerOrderUpdatePayload(
                line_proposal_id=alternative_proposal.id,
                products=[
                    {
                        "product_id": product.id,
                        "proposal_id": selected_proposal.id,
                        "quantity": 1,
                        "price": 500,
                    }
                ],
            ),
            tenant_scope=TEST_TENANT_SCOPE,
        )


@pytest.mark.asyncio
async def test_explicit_line_proposal_scope_rejects_foreign_and_locked_proposals(
    update_session: AsyncSession,
):
    order_id, customer_id = await _create_order(update_session)
    selected_proposal = OrderProposal(order_id=order_id, is_selected=True)
    locked_proposal = OrderProposal(
        order_id=order_id,
        name="Отправленный вариант",
        status="sent",
    )
    foreign_order = Order(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        storefront_id=TEST_TENANT_SCOPE.storefront_id,
        customer_id=customer_id,
        status=OrderStatus.NEGOTIATION,
    )
    update_session.add_all([selected_proposal, locked_proposal, foreign_order])
    await update_session.flush()
    foreign_proposal = OrderProposal(order_id=foreign_order.id, is_selected=True)
    update_session.add(foreign_proposal)
    await update_session.flush()
    locked_proposal_id = int(locked_proposal.id)
    foreign_proposal_id = int(foreign_proposal.id)
    await update_session.commit()

    with pytest.raises(ValueError, match="Proposal not found"):
        await OrderUpdateCommandService.update_order_for_manager(
            update_session,
            order_id,
            ManagerOrderUpdatePayload(
                line_proposal_id=foreign_proposal_id,
                products=[],
            ),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    with pytest.raises(ValueError, match="cannot be edited"):
        await OrderUpdateCommandService.update_order_for_manager(
            update_session,
            order_id,
            ManagerOrderUpdatePayload(
                line_proposal_id=locked_proposal_id,
                products=[],
            ),
            tenant_scope=TEST_TENANT_SCOPE,
        )
