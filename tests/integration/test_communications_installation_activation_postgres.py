import asyncio
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

import pytest
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from core.config import settings
from models import (
    CommunicationDelivery,
    CommunicationRuntimeState,
    IntegrationOutboxEvent,
    StaffUser,
)
from services.communications.contracts import (
    InstallationEstimateLeadCreatedPayloadV1,
)
from services.communications.dispatcher import CommunicationOutboxDispatcher
from services.communications.installation_notifications import (
    InstallationNotificationControlRejected,
    InstallationNotificationOperations,
)
from services.communications.installation_activation_fence import (
    INSTALLATION_ACTIVATION_FENCE_LOCK,
    InstallationEventEnqueueFenceBusy,
)
from services.communications.outbox_service import IntegrationOutboxService
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.runtime_config import CommunicationRuntimeConfig
from services.communications.runtime_state import (
    CommunicationRuntimeStateService,
)
from services.communications.template_registry import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
)
from services.runtime_lock_service import RuntimeLockService


def _config(lock_name: str) -> CommunicationRuntimeConfig:
    return CommunicationRuntimeConfig(
        enabled=True,
        app_role="primary",
        allow_all_mode=True,
        lock_name=lock_name,
        instance_id="installation-activation-test",
        poll_seconds=0.01,
        heartbeat_seconds=10,
        lock_retry_seconds=0.01,
        lock_check_seconds=0.01,
        db_probe_timeout_seconds=0.1,
        fencing_seconds=3,
        shutdown_seconds=0.2,
        provider_timeout_seconds=1,
        provider_close_seconds=0.1,
        lease_seconds=30,
    )


def _payload(order_id: int) -> InstallationEstimateLeadCreatedPayloadV1:
    return InstallationEstimateLeadCreatedPayloadV1(
        order_id=order_id,
        status="new_lead",
        name="Activation fence test",
        phone="+375291112233",
        description="Commit ordering",
        attachment_count=1,
        photo_categories=("Место внутреннего блока",),
    )


async def _enqueue(
    factory,
    *,
    order_id: int,
    occurred_at: datetime | None = None,
):
    async with factory() as session:
        result = await IntegrationOutboxService.enqueue_with_result(
            session,
            event_type=INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
            aggregate_type="order",
            aggregate_id=order_id,
            payload=_payload(order_id),
            idempotency_key=f"activation-fence:{order_id}",
            occurred_at=occurred_at,
        )
        await session.commit()
        return result


@pytest.fixture
async def activation_context(db_engine, monkeypatch):
    assert db_engine.dialect.name == "postgresql"
    monkeypatch.setattr(
        settings,
        "RUNTIME_DB_LOCKS_ENABLED",
        True,
        raising=False,
    )
    factory = sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    config = _config(f"mvn:test:installation-activation:{uuid4()}")
    runtime_lock = await RuntimeLockService.try_acquire(
        factory,
        config.lock_name,
        required=True,
    )
    assert runtime_lock.acquired
    try:
        async with factory() as session:
            now = await CommunicationRuntimeStateService.database_now(session)
            state = await CommunicationRuntimeStateService.ensure_state(
                session,
                channel="telegram",
            )
            state.status = "disabled"
            state.instance_id = config.instance_id
            state.started_at = now
            state.heartbeat_at = now
            state.updated_at = now
            session.add_all(
                [
                    state,
                    StaffUser(
                        display_name="Owner",
                        status="active",
                        roles=["owner"],
                        primary_role="owner",
                        telegram_id=90001,
                    ),
                ]
            )
            await session.commit()
        yield factory, config
    finally:
        await runtime_lock.release()


async def _activate(factory, config):
    async with factory() as session:
        try:
            inspection, revision, watermark = (
                await InstallationNotificationOperations.activate_installation_from_off(
                    session,
                    config=config,
                    bot_token="valid-token",
                    runtime_locks_enabled=True,
                )
            )
        except InstallationNotificationControlRejected as error:
            await session.rollback()
            return error.error_code
        await session.commit()
        return inspection, revision, watermark


@pytest.mark.asyncio
async def test_activation_fails_fast_behind_uncommitted_enqueue_then_inventories_it(
    activation_context,
):
    factory, config = activation_context
    async with factory() as enqueue_session:
        enqueued = await IntegrationOutboxService.enqueue_with_result(
            enqueue_session,
            event_type=INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
            aggregate_type="order",
            aggregate_id=701,
            payload=_payload(701),
            idempotency_key="activation-fence:701",
        )
        assert enqueued.created is True

        activation_task = asyncio.create_task(_activate(factory, config))
        result = await asyncio.wait_for(activation_task, timeout=1)
        assert result == "installation_activation_fence_busy"
        await enqueue_session.commit()

    assert await _activate(factory, config) == "installation_backlog_not_reconciled"
    async with factory() as session:
        event = await session.get(
            IntegrationOutboxEvent,
            enqueued.event.event_id,
        )
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert event is not None and event.status == "pending"
        assert state is not None and state.mode == "off"
        assert state.installation_estimate_watermark_at is None


@pytest.mark.asyncio
async def test_enqueue_after_activation_is_in_scope_and_replay_is_unique(
    activation_context,
    monkeypatch,
):
    factory, config = activation_context
    activation_inside_inventory = asyncio.Event()
    release_activation = asyncio.Event()
    original_backlog_count = InstallationNotificationOperations._backlog_count

    async def paused_backlog_count(cls, session, *, cutoff):
        activation_inside_inventory.set()
        await release_activation.wait()
        return await original_backlog_count(session, cutoff=cutoff)

    monkeypatch.setattr(
        InstallationNotificationOperations,
        "_backlog_count",
        classmethod(paused_backlog_count),
    )

    activation_task = asyncio.create_task(_activate(factory, config))
    await asyncio.wait_for(activation_inside_inventory.wait(), timeout=3)
    enqueue_task = asyncio.create_task(
        _enqueue(
            factory,
            order_id=702,
            occurred_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
    )
    await asyncio.sleep(0.1)
    assert enqueue_task.done() is False

    release_activation.set()
    activation = await asyncio.wait_for(activation_task, timeout=3)
    assert not isinstance(activation, str)
    _, revision, watermark = activation
    enqueued = await asyncio.wait_for(enqueue_task, timeout=3)
    assert enqueued.created is True

    replay = await _enqueue(factory, order_id=702)
    assert replay.created is False
    assert replay.event.event_id == enqueued.event.event_id

    async with factory() as session:
        event = await session.get(
            IntegrationOutboxEvent,
            enqueued.event.event_id,
        )
        assert event is not None
        assert CommunicationRuntimeStateService._as_utc(
            event.created_at
        ) >= watermark
        assert CommunicationRuntimeStateService._as_utc(
            event.occurred_at
        ) < watermark
        monkeypatch.setattr(
            CommunicationOutboxDispatcher,
            "_utc_now",
            staticmethod(
                lambda: datetime(1990, 1, 1, tzinfo=timezone.utc)
            ),
        )
        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session,
            scope=CommunicationProcessingScope.all(
                control_revision=revision,
                event_created_at_watermark=watermark,
            ),
            dispatcher_id="activation-fence-dispatcher",
        )
        await session.commit()
        assert outcome is not None
        assert outcome.outcome == "materialized"
        assert outcome.delivery_count == 1
        assert (
            await session.scalar(
                select(func.count(IntegrationOutboxEvent.event_id)).where(
                    IntegrationOutboxEvent.event_id == event.event_id
                )
            )
        ) == 1
        assert (
            await session.scalar(
                select(func.count(CommunicationDelivery.delivery_id)).where(
                    CommunicationDelivery.event_id == event.event_id
                )
            )
        ) == 1


@pytest.mark.asyncio
async def test_normal_enqueues_share_the_fence_without_serializing(
    activation_context,
):
    factory, _ = activation_context
    async with factory() as first_session:
        first = await IntegrationOutboxService.enqueue_with_result(
            first_session,
            event_type=INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
            aggregate_type="order",
            aggregate_id=703,
            payload=_payload(703),
            idempotency_key="activation-fence:703",
        )
        assert first.created is True

        second = await asyncio.wait_for(
            _enqueue(factory, order_id=704),
            timeout=1,
        )
        assert second.created is True
        await first_session.rollback()


@pytest.mark.asyncio
async def test_activation_rejects_repeatable_read_before_control_mutation(
    activation_context,
):
    factory, config = activation_context
    async with factory() as session:
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        )
        with pytest.raises(
            InstallationNotificationControlRejected,
            match="database_isolation_not_read_committed",
        ):
            await InstallationNotificationOperations.activate_installation_from_off(
                session,
                config=config,
                bot_token="valid-token",
                runtime_locks_enabled=True,
            )
        await session.rollback()

    async with factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state is not None
        assert state.mode == "off"
        assert state.control_revision == 0
        assert state.installation_estimate_watermark_at is None


@pytest.mark.asyncio
async def test_short_exclusive_holder_delays_enqueue_then_db_stamps_it(
    activation_context,
):
    factory, _ = activation_context
    async with factory() as holder:
        await holder.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtext(:lock_name))"
            ),
            {"lock_name": INSTALLATION_ACTIVATION_FENCE_LOCK},
        )
        enqueue_task = asyncio.create_task(
            _enqueue(factory, order_id=705)
        )
        await asyncio.sleep(0.1)
        assert enqueue_task.done() is False
        await holder.commit()

    result = await asyncio.wait_for(enqueue_task, timeout=2)
    assert result.created is True
    async with factory() as session:
        event = await session.get(
            IntegrationOutboxEvent,
            result.event.event_id,
        )
        assert event is not None
        assert event.occurred_at == event.created_at
        assert event.available_at == event.created_at


@pytest.mark.asyncio
async def test_long_exclusive_holder_aborts_enqueue_with_bounded_error(
    activation_context,
):
    factory, _ = activation_context
    async with factory() as holder:
        await holder.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtext(:lock_name))"
            ),
            {"lock_name": INSTALLATION_ACTIVATION_FENCE_LOCK},
        )
        started = monotonic()
        with pytest.raises(InstallationEventEnqueueFenceBusy):
            await asyncio.wait_for(
                _enqueue(factory, order_id=706),
                timeout=2,
            )
        elapsed = monotonic() - started
        assert 0.8 <= elapsed < 1.8
        await holder.rollback()

    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(IntegrationOutboxEvent.event_id)).where(
                    IntegrationOutboxEvent.aggregate_id == "706"
                )
            )
        ) == 0
