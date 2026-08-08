from datetime import datetime, timedelta, timezone

import pytest

from models import CommunicationDelivery, CommunicationDeliveryAttempt
from services.communications.delivery_service import CommunicationDeliveryService
from services.communications.delivery_worker import CommunicationDeliveryWorker
from services.communications.provider_boundary_authorization import (
    WebsiteCanaryProviderBoundaryRejected,
)
from services.communications.providers.base import ProviderDeliveryResult
from tests.unit.test_communication_delivery_worker import (
    ALL_SCOPE,
    RecordingProvider,
    _seed_delivery,
    worker_session_factory,
)


async def _claim_then_expire(
    session_factory,
    *,
    delivery_id: str,
    mark_provider_started: bool,
) -> None:
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        claim = await CommunicationDeliveryService.claim_next(
            session,
            scope=ALL_SCOPE,
            worker_id="crashed-worker",
            lease_seconds=60,
            now=now,
        )
        assert claim is not None
        await session.commit()
    async with session_factory() as session:
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert attempt is not None
        attempt.started_at = now - timedelta(seconds=2)
        session.add(attempt)
        await session.commit()
    if mark_provider_started:
        async with session_factory() as session:
            await CommunicationDeliveryService.mark_provider_started(
                session,
                delivery_id=delivery_id,
                worker_id="crashed-worker",
                lease_token=claim.lease_token,
                lease_seconds=60,
                now=now - timedelta(seconds=1),
            )
            await session.commit()
    async with session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.add(row)
        await session.commit()


@pytest.mark.asyncio
async def test_crash_before_provider_boundary_retries_then_sends_once(
    worker_session_factory,
    monkeypatch,
):
    _, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=91,
        telegram_id=910091,
    )
    await _claim_then_expire(
        worker_session_factory,
        delivery_id=delivery_id,
        mark_provider_started=False,
    )
    provider = RecordingProvider(
        worker_session_factory,
        {"910091": ProviderDeliveryResult.sent("provider-boundary-safe-retry")},
    )
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="replacement-worker",
        lease_seconds=60,
    )

    recovered = await worker.run_once()
    assert recovered.outcome == "idle"
    assert recovered.recovered_retry_count == 1
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None and row.status == "retry"
        due_at = CommunicationDeliveryService._coerce_database_datetime(
            row.available_at
        )
        first_attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert first_attempt is not None
        assert first_attempt.outcome == "retry"
        assert first_attempt.provider_started_at is None
        assert first_attempt.ambiguous is False
        assert first_attempt.error_code == "lease_expired_before_provider"

    async def after_backoff(cls, session):
        return due_at + timedelta(seconds=1)

    monkeypatch.setattr(
        CommunicationDeliveryService,
        "_database_now",
        classmethod(after_backoff),
    )
    sent = await worker.run_once()
    idle = await worker.run_once()

    assert sent.outcome == "sent"
    assert idle.outcome == "idle"
    assert len(provider.calls) == 1
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        assert row.status == "sent"
        assert row.attempts == 2
        second_attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 2),
        )
        assert second_attempt is not None
        assert second_attempt.outcome == "sent"
        assert second_attempt.provider_started_at is not None


@pytest.mark.asyncio
async def test_crash_after_provider_boundary_is_terminal_and_never_calls_again(
    worker_session_factory,
):
    _, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=92,
        telegram_id=920092,
    )
    await _claim_then_expire(
        worker_session_factory,
        delivery_id=delivery_id,
        mark_provider_started=True,
    )
    provider = RecordingProvider(
        worker_session_factory,
        {"920092": ProviderDeliveryResult.sent("must-not-send")},
    )
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="replacement-worker",
        lease_seconds=60,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "idle"
    assert outcome.recovered_dead_count == 1
    assert provider.calls == []
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert row is not None and row.status == "dead"
        assert attempt is not None
        assert attempt.outcome == "dead"
        assert attempt.provider_started_at is not None
        assert attempt.ambiguous is True
        assert attempt.error_code == "lease_expired_after_provider"


@pytest.mark.asyncio
async def test_provider_boundary_database_failure_prevents_network_call(
    worker_session_factory,
    monkeypatch,
):
    _, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=93,
        telegram_id=930093,
    )
    provider = RecordingProvider(
        worker_session_factory,
        {"930093": ProviderDeliveryResult.sent("must-not-send")},
    )
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="boundary-failure-worker",
        lease_seconds=60,
    )

    async def fail_boundary(cls, session, **kwargs):
        raise RuntimeError("simulated provider-boundary database failure")

    monkeypatch.setattr(
        CommunicationDeliveryService,
        "mark_provider_started",
        classmethod(fail_boundary),
    )

    with pytest.raises(
        RuntimeError,
        match="simulated provider-boundary database failure",
    ):
        await worker.run_once()
    assert provider.calls == []
    async with worker_session_factory() as session:
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert attempt is not None
        assert attempt.outcome == "running"
        assert attempt.provider_started_at is None


@pytest.mark.asyncio
async def test_boundary_control_rejection_exhausts_without_ambiguity(
    worker_session_factory,
):
    _, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=94,
        telegram_id=940094,
        max_attempts=1,
    )
    provider = RecordingProvider(
        worker_session_factory,
        {"940094": ProviderDeliveryResult.sent("must-not-send")},
    )

    async def reject_boundary(_session):
        raise RuntimeError("runtime control changed")

    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="boundary-control-rejected-worker",
        lease_seconds=60,
        provider_boundary_check=reject_boundary,
    )

    with pytest.raises(RuntimeError, match="runtime control changed"):
        await worker.run_once()

    assert provider.calls == []
    async with worker_session_factory() as session:
        delivery = await session.get(CommunicationDelivery, delivery_id)
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert delivery is not None
        assert delivery.status == "dead"
        assert delivery.worker_id is None
        assert delivery.lease_token is None
        assert delivery.lease_expires_at is None
        assert attempt is not None
        assert attempt.outcome == "dead"
        assert attempt.provider_started_at is None
        assert attempt.ambiguous is False
        assert attempt.error_code == "runtime_control_fenced_before_provider"


@pytest.mark.asyncio
async def test_recipient_revoked_after_early_check_cancels_before_provider(
    worker_session_factory,
):
    _, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=95,
        telegram_id=950095,
    )
    provider = RecordingProvider(
        worker_session_factory,
        {"950095": ProviderDeliveryResult.sent("must-not-send")},
    )

    async def revoked_at_boundary(_session, _claim):
        async def reject_delivery(_delivery):
            raise WebsiteCanaryProviderBoundaryRejected(
                "website_canary_provider_boundary_rejected"
            )

        return reject_delivery

    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="recipient-revoked-race-worker",
        lease_seconds=60,
        provider_boundary_authorizer=revoked_at_boundary,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "canceled"
    assert provider.calls == []
    async with worker_session_factory() as session:
        delivery = await session.get(CommunicationDelivery, delivery_id)
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert delivery is not None and delivery.status == "canceled"
        assert attempt is not None and attempt.outcome == "canceled"
        assert attempt.provider_started_at is None
        assert attempt.ambiguous is False
        assert attempt.error_code == "recipient_inactive"
