import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from api_contracts.bot import BotQuickOrderDraft
from models import (
    Customer,
    CustomerRequisitesRecognition,
    Lead,
    Order,
    OrderWorkStage,
    StaffUser,
    TenantMembership,
)
from services.bot_customer_requisites_api_service import BotCustomerRequisitesApiService
from services.bot_quick_order_api_service import BotQuickOrderApiService
from services.tenant_scope_service import SystemTenantScopeResolver


@pytest.mark.asyncio
async def test_postgres_bot_order_and_customer_mutations_are_concurrently_idempotent(
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
        staff_user = StaffUser(
            display_name="Concurrency manager",
            status="active",
            roles=["manager"],
            primary_role="manager",
            telegram_id=987650001,
        )
        setup_session.add(staff_user)
        await setup_session.flush()
        setup_session.add(
            TenantMembership(
                tenant_id=tenant_scope.tenant_id,
                staff_user_id=int(staff_user.id),
                role="manager",
                status="active",
            )
        )
        recognition = CustomerRequisitesRecognition(
            tenant_id=tenant_scope.tenant_id,
            source="telegram_text",
            status="recognized",
            telegram_user_id=987650001,
            telegram_chat_id=-100,
            telegram_message_id=77,
            raw_text="ООО Конкурент УНП 123456789",
            extracted_json={
                "name": "ООО Конкурент",
                "inn": "123456789",
                "phone": "+375291234567",
            },
            validation_flags={"field_errors": {}, "warnings": {}, "is_valid": True},
        )
        setup_session.add(recognition)
        await setup_session.commit()

    notify = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "services.bot_quick_order_service.NotificationService.notify_admins_staff_order_created",
        notify,
    )
    draft = BotQuickOrderDraft(
        name="Иван",
        phone="+375291111111",
        address="Победы 15",
        service_type="install_only",
        service_label="Монтаж",
        target_date="2026-07-20T14:00:00",
        request_text="Монтаж, Иван, Победы 15",
    )
    order_barrier = asyncio.Barrier(12)

    async def create_order_once():
        async with session_factory() as session:
            await order_barrier.wait()
            return await BotQuickOrderApiService.create_for_manager(
                session,
                telegram_id=987650001,
                idempotency_key="telegram:-100:55",
                draft=draft,
            )

    order_results = await asyncio.gather(*(create_order_once() for _ in range(12)))

    assert len({result.order_id for result in order_results}) == 1
    assert len({result.customer_id for result in order_results}) == 1
    assert sum(result.created for result in order_results) == 1
    notify.assert_awaited_once()

    action_barrier = asyncio.Barrier(12)

    async def confirm_customer_once():
        async with session_factory() as session:
            await action_barrier.wait()
            return await BotCustomerRequisitesApiService.apply_action_for_manager(
                session,
                telegram_id=987650001,
                recognition_id=int(recognition.id),
                action="create",
                tenant_scope=tenant_scope,
            )

    action_results = await asyncio.gather(*(confirm_customer_once() for _ in range(12)))

    assert sum(result.changed for result in action_results) == 1
    assert len({result.customer["id"] for result in action_results}) == 1

    async with session_factory() as verification_session:
        leads = (await verification_session.execute(select(Lead))).scalars().all()
        orders = (await verification_session.execute(select(Order))).scalars().all()
        stages = (await verification_session.execute(select(OrderWorkStage))).scalars().all()
        customers = (await verification_session.execute(select(Customer))).scalars().all()
        persisted_recognition = await verification_session.get(
            CustomerRequisitesRecognition,
            recognition.id,
        )

    assert len(leads) == 1
    assert len(orders) == 1
    assert len(stages) == 1
    assert len(customers) == 2
    assert persisted_recognition.status == "confirmed"
