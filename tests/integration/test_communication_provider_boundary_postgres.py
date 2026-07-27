import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    CommunicationRuntimeState,
)
from services.communications.delivery_service import CommunicationDeliveryService
from services.communications.delivery_worker import CommunicationDeliveryWorker
from services.communications.installation_notifications import (
    InstallationNotificationOperations,
)
from services.communications.providers.base import ProviderDeliveryResult
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.runtime_state import (
    CommunicationRuntimeMode,
    CommunicationRuntimeModeBlocked,
    CommunicationRuntimeStateService,
)
from tests.integration.test_communication_delivery_concurrency import (
    ALL_SCOPE,
    _seed_deliveries,
    communication_db_engine,
)
from tests.unit.test_communication_delivery_worker import (
    RecordingProvider,
    _seed_delivery,
)


RUNTIME_INSTANCE_ID = "provider-boundary-runtime"


async def _seed_owned_all_runtime(factory) -> CommunicationProcessingScope:
    async with factory() as session:
        state = await CommunicationRuntimeStateService.ensure_state(
            session,
            channel="telegram",
        )
        watermark = await CommunicationRuntimeStateService.database_now(session)
        CommunicationRuntimeStateService._apply_control(
            state,
            mode=CommunicationRuntimeMode.ALL,
            canary_run_id=None,
            now=watermark,
            installation_estimate_watermark_at=watermark,
        )
        state.status = "running"
        state.instance_id = RUNTIME_INSTANCE_ID
        await session.flush()
        control = CommunicationRuntimeStateService._to_control(state)
        await session.commit()
    assert control.installation_estimate_watermark_at is not None
    return CommunicationProcessingScope.all(
        control_revision=control.control_revision,
        event_created_at_watermark=control.installation_estimate_watermark_at,
    )


async def _switch_runtime_off(factory) -> None:
    async with factory() as session:
        await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=CommunicationRuntimeMode.OFF,
        )
        await session.commit()


def _runtime_boundary_check(scope):
    async def check(session):
        await CommunicationRuntimeStateService.lock_owned_processing_scope(
            session,
            channel="telegram",
            instance_id=RUNTIME_INSTANCE_ID,
            scope=scope,
        )

    return check


@pytest.mark.asyncio
async def test_concurrent_failover_recovers_one_expired_attempt_once(
    communication_db_engine,
):
    await _seed_deliveries(communication_db_engine, 1, expired=True)
    factory = sessionmaker(
        communication_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with factory() as first, factory() as second:
        first_result = (
            await CommunicationDeliveryService.recover_expired_leases(
                first,
                scope=ALL_SCOPE,
            )
        )
        second_result = await asyncio.wait_for(
            CommunicationDeliveryService.recover_expired_leases(
                second,
                scope=ALL_SCOPE,
            ),
            timeout=2,
        )
        assert first_result.retry_count == 1
        assert second_result.retry_count == 0
        assert first_result.dead_count == second_result.dead_count == 0
        await second.commit()
        await first.commit()

    async with factory() as session:
        delivery = await session.get(CommunicationDelivery, f"{1:032x}")
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (f"{1:032x}", 1),
        )
        assert delivery is not None and delivery.status == "retry"
        assert attempt is not None and attempt.outcome == "retry"
        assert attempt.ambiguous is False


@pytest.mark.asyncio
async def test_post_provider_expiry_is_dead_ambiguous_and_never_reclaimed(
    communication_db_engine,
):
    await _seed_deliveries(communication_db_engine, 1)
    factory = sessionmaker(
        communication_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    now = datetime.now(timezone.utc)
    async with factory() as session:
        claim = await CommunicationDeliveryService.claim_next(
            session,
            scope=ALL_SCOPE,
            worker_id="provider-boundary-worker",
            lease_seconds=60,
            now=now,
        )
        assert claim is not None
        await session.commit()
    async with factory() as session:
        await CommunicationDeliveryService.mark_provider_started(
            session,
            delivery_id=claim.delivery_id,
            worker_id="provider-boundary-worker",
            lease_token=claim.lease_token,
            lease_seconds=60,
            now=now + timedelta(seconds=1),
        )
        await session.commit()
    recovery_time = now + timedelta(seconds=62)
    async with factory() as session:
        result = await CommunicationDeliveryService.recover_expired_leases(
            session,
            scope=ALL_SCOPE,
            now=recovery_time,
        )
        await session.commit()
        assert result.retry_count == 0
        assert result.dead_count == 1

    async with factory() as session:
        claim_again = await CommunicationDeliveryService.claim_next(
            session,
            scope=ALL_SCOPE,
            worker_id="replacement-worker",
            now=recovery_time + timedelta(seconds=1),
        )
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (claim.delivery_id, 1),
        )
        assert claim_again is None
        assert attempt is not None
        assert attempt.provider_started_at is not None
        assert attempt.outcome == "dead"
        assert attempt.ambiguous is True
        assert attempt.error_code == "lease_expired_after_provider"


@pytest.mark.asyncio
async def test_committed_off_between_preflight_and_boundary_prevents_provider_call(
    db_engine,
):
    factory = sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    scope = await _seed_owned_all_runtime(factory)
    _, delivery_id = await _seed_delivery(
        factory,
        sequence=501,
        telegram_id=501501,
    )
    provider = RecordingProvider(
        factory,
        {"501501": ProviderDeliveryResult.sent("must-not-send")},
    )
    final_preflight = asyncio.Event()
    release_preflight = asyncio.Event()
    safety_calls = 0

    async def safety_check():
        nonlocal safety_calls
        safety_calls += 1
        if safety_calls == 3:
            final_preflight.set()
            await release_preflight.wait()

    worker = CommunicationDeliveryWorker(
        session_factory=factory,
        scope=scope,
        provider=provider,
        worker_id=RUNTIME_INSTANCE_ID,
        lease_seconds=60,
        safety_check=safety_check,
        provider_boundary_check=_runtime_boundary_check(scope),
    )
    worker_task = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(final_preflight.wait(), timeout=3)
    await _switch_runtime_off(factory)
    release_preflight.set()

    with pytest.raises(CommunicationRuntimeModeBlocked):
        await asyncio.wait_for(worker_task, timeout=3)

    assert provider.calls == []
    async with factory() as session:
        await CommunicationRuntimeStateService.record_status(
            session,
            channel="telegram",
            instance_id=RUNTIME_INSTANCE_ID,
            status="disabled",
        )
        await session.commit()
    drain = await InstallationNotificationOperations.wait_until_off_drained(
        factory,
        wait_seconds=0,
    )
    assert drain["drained"] is True
    assert drain["running_delivery_count"] == 0
    async with factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        delivery = await session.get(CommunicationDelivery, delivery_id)
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert state is not None and state.mode == "off"
        assert delivery is not None
        assert delivery.status == "retry"
        assert delivery.worker_id is None
        assert delivery.lease_token is None
        assert delivery.lease_expires_at is None
        assert attempt is not None
        assert attempt.outcome == "retry"
        assert attempt.provider_started_at is None
        assert attempt.ambiguous is False
        assert attempt.error_code == "runtime_control_fenced_before_provider"
        assert (
            await InstallationNotificationOperations._backlog_count(
                session,
                cutoff=None,
            )
            == 1
        )


@pytest.mark.asyncio
async def test_boundary_lock_commits_before_concurrent_off_and_sends_once(
    db_engine,
):
    factory = sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    scope = await _seed_owned_all_runtime(factory)
    _, delivery_id = await _seed_delivery(
        factory,
        sequence=502,
        telegram_id=502502,
    )
    provider = RecordingProvider(
        factory,
        {"502502": ProviderDeliveryResult.sent("boundary-before-off")},
    )
    boundary_locked = asyncio.Event()
    release_boundary = asyncio.Event()

    async def holding_boundary_check(session):
        await CommunicationRuntimeStateService.lock_owned_processing_scope(
            session,
            channel="telegram",
            instance_id=RUNTIME_INSTANCE_ID,
            scope=scope,
        )
        boundary_locked.set()
        await release_boundary.wait()

    worker = CommunicationDeliveryWorker(
        session_factory=factory,
        scope=scope,
        provider=provider,
        worker_id=RUNTIME_INSTANCE_ID,
        lease_seconds=60,
        provider_boundary_check=holding_boundary_check,
    )
    worker_task = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(boundary_locked.wait(), timeout=3)
    off_task = asyncio.create_task(_switch_runtime_off(factory))
    await asyncio.sleep(0.05)
    assert off_task.done() is False

    release_boundary.set()
    outcome, _ = await asyncio.wait_for(
        asyncio.gather(worker_task, off_task),
        timeout=5,
    )

    assert outcome.outcome == "sent"
    assert len(provider.calls) == 1
    async with factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert state is not None and state.mode == "off"
        assert attempt is not None
        assert attempt.outcome == "sent"
        assert attempt.provider_started_at is not None
