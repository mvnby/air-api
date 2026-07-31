import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from models import (
    Installer,
    Order,
    OrderStageStatus,
    OrderStatus,
    OrderWorkStage,
    StaffUser,
    TenantMembership,
)
from services.bot_task_mutation_service import BotTaskMutationService
from services.tenant_scope_service import SystemTenantScopeResolver


@pytest.mark.asyncio
async def test_postgres_duplicate_bot_task_mutations_change_each_value_once(
    db_engine,
    monkeypatch,
):
    assert db_engine.dialect.name == "postgresql"
    session_factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as setup_session:
        tenant_scope = await SystemTenantScopeResolver.resolve(setup_session)
        installer = Installer(name="Concurrency installer")
        setup_session.add(installer)
        await setup_session.flush()
        staff_user = StaffUser(
            display_name="Concurrency staff",
            status="active",
            roles=["installer"],
            telegram_id=987654321,
            legacy_installer_id=installer.id,
        )
        setup_session.add(staff_user)
        await setup_session.flush()
        setup_session.add(
            TenantMembership(
                tenant_id=tenant_scope.tenant_id,
                staff_user_id=int(staff_user.id),
                role="installer",
                status="active",
            )
        )
        order = Order(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            status=OrderStatus.EXECUTION,
            title="Concurrency order",
        )
        setup_session.add(order)
        await setup_session.flush()
        status_stage = OrderWorkStage(
            order_id=order.id,
            name="Status stage",
            installer_id=installer.id,
            status=OrderStageStatus.PLANNED,
        )
        report_stage = OrderWorkStage(
            order_id=order.id,
            name="Report stage",
            installer_id=installer.id,
            status=OrderStageStatus.IN_PROGRESS,
        )
        setup_session.add_all([status_stage, report_stage])
        await setup_session.commit()

    notify = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "services.bot_task_mutation_service.NotificationService.notify_admins_work_stage_status_changed",
        notify,
    )

    status_barrier = asyncio.Barrier(12)

    async def accept_stage_once() -> bool:
        async with session_factory() as session:
            await status_barrier.wait()
            result = await BotTaskMutationService.update_stage_status(
                session,
                telegram_id=987654321,
                stage_id=status_stage.id,
                status=OrderStageStatus.IN_PROGRESS,
                tenant_scope=tenant_scope,
            )
            return result.changed

    status_changes = await asyncio.gather(*(accept_stage_once() for _ in range(12)))

    report_barrier = asyncio.Barrier(12)

    async def save_report_once() -> bool:
        async with session_factory() as session:
            await report_barrier.wait()
            result = await BotTaskMutationService.save_stage_report(
                session,
                telegram_id=987654321,
                stage_id=report_stage.id,
                report="Один и тот же отчет",
                tenant_scope=tenant_scope,
            )
            return result.changed

    report_changes = await asyncio.gather(*(save_report_once() for _ in range(12)))

    assert status_changes.count(True) == 1
    assert report_changes.count(True) == 1
    notify.assert_awaited_once()

    async with session_factory() as verification_session:
        persisted_status_stage = await verification_session.get(
            OrderWorkStage,
            status_stage.id,
        )
        persisted_report_stage = await verification_session.get(
            OrderWorkStage,
            report_stage.id,
        )
    assert persisted_status_stage.status == OrderStageStatus.IN_PROGRESS
    assert persisted_report_stage.installer_report == "Один и тот же отчет"
