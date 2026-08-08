from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from core.config import settings
from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    IntegrationOutboxEvent,
    StaffUser,
)
from services.communications.contracts import (
    InstallationEstimateLeadCreatedPayloadV1,
)
from services.communications.delivery_service import (
    CommunicationDeliveryLeaseLost,
    CommunicationDeliveryService,
)
from services.communications.delivery_worker import CommunicationDeliveryWorker
from services.communications.providers.base import ProviderDeliveryResult
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.template_registry import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    INSTALLATION_ESTIMATE_TEMPLATE_KEY,
)
from tests.unit.tenant_website_test_support import (
    add_tenant_members,
    ensure_tenant_website_scope,
)

ALL_SCOPE = CommunicationProcessingScope.all(
    control_revision=0,
    event_created_at_watermark=datetime(2000, 1, 1, tzinfo=timezone.utc),
)


@pytest.fixture
async def worker_session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'worker.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_delivery(
    session_factory,
    *,
    sequence: int,
    telegram_id: int,
    status: str = "active",
    priority: int = 100,
    max_attempts: int = 3,
) -> tuple[int, str]:
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        await ensure_tenant_website_scope(session)
        owner = StaffUser(
            display_name=f"Owner {sequence}",
            status=status,
            roles=["owner"],
            primary_role="owner",
            telegram_id=telegram_id,
        )
        await add_tenant_members(session, owner)
        assert owner.id is not None
        delivery_id = f"{sequence:032x}"
        event_id = f"{sequence + 1000:032x}"
        session.add(
            IntegrationOutboxEvent(
                event_id=event_id,
                event_type=INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
                schema_version=1,
                aggregate_type="order",
                aggregate_id=str(sequence),
                deduplication_key=f"delivery-worker:{sequence}",
                payload={},
                status="published",
                available_at=now,
                occurred_at=now,
                published_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            CommunicationDelivery(
                delivery_id=delivery_id,
                event_id=event_id,
                channel="telegram",
                recipient_key=f"staff:{owner.id}",
                destination=str(telegram_id),
                template_key=INSTALLATION_ESTIMATE_TEMPLATE_KEY,
                template_version=1,
                render_context=InstallationEstimateLeadCreatedPayloadV1(
                    tenant_id=1,
                    storefront_id=1,
                    order_id=sequence,
                    status="new_lead",
                    name=f"Lead {sequence}",
                    phone="+375291112233",
                    description="Нужна консультация",
                    attachment_count=2,
                    photo_categories=("Внутренний блок", "Наружный блок"),
                ).model_dump(mode="json"),
                status="queued",
                priority=priority,
                attempts=0,
                max_attempts=max_attempts,
                available_at=now - timedelta(seconds=1),
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
        return owner.id, delivery_id


class RecordingProvider:
    channel = "telegram"

    def __init__(self, session_factory, outcomes):
        self._session_factory = session_factory
        self._outcomes = outcomes
        self.calls: list[tuple[str, str, str]] = []
        self.claim_was_durable = False
        self.provider_boundary_was_durable = False

    async def send(self, *, destination: str, text: str, delivery_id: str):
        async with self._session_factory() as session:
            row = await session.get(CommunicationDelivery, delivery_id)
            attempt = await session.get(
                CommunicationDeliveryAttempt,
                (delivery_id, int(row.attempts) if row is not None else 0),
            )
            self.claim_was_durable = bool(
                row
                and row.status == "running"
                and row.worker_id
                and row.lease_token
                and row.lease_expires_at
            )
            self.provider_boundary_was_durable = bool(
                attempt and attempt.provider_started_at is not None
            )
        self.calls.append((destination, text, delivery_id))
        outcome = self._outcomes[destination]
        return outcome() if callable(outcome) else outcome

    async def close(self):
        return None


class HeartbeatObservingProvider:
    channel = "telegram"

    def __init__(self, session_factory):
        self._session_factory = session_factory
        self.lease_was_extended = False

    async def send(self, *, destination: str, text: str, delivery_id: str):
        async with self._session_factory() as session:
            before = await session.get(CommunicationDelivery, delivery_id)
            assert before is not None
            initial_expiry = before.lease_expires_at
        await asyncio.sleep(1.2)
        async with self._session_factory() as session:
            after = await session.get(CommunicationDelivery, delivery_id)
            assert after is not None
            self.lease_was_extended = bool(
                initial_expiry
                and after.lease_expires_at
                and after.lease_expires_at > initial_expiry
            )
        return ProviderDeliveryResult.sent("heartbeat-message")

    async def close(self):
        return None


class ImmediateProvider:
    channel = "telegram"

    def __init__(self):
        self.calls = 0

    async def send(self, *, destination: str, text: str, delivery_id: str):
        self.calls += 1
        return ProviderDeliveryResult.sent("immediate-message")

    async def close(self):
        return None


class CancellationRaceProvider:
    channel = "telegram"

    def __init__(self):
        self.completed = asyncio.Event()

    async def send(self, *, destination: str, text: str, delivery_id: str):
        self.completed.set()
        return ProviderDeliveryResult.sent("cancellation-race-message")

    async def close(self):
        return None


class ImmediateFailureProvider:
    channel = "telegram"

    async def send(self, *, destination: str, text: str, delivery_id: str):
        return ProviderDeliveryResult.transient_failure(
            category="network",
            code="timeout",
            message="Telegram request timed out",
        )

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_worker_commits_claim_before_provider_and_marks_sent(
    worker_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    _, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=1,
        telegram_id=101001,
    )
    provider = RecordingProvider(
        worker_session_factory,
        {"101001": ProviderDeliveryResult.sent("message-1")},
    )
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="test-worker",
        lease_seconds=60,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "sent"
    assert outcome.delivery_id == delivery_id
    assert provider.claim_was_durable is True
    assert provider.provider_boundary_was_durable is True
    assert len(provider.calls) == 1
    assert "Lead 1" in provider.calls[0][1]
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        assert row.status == "sent"
        assert row.attempts == 1
        assert row.provider_message_id == "message-1"
        assert row.worker_id is None
        assert row.lease_token is None
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert attempt is not None
        assert attempt.outcome == "sent"
        assert attempt.provider_latency_ms is not None
        assert attempt.provider_latency_ms >= 0


@pytest.mark.asyncio
async def test_worker_renews_lease_while_provider_call_is_in_flight(
    worker_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    monkeypatch.setattr(CommunicationDeliveryService, "MIN_LEASE_SECONDS", 1)
    await _seed_delivery(
        worker_session_factory,
        sequence=10,
        telegram_id=101010,
    )
    provider = HeartbeatObservingProvider(worker_session_factory)
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="heartbeat-worker",
        lease_seconds=3,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "sent"
    assert provider.lease_was_extended is True


@pytest.mark.asyncio
async def test_worker_refences_expired_lease_before_network_call(
    worker_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    await _seed_delivery(
        worker_session_factory,
        sequence=11,
        telegram_id=111011,
    )
    provider = ImmediateProvider()
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="preflight-worker",
        lease_seconds=60,
    )
    original_recipient_check = worker._recipient_is_current

    async def expire_after_recipient_check(claim, plan):
        is_current = await original_recipient_check(claim, plan)
        async with worker_session_factory() as session:
            row = await session.get(CommunicationDelivery, claim.delivery_id)
            assert row is not None
            row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(row)
            await session.commit()
        return is_current

    monkeypatch.setattr(worker, "_recipient_is_current", expire_after_recipient_check)

    outcome = await worker.run_once()

    assert outcome.outcome == "lease_lost"
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_known_provider_result_wins_simultaneous_heartbeat_failure(
    worker_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    _, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=12,
        telegram_id=121012,
    )
    provider = ImmediateProvider()
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="simultaneous-worker",
        lease_seconds=60,
    )

    async def fail_heartbeat_immediately(_claim, _stop):
        raise CommunicationDeliveryLeaseLost("simulated simultaneous lease signal")

    monkeypatch.setattr(worker, "_heartbeat", fail_heartbeat_immediately)

    outcome = await worker.run_once()

    assert outcome.outcome == "sent"
    assert provider.calls == 1
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        assert row.status == "sent"
        assert row.provider_message_id == "immediate-message"


@pytest.mark.asyncio
async def test_managed_cancellation_preserves_known_provider_result(
    worker_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    _, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=13,
        telegram_id=131013,
    )
    provider = CancellationRaceProvider()
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="cancellation-worker",
        lease_seconds=60,
    )

    run_task = asyncio.create_task(worker.run_once())
    await provider.completed.wait()
    run_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run_task

    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        assert row.status == "sent"
        assert row.provider_message_id == "cancellation-race-message"


@pytest.mark.asyncio
async def test_cancellation_inside_sent_finalizer_commits_then_propagates(
    worker_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    _, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=14,
        telegram_id=141014,
    )
    provider = ImmediateProvider()
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="sent-finalizer-worker",
        lease_seconds=60,
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    original_mark_sent = worker._mark_sent

    async def blocked_mark_sent(
        claim,
        provider_message_id,
        provider_latency_ms=None,
    ):
        entered.set()
        await release.wait()
        await original_mark_sent(
            claim,
            provider_message_id,
            provider_latency_ms=provider_latency_ms,
        )

    monkeypatch.setattr(worker, "_mark_sent", blocked_mark_sent)
    run_task = asyncio.create_task(worker.run_once())
    await entered.wait()
    run_task.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await run_task
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        assert row.status == "sent"
        assert row.provider_message_id == "immediate-message"


@pytest.mark.asyncio
async def test_cancellation_inside_failure_finalizer_commits_then_propagates(
    worker_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    _, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=15,
        telegram_id=151015,
    )
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=ImmediateFailureProvider(),
        worker_id="failure-finalizer-worker",
        lease_seconds=60,
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    original_record_failure = worker._record_failure

    async def blocked_record_failure(
        claim,
        result,
        recovery,
        provider_latency_ms=None,
    ):
        entered.set()
        await release.wait()
        return await original_record_failure(
            claim,
            result,
            recovery,
            provider_latency_ms=provider_latency_ms,
        )

    monkeypatch.setattr(worker, "_record_failure", blocked_record_failure)
    run_task = asyncio.create_task(worker.run_once())
    await entered.wait()
    run_task.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await run_task
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        assert row.status == "dead"
        assert row.last_error_code == "timeout"
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert attempt is not None
        assert attempt.outcome == "dead"
        assert attempt.provider_latency_ms is not None
        assert attempt.provider_latency_ms >= 0
        assert attempt.ambiguous is True


@pytest.mark.asyncio
async def test_worker_keeps_recipient_failures_independent(
    worker_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    _, ambiguous_delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=3,
        telegram_id=303003,
        priority=1,
    )
    sent_delivery_id = f"{4:032x}"
    async with worker_session_factory() as session:
        second_owner = StaffUser(
            display_name="Owner 4",
            status="active",
            roles=["owner"],
            primary_role="owner",
            telegram_id=404004,
        )
        await add_tenant_members(session, second_owner)
        assert second_owner.id is not None
        existing = await session.get(
            CommunicationDelivery,
            ambiguous_delivery_id,
        )
        assert existing is not None
        session.add(
            CommunicationDelivery(
                delivery_id=sent_delivery_id,
                event_id=existing.event_id,
                channel=existing.channel,
                recipient_key=f"staff:{second_owner.id}",
                destination="404004",
                template_key=existing.template_key,
                template_version=existing.template_version,
                render_context=existing.render_context,
                status="queued",
                priority=2,
                attempts=0,
                max_attempts=existing.max_attempts,
                available_at=existing.available_at,
                created_at=existing.created_at,
                updated_at=existing.updated_at,
            )
        )
        await session.commit()
    provider = RecordingProvider(
        worker_session_factory,
        {
            "303003": ProviderDeliveryResult.transient_failure(
                category="network",
                code="timeout",
                message="Telegram request timed out",
            ),
            "404004": ProviderDeliveryResult.sent("message-4"),
        },
    )
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="test-worker",
        lease_seconds=60,
    )

    first = await worker.run_once()
    second = await worker.run_once()

    assert first.outcome == "dead"
    assert first.delivery_id == ambiguous_delivery_id
    assert second.outcome == "sent"
    assert second.delivery_id == sent_delivery_id
    async with worker_session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(CommunicationDelivery).order_by(
                        CommunicationDelivery.delivery_id
                    )
                )
            ).scalars()
        )
        assert [row.status for row in rows] == ["dead", "sent"]
        assert [row.attempts for row in rows] == [1, 1]


@pytest.mark.asyncio
async def test_worker_converts_render_error_to_permanent_dead_letter(
    worker_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    _, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=5,
        telegram_id=505005,
    )
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        # Keep the row inside the reviewed runtime allowlist while corrupting
        # its immutable payload snapshot. Unknown templates are intentionally
        # invisible to the worker and therefore cannot exercise render DLQ.
        row.render_context = {"lead_id": 5}
        session.add(row)
        await session.commit()

    provider = RecordingProvider(
        worker_session_factory,
        {"505005": ProviderDeliveryResult.sent("must-not-send")},
    )
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="test-worker",
        lease_seconds=60,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "dead"
    assert provider.calls == []
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        assert row.status == "dead"
        assert row.last_error_category == "template"
        assert row.last_error_message == "Communication template could not be rendered"
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert attempt is not None
        assert attempt.outcome == "dead"
        assert attempt.error_code == "template_render_failed"
        assert attempt.provider_latency_ms is None
        assert attempt.ambiguous is False
