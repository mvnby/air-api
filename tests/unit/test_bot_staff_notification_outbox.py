from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    ConsumerInbox,
    Customer,
    Installer,
    IntegrationOutboxEvent,
    Order,
    OrderStageStatus,
    OrderWorkStage,
    StaffUser,
)
from services.bot_staff_notification_api_service import (
    BotStaffNotificationApiService,
)
import services.bot_staff_notification_api_service as bot_api_module
from services.communications.delivery_service import CommunicationDeliveryService
from services.staff_task_notification_event_service import (
    StaffTaskNotificationEventService,
)


@pytest.fixture
async def staff_outbox_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'staff-outbox.db'}")
    tables = (
        Installer.__table__,
        StaffUser.__table__,
        Customer.__table__,
        Order.__table__,
        OrderWorkStage.__table__,
        IntegrationOutboxEvent.__table__,
        ConsumerInbox.__table__,
        CommunicationDelivery.__table__,
        CommunicationDeliveryAttempt.__table__,
    )
    async with engine.begin() as connection:
        for table in tables:
            await connection.run_sync(table.create)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


async def _seed_task(session: AsyncSession) -> OrderWorkStage:
    installer = Installer(id=10, name="Монтажник")
    staff = StaffUser(
        id=20,
        display_name="Иван",
        status="active",
        roles=["installer"],
        primary_role="installer",
        telegram_id=123456,
        legacy_installer_id=10,
    )
    customer = Customer(id=30, name="Клиент", phone="+375291112233")
    order = Order(id=40, customer_id=30, delivery_address="Минск, Ленина 1")
    stage = OrderWorkStage(
        id=50,
        order_id=40,
        name="Монтаж",
        status=OrderStageStatus.PLANNED,
        start_time=datetime(2026, 7, 20, 10, 0),
        installer_id=10,
    )
    session.add_all([installer, staff, customer, order, stage])
    await session.commit()
    return stage


@pytest.mark.asyncio
async def test_assignment_event_claim_and_ack_use_database_clock(
    staff_outbox_session,
    monkeypatch,
):
    class AppClockMustNotBeRead:
        @classmethod
        def now(cls, *args, **kwargs):
            raise AssertionError("staff lifecycle must use the database clock")

    monkeypatch.setattr(bot_api_module, "datetime", AppClockMustNotBeRead)
    stage = await _seed_task(staff_outbox_session)
    created = await StaffTaskNotificationEventService.enqueue_assigned(
        staff_outbox_session,
        stage=stage,
        previous_installer_id=None,
    )
    duplicate = await StaffTaskNotificationEventService.enqueue_assigned(
        staff_outbox_session,
        stage=stage,
        previous_installer_id=None,
    )
    await staff_outbox_session.commit()

    assert created is True
    assert duplicate is False
    notification = await BotStaffNotificationApiService.claim(
        staff_outbox_session,
        worker_id="bot-1",
        visibility_timeout_seconds=90,
    )

    assert notification is not None
    assert notification["telegram_id"] == 123456
    assert notification["payload"]["event_kind"] == "assigned"
    assert notification["payload"]["stage_id"] == 50
    result = await BotStaffNotificationApiService.ack(
        staff_outbox_session,
        delivery_id=notification["delivery_id"],
        worker_id="bot-1",
        lease_token=notification["lease_token"],
        telegram_message_id=777,
        provider_latency_ms=25,
    )
    delivery = await staff_outbox_session.get(
        CommunicationDelivery,
        notification["delivery_id"],
    )

    assert result.status == "sent"
    assert delivery.status == "sent"
    assert delivery.provider_message_id == "telegram:777"


@pytest.mark.asyncio
async def test_claim_cancels_delivery_when_assignment_is_stale(staff_outbox_session):
    stage = await _seed_task(staff_outbox_session)
    await StaffTaskNotificationEventService.enqueue_assigned(
        staff_outbox_session,
        stage=stage,
        previous_installer_id=None,
    )
    await staff_outbox_session.commit()
    stage.installer_id = None
    staff_outbox_session.add(stage)
    await staff_outbox_session.commit()

    notification = await BotStaffNotificationApiService.claim(
        staff_outbox_session,
        worker_id="bot-1",
        visibility_timeout_seconds=90,
    )
    delivery = (
        await staff_outbox_session.execute(select(CommunicationDelivery))
    ).scalar_one()

    assert notification is None
    assert delivery.status == "canceled"
    assert delivery.last_error_code == "staff_task_assignment_stale"


@pytest.mark.asyncio
async def test_nack_schedules_retry_and_next_claim_increments_attempt(
    staff_outbox_session,
):
    stage = await _seed_task(staff_outbox_session)
    await StaffTaskNotificationEventService.enqueue_assigned(
        staff_outbox_session,
        stage=stage,
        previous_installer_id=None,
    )
    await staff_outbox_session.commit()
    first = await BotStaffNotificationApiService.claim(
        staff_outbox_session,
        worker_id="bot-1",
        visibility_timeout_seconds=90,
    )
    assert first is not None

    failed = await BotStaffNotificationApiService.nack(
        staff_outbox_session,
        delivery_id=first["delivery_id"],
        worker_id="bot-1",
        lease_token=first["lease_token"],
        permanent=False,
        error_code="telegram_retry_after",
        retry_after_seconds=1,
    )
    assert failed.status == "retry"
    delivery = await staff_outbox_session.get(CommunicationDelivery, first["delivery_id"])
    delivery.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    staff_outbox_session.add(delivery)
    await staff_outbox_session.commit()

    second = await BotStaffNotificationApiService.claim(
        staff_outbox_session,
        worker_id="bot-2",
        visibility_timeout_seconds=90,
    )
    assert second is not None
    assert second["attempt"] == 2


@pytest.mark.asyncio
async def test_transport_nack_is_terminal_ambiguous_after_remote_handoff(
    staff_outbox_session,
):
    stage = await _seed_task(staff_outbox_session)
    await StaffTaskNotificationEventService.enqueue_assigned(
        staff_outbox_session,
        stage=stage,
        previous_installer_id=None,
    )
    await staff_outbox_session.commit()
    claim = await BotStaffNotificationApiService.claim(
        staff_outbox_session,
        worker_id="bot-transport-failure",
        visibility_timeout_seconds=90,
    )
    assert claim is not None

    failed = await BotStaffNotificationApiService.nack(
        staff_outbox_session,
        delivery_id=claim["delivery_id"],
        worker_id="bot-transport-failure",
        lease_token=claim["lease_token"],
        permanent=False,
        error_code="telegram_transport_error",
        retry_after_seconds=None,
    )
    attempt = await staff_outbox_session.get(
        CommunicationDeliveryAttempt,
        (claim["delivery_id"], 1),
    )

    assert failed.status == "dead"
    assert attempt is not None
    assert attempt.outcome == "dead"
    assert attempt.ambiguous is True
    assert attempt.error_code == "telegram_transport_error"


@pytest.mark.asyncio
async def test_claim_handoff_expiry_is_terminal_and_never_claimed_again(
    staff_outbox_session,
):
    stage = await _seed_task(staff_outbox_session)
    await StaffTaskNotificationEventService.enqueue_assigned(
        staff_outbox_session,
        stage=stage,
        previous_installer_id=None,
    )
    await staff_outbox_session.commit()
    first = await BotStaffNotificationApiService.claim(
        staff_outbox_session,
        worker_id="bot-that-disappears",
        visibility_timeout_seconds=90,
    )
    assert first is not None

    delivery = await staff_outbox_session.get(
        CommunicationDelivery,
        first["delivery_id"],
    )
    assert delivery is not None
    delivery.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    staff_outbox_session.add(delivery)
    await staff_outbox_session.commit()

    second = await BotStaffNotificationApiService.claim(
        staff_outbox_session,
        worker_id="replacement-bot",
        visibility_timeout_seconds=90,
    )
    await staff_outbox_session.refresh(delivery)
    attempt = await staff_outbox_session.get(
        CommunicationDeliveryAttempt,
        (delivery.delivery_id, 1),
    )

    assert second is None
    assert delivery.status == "dead"
    assert attempt is not None
    assert attempt.provider_started_at is not None
    assert attempt.outcome == "dead"
    assert attempt.ambiguous is True
    assert attempt.error_code == "lease_expired_after_provider"


@pytest.mark.asyncio
async def test_old_api_null_boundary_handoff_is_conservatively_terminal(
    staff_outbox_session,
):
    stage = await _seed_task(staff_outbox_session)
    await StaffTaskNotificationEventService.enqueue_assigned(
        staff_outbox_session,
        stage=stage,
        previous_installer_id=None,
    )
    await staff_outbox_session.commit()
    now = await CommunicationDeliveryService.database_now(
        staff_outbox_session
    )
    await BotStaffNotificationApiService._materialize_pending(
        staff_outbox_session,
        worker_id="old-api",
        now=now,
    )
    old_claim = await CommunicationDeliveryService.claim_next(
        staff_outbox_session,
        worker_id="old-api",
        scope=BotStaffNotificationApiService._SCOPE,
        channel="telegram",
        lease_seconds=90,
        now=now,
    )
    assert old_claim is not None
    await staff_outbox_session.commit()
    delivery = await staff_outbox_session.get(
        CommunicationDelivery,
        old_claim.delivery_id,
    )
    assert delivery is not None
    delivery.lease_expires_at = now - timedelta(seconds=1)
    staff_outbox_session.add(delivery)
    await staff_outbox_session.commit()

    replacement = await BotStaffNotificationApiService.claim(
        staff_outbox_session,
        worker_id="new-api",
        visibility_timeout_seconds=90,
    )
    attempt = await staff_outbox_session.get(
        CommunicationDeliveryAttempt,
        (old_claim.delivery_id, 1),
    )

    assert replacement is None
    assert delivery.status == "dead"
    assert attempt is not None
    assert attempt.provider_started_at is None
    assert attempt.outcome == "dead"
    assert attempt.ambiguous is True
    assert attempt.error_code == "lease_expired_after_provider"


@pytest.mark.asyncio
async def test_departure_reminder_scan_is_idempotent(staff_outbox_session):
    stage = await _seed_task(staff_outbox_session)
    now = datetime(2026, 7, 20, 8, 0)
    stage.start_time = now + timedelta(minutes=120)
    staff_outbox_session.add(stage)
    await staff_outbox_session.commit()

    first = await StaffTaskNotificationEventService.enqueue_departure_reminders(
        staff_outbox_session,
        now=now,
        offset_minutes=120,
        scan_window_minutes=10,
    )
    second = await StaffTaskNotificationEventService.enqueue_departure_reminders(
        staff_outbox_session,
        now=now,
        offset_minutes=120,
        scan_window_minutes=10,
    )

    assert first == 1
    assert second == 0
