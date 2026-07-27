from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from conftest import TEST_DATABASE_URL
from core.config import settings
from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    CommunicationRuntimeState,
    IntegrationOutboxEvent,
)
from scripts.reconcile_installation_estimate_backlog import run_command
from services.communications.backlog_reconciliation import (
    STALE_BACKLOG_ERROR_CODE,
    InstallationEstimateBacklogExecutionBlocked,
)
from services.communications.runtime_config import CommunicationRuntimeConfig
from services.communications.template_registry import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    INSTALLATION_ESTIMATE_TEMPLATE_KEY,
)
from services.runtime_lock_service import RuntimeLock, RuntimeLockService


@pytest_asyncio.fixture
async def reconciliation_postgres_factory(monkeypatch):
    schema_name = f"communications_backlog_{uuid4().hex}"
    admin_engine = create_async_engine(TEST_DATABASE_URL)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(IntegrationOutboxEvent.__table__.create)
        await connection.run_sync(CommunicationDelivery.__table__.create)
        await connection.run_sync(CommunicationDeliveryAttempt.__table__.create)
        await connection.run_sync(CommunicationRuntimeState.__table__.create)
    monkeypatch.setattr(
        settings,
        "RUNTIME_DB_LOCKS_ENABLED",
        True,
        raising=False,
    )
    monkeypatch.setattr(settings, "APP_ROLE", "primary", raising=False)
    monkeypatch.setattr(
        settings,
        "COMMUNICATIONS_WORKER_ENABLED",
        False,
        raising=False,
    )
    monkeypatch.setattr(
        settings,
        "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE",
        False,
        raising=False,
    )
    factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        yield factory
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        await admin_engine.dispose()


def _event(
    sequence: int,
    *,
    status: str,
    created_at: datetime,
) -> IntegrationOutboxEvent:
    return IntegrationOutboxEvent(
        event_id=f"{sequence:032x}",
        event_type=INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
        schema_version=1,
        aggregate_type="order",
        aggregate_id=str(sequence),
        aggregate_version=1,
        deduplication_key=f"postgres-backlog:{sequence}",
        payload={"order_id": sequence, "phone": "+375291112233"},
        status=status,
        available_at=created_at,
        occurred_at=created_at,
        published_at=created_at if status == "published" else None,
        created_at=created_at,
        updated_at=created_at,
    )


def _delivery(
    sequence: int,
    *,
    event: IntegrationOutboxEvent,
    status: str,
    now: datetime,
) -> CommunicationDelivery:
    running = status == "running"
    retry = status == "retry"
    return CommunicationDelivery(
        delivery_id=f"{sequence + 10_000:032x}",
        event_id=event.event_id,
        channel="telegram",
        recipient_key=f"staff:{sequence}",
        destination=str(700_000 + sequence),
        template_key=INSTALLATION_ESTIMATE_TEMPLATE_KEY,
        template_version=1,
        render_context={"order_id": sequence},
        status=status,
        priority=20,
        attempts=1 if running or retry else 0,
        max_attempts=8,
        available_at=now,
        worker_id="stopped-runtime" if running else None,
        lease_token="x" * 40 if running else None,
        lease_expires_at=now - timedelta(minutes=1) if running else None,
        created_at=now,
        updated_at=now,
    )


async def _seed_stopped_runtime(factory, *, mode: str = "off") -> None:
    now = datetime.now(timezone.utc)
    async with factory() as session:
        session.add(
            CommunicationRuntimeState(
                channel="telegram",
                mode=mode,
                installation_estimate_watermark_at=(
                    now if mode == "all" else None
                ),
                status="stopped",
                control_revision=1,
                control_updated_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_execute_suppresses_pending_and_materialized_backlog_atomically(
    reconciliation_postgres_factory,
):
    factory = reconciliation_postgres_factory
    await _seed_stopped_runtime(factory)
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    cutoff = now - timedelta(days=2)
    pending = _event(1, status="pending", created_at=now - timedelta(days=6))
    published = _event(
        2,
        status="published",
        created_at=now - timedelta(days=5),
    )
    processing = _event(
        3,
        status="processing",
        created_at=now - timedelta(days=4),
    )
    queued = _delivery(2, event=published, status="queued", now=now)
    running = _delivery(3, event=processing, status="running", now=now)
    async with factory() as session:
        session.add_all([pending, published, processing, queued, running])
        session.add(
            CommunicationDeliveryAttempt(
                delivery_id=running.delivery_id,
                attempt_no=1,
                started_at=now - timedelta(minutes=3),
                outcome="running",
            )
        )
        await session.commit()

    report = await run_command(
        cutoff=cutoff,
        limit=10,
        execute=True,
        session_factory=factory,
        now=now,
    )

    assert report["candidate_total"] == 3
    assert report["suppressed_count"] == 3
    assert report["suppressed_delivery_count"] == 2
    assert report["ambiguous_delivery_count"] == 1
    assert report["remaining_candidate_count"] == 0
    assert report["activation_safe"] is True
    async with factory() as session:
        for event in (pending, published, processing):
            stored_event = await session.get(
                IntegrationOutboxEvent,
                event.event_id,
            )
            assert stored_event is not None
            assert stored_event.status == "dead"
            assert stored_event.last_error_code == STALE_BACKLOG_ERROR_CODE
        stored_queued = await session.get(
            CommunicationDelivery,
            queued.delivery_id,
        )
        assert stored_queued is not None
        assert stored_queued.status == "canceled"
        assert stored_queued.attempts == 1
        queued_attempt = await session.get(
            CommunicationDeliveryAttempt,
            (queued.delivery_id, 1),
        )
        assert queued_attempt is not None
        assert queued_attempt.outcome == "canceled"
        assert queued_attempt.ambiguous is False
        stored_running = await session.get(
            CommunicationDelivery,
            running.delivery_id,
        )
        assert stored_running is not None
        assert stored_running.status == "dead"
        assert stored_running.worker_id is None
        running_attempt = await session.get(
            CommunicationDeliveryAttempt,
            (running.delivery_id, 1),
        )
        assert running_attempt is not None
        assert running_attempt.outcome == "dead"
        assert running_attempt.ambiguous is True
        assert running_attempt.finished_at is not None


@pytest.mark.asyncio
async def test_execute_fails_closed_while_runtime_lock_is_owned(
    reconciliation_postgres_factory,
):
    factory = reconciliation_postgres_factory
    await _seed_stopped_runtime(factory)
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    event = _event(11, status="pending", created_at=now - timedelta(days=5))
    async with factory() as session:
        session.add(event)
        await session.commit()

    config = CommunicationRuntimeConfig.from_settings()
    held_lock = await RuntimeLockService.try_acquire(
        factory,
        config.lock_name,
        required=True,
    )
    assert held_lock.acquired
    try:
        with pytest.raises(
            InstallationEstimateBacklogExecutionBlocked,
            match="communications_runtime_lock_unavailable",
        ):
            await run_command(
                cutoff=now - timedelta(days=2),
                limit=10,
                execute=True,
                session_factory=factory,
                now=now,
            )
    finally:
        await held_lock.release()

    async with factory() as session:
        stored = await session.get(IntegrationOutboxEvent, event.event_id)
        assert stored is not None and stored.status == "pending"


@pytest.mark.asyncio
async def test_execute_fails_closed_unless_runtime_mode_is_off(
    reconciliation_postgres_factory,
):
    factory = reconciliation_postgres_factory
    await _seed_stopped_runtime(factory, mode="all")
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    event = _event(21, status="pending", created_at=now - timedelta(days=5))
    async with factory() as session:
        session.add(event)
        await session.commit()

    with pytest.raises(
        InstallationEstimateBacklogExecutionBlocked,
        match="communications_runtime_mode_not_off",
    ):
        await run_command(
            cutoff=now - timedelta(days=2),
            limit=10,
            execute=True,
            session_factory=factory,
            now=now,
        )

    async with factory() as session:
        stored = await session.get(IntegrationOutboxEvent, event.event_id)
        assert stored is not None and stored.status == "pending"


@pytest.mark.asyncio
async def test_execute_fails_closed_when_deployment_gate_is_enabled(
    reconciliation_postgres_factory,
    monkeypatch,
):
    factory = reconciliation_postgres_factory
    await _seed_stopped_runtime(factory)
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    event = _event(25, status="pending", created_at=now - timedelta(days=5))
    async with factory() as session:
        session.add(event)
        await session.commit()

    monkeypatch.setattr(
        settings,
        "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE",
        True,
        raising=False,
    )
    with pytest.raises(
        InstallationEstimateBacklogExecutionBlocked,
        match="communications_runtime_deployment_gate_enabled",
    ):
        await run_command(
            cutoff=now - timedelta(days=2),
            limit=10,
            execute=True,
            session_factory=factory,
            now=now,
        )

    async with factory() as session:
        stored = await session.get(IntegrationOutboxEvent, event.event_id)
        assert stored is not None and stored.status == "pending"


@pytest.mark.asyncio
async def test_execute_rolls_back_when_runtime_lock_is_lost_before_commit(
    reconciliation_postgres_factory,
    monkeypatch,
):
    factory = reconciliation_postgres_factory
    await _seed_stopped_runtime(factory)
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    event = _event(27, status="pending", created_at=now - timedelta(days=5))
    async with factory() as session:
        session.add(event)
        await session.commit()

    original_is_held = RuntimeLock.is_held
    checks = 0

    async def lose_after_preflight(runtime_lock):
        nonlocal checks
        checks += 1
        if checks == 1:
            return await original_is_held(runtime_lock)
        return False

    monkeypatch.setattr(RuntimeLock, "is_held", lose_after_preflight)
    with pytest.raises(
        InstallationEstimateBacklogExecutionBlocked,
        match="communications_runtime_lock_lost",
    ):
        await run_command(
            cutoff=now - timedelta(days=2),
            limit=10,
            execute=True,
            session_factory=factory,
            now=now,
        )

    assert checks == 2
    async with factory() as session:
        stored = await session.get(IntegrationOutboxEvent, event.event_id)
        assert stored is not None and stored.status == "pending"


@pytest.mark.asyncio
async def test_execute_skips_concurrently_locked_event_without_blocking(
    reconciliation_postgres_factory,
):
    factory = reconciliation_postgres_factory
    await _seed_stopped_runtime(factory)
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    cutoff = now - timedelta(days=2)
    first = _event(31, status="pending", created_at=now - timedelta(days=6))
    second = _event(32, status="pending", created_at=now - timedelta(days=5))
    async with factory() as seed:
        seed.add_all([first, second])
        await seed.commit()

    async with factory() as owner:
        await owner.execute(
            select(IntegrationOutboxEvent)
            .where(IntegrationOutboxEvent.event_id == first.event_id)
            .with_for_update()
        )
        report = await run_command(
            cutoff=cutoff,
            limit=1,
            execute=True,
            session_factory=factory,
            now=now,
        )
        assert report["selected_count"] == 1
        assert report["suppressed_count"] == 1
        assert report["remaining_candidate_count"] == 1
        assert report["truncated"] is True
        await owner.rollback()

    async with factory() as session:
        stored_first = await session.get(
            IntegrationOutboxEvent,
            first.event_id,
        )
        stored_second = await session.get(
            IntegrationOutboxEvent,
            second.event_id,
        )
        assert stored_first is not None and stored_first.status == "pending"
        assert stored_second is not None and stored_second.status == "dead"
