from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import CommunicationDelivery, CommunicationDeliveryAttempt
from services.communications.delivery_attempt_service import (
    CommunicationDeliveryAttemptStateError,
)
from services.communications.delivery_service import (
    CommunicationDeliveryLeaseLost,
    CommunicationDeliveryService,
)
from services.communications.providers.base import ProviderDeliveryResult

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def attempt_session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'attempt.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(CommunicationDelivery.__table__.create)
        await connection.run_sync(CommunicationDeliveryAttempt.__table__.create)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _delivery(
    sequence: int,
    *,
    status: str = "queued",
    attempts: int = 0,
    worker_id: str | None = None,
    lease_token: str | None = None,
    lease_expires_at: datetime | None = None,
) -> CommunicationDelivery:
    return CommunicationDelivery(
        delivery_id=f"{sequence:032x}",
        event_id=f"{sequence + 1000:032x}",
        channel="telegram",
        recipient_key=f"staff:{sequence}",
        destination=str(100000 + sequence),
        template_key="telegram.website_contact_lead_created",
        template_version=1,
        render_context={},
        status=status,
        attempts=attempts,
        max_attempts=3,
        available_at=NOW,
        worker_id=worker_id,
        lease_token=lease_token,
        lease_expires_at=lease_expires_at,
        created_at=NOW,
        updated_at=NOW,
    )


def test_attempt_model_contains_only_pii_free_operational_fields():
    assert set(CommunicationDeliveryAttempt.__table__.columns.keys()) == {
        "delivery_id",
        "attempt_no",
        "started_at",
        "finished_at",
        "outcome",
        "error_category",
        "error_code",
        "retry_after_seconds",
        "provider_latency_ms",
        "ambiguous",
    }


@pytest.mark.asyncio
async def test_cancel_closes_current_attempt_without_provider_telemetry(
    attempt_session_factory,
):
    async with attempt_session_factory() as session:
        session.add(_delivery(1))
        await session.commit()
        claim = await CommunicationDeliveryService.claim_next(
            session,
            worker_id="worker",
            lease_seconds=60,
            now=NOW,
        )
        assert claim is not None
        await session.commit()

    async with attempt_session_factory() as session:
        await CommunicationDeliveryService.cancel_owned(
            session,
            delivery_id=claim.delivery_id,
            worker_id="worker",
            lease_token=claim.lease_token,
            now=NOW + timedelta(seconds=1),
        )
        await session.commit()
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (claim.delivery_id, 1),
        )
        assert attempt is not None
        assert attempt.outcome == "canceled"
        assert attempt.error_category == "recipient"
        assert attempt.error_code == "recipient_inactive"
        assert attempt.retry_after_seconds is None
        assert attempt.provider_latency_ms is None
        assert attempt.ambiguous is False


@pytest.mark.asyncio
async def test_attempt_history_keeps_every_retry_row(attempt_session_factory):
    async with attempt_session_factory() as session:
        session.add(_delivery(2))
        await session.commit()
        first_claim = await CommunicationDeliveryService.claim_next(
            session,
            worker_id="worker-a",
            lease_seconds=60,
            now=NOW,
        )
        assert first_claim is not None
        await session.commit()

    async with attempt_session_factory() as session:
        failure = await CommunicationDeliveryService.mark_failed(
            session,
            delivery_id=first_claim.delivery_id,
            worker_id="worker-a",
            lease_token=first_claim.lease_token,
            result=ProviderDeliveryResult.transient_failure(
                category="rate_limit",
                code="telegram_retry_after",
                message="Retry later",
                retry_after_seconds=60,
            ),
            provider_latency_ms=10,
            now=NOW + timedelta(seconds=1),
        )
        assert failure.next_attempt_at is not None
        await session.commit()

    async with attempt_session_factory() as session:
        second_claim = await CommunicationDeliveryService.claim_next(
            session,
            worker_id="worker-b",
            lease_seconds=60,
            now=failure.next_attempt_at,
        )
        assert second_claim is not None
        assert second_claim.attempts == 2
        await session.commit()

    async with attempt_session_factory() as session:
        await CommunicationDeliveryService.mark_sent(
            session,
            delivery_id=second_claim.delivery_id,
            worker_id="worker-b",
            lease_token=second_claim.lease_token,
            provider_message_id="telegram-message-2",
            provider_latency_ms=12,
            now=failure.next_attempt_at + timedelta(seconds=1),
        )
        await session.commit()
        attempts = list(
            (
                await session.execute(
                    select(CommunicationDeliveryAttempt)
                    .where(
                        CommunicationDeliveryAttempt.delivery_id
                        == second_claim.delivery_id
                    )
                    .order_by(CommunicationDeliveryAttempt.attempt_no)
                )
            ).scalars()
        )
        assert [attempt.attempt_no for attempt in attempts] == [1, 2]
        assert [attempt.outcome for attempt in attempts] == ["retry", "sent"]
        assert [attempt.provider_latency_ms for attempt in attempts] == [10, 12]


@pytest.mark.asyncio
async def test_terminal_transition_and_attempt_are_caller_owned(
    attempt_session_factory,
):
    async with attempt_session_factory() as session:
        session.add(_delivery(3))
        await session.commit()
        claim = await CommunicationDeliveryService.claim_next(
            session,
            worker_id="worker",
            lease_seconds=60,
            now=NOW,
        )
        assert claim is not None
        await session.commit()

    async with attempt_session_factory() as session:
        await CommunicationDeliveryService.mark_sent(
            session,
            delivery_id=claim.delivery_id,
            worker_id="worker",
            lease_token=claim.lease_token,
            provider_message_id="not-committed",
            provider_latency_ms=4,
            now=NOW + timedelta(seconds=1),
        )
        local_delivery = await session.get(CommunicationDelivery, claim.delivery_id)
        local_attempt = await session.get(
            CommunicationDeliveryAttempt,
            (claim.delivery_id, 1),
        )
        assert local_delivery is not None and local_delivery.status == "sent"
        assert local_attempt is not None and local_attempt.outcome == "sent"
        await session.rollback()

    async with attempt_session_factory() as session:
        delivery = await session.get(CommunicationDelivery, claim.delivery_id)
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (claim.delivery_id, 1),
        )
        assert delivery is not None and delivery.status == "running"
        assert delivery.provider_message_id is None
        assert attempt is not None and attempt.outcome == "running"
        assert attempt.finished_at is None


@pytest.mark.asyncio
async def test_terminal_fence_leaves_attempt_open_for_lease_owner(
    attempt_session_factory,
):
    async with attempt_session_factory() as session:
        session.add(_delivery(4))
        await session.commit()
        claim = await CommunicationDeliveryService.claim_next(
            session,
            worker_id="worker-a",
            lease_seconds=60,
            now=NOW,
        )
        assert claim is not None
        await session.commit()

    async with attempt_session_factory() as session:
        with pytest.raises(CommunicationDeliveryLeaseLost):
            await CommunicationDeliveryService.mark_sent(
                session,
                delivery_id=claim.delivery_id,
                worker_id="worker-b",
                lease_token=claim.lease_token,
                provider_message_id="must-not-persist",
                now=NOW + timedelta(seconds=1),
            )
        await session.rollback()

    async with attempt_session_factory() as session:
        delivery = await session.get(CommunicationDelivery, claim.delivery_id)
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (claim.delivery_id, 1),
        )
        assert delivery is not None and delivery.status == "running"
        assert delivery.worker_id == "worker-a"
        assert attempt is not None and attempt.outcome == "running"


@pytest.mark.asyncio
async def test_duplicate_next_attempt_aborts_claim_before_delivery_mutation(
    attempt_session_factory,
):
    delivery = _delivery(7)
    async with attempt_session_factory() as session:
        session.add_all(
            [
                delivery,
                CommunicationDeliveryAttempt(
                    delivery_id=delivery.delivery_id,
                    attempt_no=1,
                    started_at=NOW,
                    outcome="running",
                ),
            ]
        )
        await session.commit()
        with pytest.raises(CommunicationDeliveryAttemptStateError):
            await CommunicationDeliveryService.claim_next(
                session,
                worker_id="worker",
                lease_seconds=60,
                now=NOW,
            )
        unchanged = await session.get(CommunicationDelivery, delivery.delivery_id)
        assert unchanged is not None
        assert unchanged.status == "queued"
        assert unchanged.attempts == 0
        await session.rollback()


@pytest.mark.asyncio
async def test_missing_running_attempt_aborts_terminal_transition(
    attempt_session_factory,
):
    delivery = _delivery(
        5,
        status="running",
        attempts=1,
        worker_id="worker",
        lease_token="z" * 43,
        lease_expires_at=NOW + timedelta(minutes=1),
    )
    delivery_id = delivery.delivery_id
    async with attempt_session_factory() as session:
        session.add(delivery)
        await session.commit()
        with pytest.raises(CommunicationDeliveryAttemptStateError):
            await CommunicationDeliveryService.mark_sent(
                session,
                delivery_id=delivery_id,
                worker_id="worker",
                lease_token="z" * 43,
                provider_message_id="must-not-persist",
                now=NOW,
            )
        await session.rollback()

    async with attempt_session_factory() as session:
        unchanged = await session.get(CommunicationDelivery, delivery_id)
        assert unchanged is not None
        assert unchanged.status == "running"
        assert unchanged.provider_message_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attempt_values",
    [
        {"attempt_no": 0, "outcome": "running"},
        {"attempt_no": 1, "outcome": "sent"},
        {
            "attempt_no": 1,
            "outcome": "sent",
            "finished_at": NOW,
            "error_category": "provider",
            "error_code": "not_allowed",
        },
        {"attempt_no": 1, "outcome": "retry", "finished_at": NOW},
        {
            "attempt_no": 1,
            "outcome": "retry",
            "finished_at": NOW,
            "error_category": " ",
            "error_code": "timeout",
        },
        {
            "attempt_no": 1,
            "outcome": "sent",
            "finished_at": NOW,
            "ambiguous": True,
        },
        {"attempt_no": 1, "outcome": "running", "retry_after_seconds": 30},
        {
            "attempt_no": 1,
            "outcome": "canceled",
            "finished_at": NOW,
            "error_category": "recipient",
            "error_code": "inactive",
            "provider_latency_ms": 1,
        },
        {
            "attempt_no": 1,
            "outcome": "retry",
            "finished_at": NOW,
            "error_category": "network",
            "error_code": "timeout",
            "provider_latency_ms": -1,
        },
    ],
)
async def test_attempt_schema_rejects_invalid_lifecycle_state(
    attempt_session_factory,
    attempt_values,
):
    async with attempt_session_factory() as session:
        delivery = _delivery(6)
        session.add(delivery)
        await session.commit()
        session.add(
            CommunicationDeliveryAttempt(
                delivery_id=delivery.delivery_id,
                started_at=NOW - timedelta(seconds=1),
                **attempt_values,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
