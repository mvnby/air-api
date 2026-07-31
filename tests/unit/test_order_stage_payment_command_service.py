from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import (
    Customer,
    Installer,
    Order,
    OrderStageStatus,
    OrderStatus,
    OrderWorkStage,
    Payment,
)
from models.tenancy import TenantScope
from schemas import (
    OrderWorkStageCreatePayload,
    OrderWorkStageUpdatePayload,
    PaymentCreatePayload,
)
from services.order_payment_command_service import OrderPaymentCommandService
from services.order_service import OrderService
from services.order_work_stage_command_service import OrderWorkStageCommandService
from services.staff_task_notification_event_service import (
    StaffTaskNotificationEventService,
)


TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def command_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'order_stage_payment_commands.db'}",
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


async def _create_order(
    session: AsyncSession,
    *,
    with_installer: bool = False,
) -> tuple[int, int | None]:
    customer = Customer(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        name="Command transaction customer",
        phone="+375290000002",
    )
    session.add(customer)
    installer = Installer(name="Command transaction installer", is_active=True)
    if with_installer:
        session.add(installer)
    await session.flush()
    order = Order(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        storefront_id=TEST_TENANT_SCOPE.storefront_id,
        customer_id=customer.id,
        status=OrderStatus.EXECUTION,
    )
    session.add(order)
    await session.commit()
    return int(order.id), int(installer.id) if with_installer else None


async def _create_stage(
    session: AsyncSession,
    order_id: int,
    *,
    installer_id: int | None = None,
) -> int:
    stage = OrderWorkStage(
        order_id=order_id,
        name="Исходный этап",
        status=OrderStageStatus.PLANNED,
        installer_id=installer_id,
    )
    session.add(stage)
    await session.commit()
    return int(stage.id)


async def _fail_financial_refresh(
    _session: AsyncSession,
    _order: Order,
) -> None:
    raise RuntimeError("injected final-step failure")


@pytest.mark.asyncio
async def test_add_stage_rolls_back_stage_when_outbox_enqueue_fails(
    command_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id, installer_id = await _create_order(
        command_session,
        with_installer=True,
    )
    monkeypatch.setattr(
        StaffTaskNotificationEventService,
        "enqueue_assigned",
        AsyncMock(side_effect=RuntimeError("injected final-step failure")),
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderWorkStageCommandService.add_order_stage(
            command_session,
            order_id,
            OrderWorkStageCreatePayload(
                name="Новый этап",
                installer_id=installer_id,
            ),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    stages = list(
        (
            await command_session.execute(
                select(OrderWorkStage).where(OrderWorkStage.order_id == order_id)
            )
        )
        .scalars()
        .all()
    )
    assert stages == []


@pytest.mark.asyncio
async def test_cancel_stage_rolls_back_status_when_outbox_enqueue_fails(
    command_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id, _ = await _create_order(command_session)
    stage_id = await _create_stage(command_session, order_id)
    monkeypatch.setattr(
        StaffTaskNotificationEventService,
        "enqueue_canceled",
        AsyncMock(side_effect=RuntimeError("injected final-step failure")),
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderWorkStageCommandService.cancel_order_stage_direct(
            command_session,
            stage_id,
            tenant_scope=TEST_TENANT_SCOPE,
        )

    stored = await command_session.get(OrderWorkStage, stage_id)
    assert stored is not None
    assert stored.status == OrderStageStatus.PLANNED


@pytest.mark.asyncio
async def test_update_stage_rolls_back_fields_when_outbox_enqueue_fails(
    command_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id, _ = await _create_order(command_session)
    stage_id = await _create_stage(command_session, order_id)
    monkeypatch.setattr(
        StaffTaskNotificationEventService,
        "enqueue_canceled",
        AsyncMock(side_effect=RuntimeError("injected final-step failure")),
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderWorkStageCommandService.update_order_stage(
            command_session,
            order_id,
            stage_id,
            OrderWorkStageUpdatePayload(
                name="Не должно сохраниться",
                status="canceled",
            ),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    stored = await command_session.get(OrderWorkStage, stage_id)
    assert stored is not None
    assert stored.name == "Исходный этап"
    assert stored.status == OrderStageStatus.PLANNED


@pytest.mark.asyncio
@pytest.mark.parametrize("direct", [False, True])
async def test_delete_stage_rolls_back_deletion_on_final_failure(
    command_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    direct: bool,
):
    order_id, _ = await _create_order(command_session)
    stage_id = await _create_stage(command_session, order_id)
    original_delete = AsyncSession.delete

    async def delete_then_fail(session: AsyncSession, instance: object) -> None:
        await original_delete(session, instance)
        raise RuntimeError("injected final-step failure")

    monkeypatch.setattr(AsyncSession, "delete", delete_then_fail)

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        if direct:
            await OrderWorkStageCommandService.delete_order_stage_direct(
                command_session,
                stage_id,
                tenant_scope=TEST_TENANT_SCOPE,
            )
        else:
            await OrderWorkStageCommandService.delete_order_stage(
                command_session,
                order_id,
                stage_id,
                tenant_scope=TEST_TENANT_SCOPE,
            )

    assert await command_session.get(OrderWorkStage, stage_id) is not None


@pytest.mark.asyncio
async def test_add_payment_rolls_back_flushed_payment_on_final_failure(
    command_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id, _ = await _create_order(command_session)
    monkeypatch.setattr(
        OrderService,
        "_refresh_order_financials",
        _fail_financial_refresh,
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderPaymentCommandService.add_payment(
            command_session,
            order_id,
            PaymentCreatePayload(amount=100, type="prepayment"),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    payments = list(
        (
            await command_session.execute(
                select(Payment).where(Payment.order_id == order_id)
            )
        )
        .scalars()
        .all()
    )
    assert payments == []


@pytest.mark.asyncio
async def test_delete_payment_rolls_back_deletion_on_final_failure(
    command_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id, _ = await _create_order(command_session)
    payment = Payment(order_id=order_id, amount=100)
    command_session.add(payment)
    await command_session.commit()
    payment_id = int(payment.id)
    monkeypatch.setattr(
        OrderService,
        "_refresh_order_financials",
        _fail_financial_refresh,
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderPaymentCommandService.delete_payment(
            command_session,
            order_id,
            payment_id,
            tenant_scope=TEST_TENANT_SCOPE,
        )

    assert await command_session.get(Payment, payment_id) is not None
