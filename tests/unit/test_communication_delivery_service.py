from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import CommunicationDelivery
from services.communications.delivery_service import (
    CommunicationDeliveryLeaseLost,
    CommunicationDeliveryService,
)
from services.communications.providers.base import ProviderDeliveryResult


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def delivery_session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'delivery.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(CommunicationDelivery.__table__.create)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _delivery(
    sequence: int,
    *,
    status: str = "queued",
    channel: str = "telegram",
    priority: int = 100,
    attempts: int = 0,
    max_attempts: int = 3,
    available_at: datetime = NOW,
    lease_expires_at: datetime | None = None,
    worker_id: str | None = None,
    lease_token: str | None = None,
    provider_message_id: str | None = None,
) -> CommunicationDelivery:
    return CommunicationDelivery(
        delivery_id=f"{sequence:032x}",
        event_id=f"{sequence + 1000:032x}",
        channel=channel,
        recipient_key=f"staff:{sequence}",
        destination=str(100000 + sequence),
        template_key="telegram.website_contact_lead_created",
        template_version=1,
        render_context={
            "lead_id": sequence,
            "customer": {"phone": "+375291112233"},
            "items": [{"name": "private item"}],
        },
        status=status,
        priority=priority,
        attempts=attempts,
        max_attempts=max_attempts,
        available_at=available_at,
        worker_id=worker_id,
        lease_token=lease_token,
        lease_expires_at=lease_expires_at,
        provider_message_id=provider_message_id,
        created_at=NOW + timedelta(microseconds=sequence),
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_claim_next_is_due_channel_scoped_ordered_and_caller_owned(
    delivery_session_factory,
):
    async with delivery_session_factory() as session:
        session.add_all(
            [
                _delivery(1, priority=20),
                _delivery(2, priority=10),
                _delivery(3, priority=1, available_at=NOW + timedelta(minutes=1)),
                _delivery(4, channel="email", priority=1),
            ]
        )
        await session.commit()

    async with delivery_session_factory() as session:
        claim = await CommunicationDeliveryService.claim_next(
            session,
            worker_id="delivery-worker-a",
            now=NOW,
            lease_seconds=60,
        )
        assert claim is not None
        assert claim.delivery_id == f"{2:032x}"
        assert claim.attempts == 1
        assert claim.lease_expires_at == NOW + timedelta(seconds=60)
        assert len(claim.lease_token) >= 32

        independent = await session.get(CommunicationDelivery, claim.delivery_id)
        assert independent is not None
        assert independent.status == "running"
        await session.rollback()

    async with delivery_session_factory() as session:
        rolled_back = await session.get(CommunicationDelivery, f"{2:032x}")
        assert rolled_back is not None
        assert rolled_back.status == "queued"
        assert rolled_back.attempts == 0


@pytest.mark.asyncio
async def test_claim_snapshot_is_frozen_and_redacts_lease_token(
    delivery_session_factory,
):
    async with delivery_session_factory() as session:
        session.add(_delivery(1))
        await session.commit()
        claim = await CommunicationDeliveryService.claim_next(
            session,
            worker_id="worker",
            lease_seconds=60,
            now=NOW,
        )
        assert claim is not None
        assert claim.lease_token not in repr(claim)
        assert "render_context" not in repr(claim)
        assert claim.destination not in repr(claim)
        assert "+375291112233" not in repr(claim)
        legacy_shaped_key = "legacy-telegram:-100123456"
        legacy_claim = replace(claim, recipient_key=legacy_shaped_key)
        assert legacy_shaped_key not in repr(legacy_claim)
        with pytest.raises(FrozenInstanceError):
            claim.attempts = 99  # type: ignore[misc]
        with pytest.raises(TypeError):
            claim.render_context["lead_id"] = 99  # type: ignore[index]
        with pytest.raises(TypeError):
            claim.render_context["customer"]["phone"] = "changed"  # type: ignore[index]
        with pytest.raises(TypeError):
            claim.render_context["items"][0]["name"] = "changed"  # type: ignore[index]


@pytest.mark.asyncio
async def test_expired_running_is_recovered_before_it_can_be_claimed(
    delivery_session_factory,
):
    expired_token = "x" * 43
    async with delivery_session_factory() as session:
        session.add(
            _delivery(
                1,
                status="running",
                attempts=1,
                worker_id="old-worker",
                lease_token=expired_token,
                lease_expires_at=NOW - timedelta(seconds=1),
            )
        )
        await session.commit()

    async with delivery_session_factory() as session:
        claim = await CommunicationDeliveryService.claim_next(
            session,
            worker_id="new-worker",
            lease_seconds=60,
            now=NOW,
        )
        assert claim is None
        recovery = await CommunicationDeliveryService.recover_expired_leases(
            session,
            now=NOW,
        )
        await session.commit()
        assert recovery.retry_count == 1
        assert recovery.dead_count == 0

    async with delivery_session_factory() as session:
        claim = await CommunicationDeliveryService.claim_next(
            session,
            worker_id="new-worker",
            lease_seconds=60,
            now=NOW,
        )
        assert claim is None
        recovered = await session.get(CommunicationDelivery, f"{1:032x}")
        assert recovered is not None
        assert recovered.status == "retry"
        assert recovered.attempts == 1
        assert recovered.available_at > NOW.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_renew_and_terminal_transitions_require_exact_unexpired_lease(
    delivery_session_factory,
):
    async with delivery_session_factory() as session:
        session.add(_delivery(1))
        await session.commit()
        claim = await CommunicationDeliveryService.claim_next(
            session,
            worker_id="worker-a",
            lease_seconds=60,
            now=NOW,
        )
        assert claim is not None
        await session.commit()

    async with delivery_session_factory() as session:
        with pytest.raises(CommunicationDeliveryLeaseLost):
            await CommunicationDeliveryService.renew_lease(
                session,
                delivery_id=claim.delivery_id,
                worker_id="worker-b",
                lease_token=claim.lease_token,
                lease_seconds=60,
                now=NOW + timedelta(seconds=1),
            )
        await session.rollback()

    async with delivery_session_factory() as session:
        renewed_until = await CommunicationDeliveryService.renew_lease(
            session,
            delivery_id=claim.delivery_id,
            worker_id="worker-a",
            lease_token=claim.lease_token,
            lease_seconds=90,
            now=NOW + timedelta(seconds=1),
        )
        assert renewed_until == NOW + timedelta(seconds=91)
        await session.commit()

    async with delivery_session_factory() as session:
        await CommunicationDeliveryService.mark_sent(
            session,
            delivery_id=claim.delivery_id,
            worker_id="worker-a",
            lease_token=claim.lease_token,
            provider_message_id="telegram-message-42",
            now=NOW + timedelta(seconds=2),
        )
        await session.commit()

    async with delivery_session_factory() as session:
        sent = await session.get(CommunicationDelivery, claim.delivery_id)
        assert sent is not None
        assert sent.status == "sent"
        assert sent.provider_message_id == "telegram-message-42"
        assert sent.worker_id is None
        assert sent.lease_token is None
        assert sent.lease_expires_at is None
        assert sent.sent_at == NOW.replace(tzinfo=None) + timedelta(seconds=2)
        assert sent.finished_at == sent.sent_at
        with pytest.raises(CommunicationDeliveryLeaseLost):
            await CommunicationDeliveryService.cancel_owned(
                session,
                delivery_id=claim.delivery_id,
                worker_id="worker-a",
                lease_token=claim.lease_token,
                now=NOW + timedelta(seconds=3),
            )


@pytest.mark.asyncio
async def test_transient_failure_has_deterministic_backoff_and_retry_after_lower_bound(
    delivery_session_factory,
):
    async with delivery_session_factory() as session:
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

    result = ProviderDeliveryResult.transient_failure(
        category="rate_limit\nsecret",
        code="retry\tafter",
        message="Safe\nmessage",
        retry_after_seconds=900,
    )
    async with delivery_session_factory() as session:
        outcome = await CommunicationDeliveryService.mark_failed(
            session,
            delivery_id=claim.delivery_id,
            worker_id="worker",
            lease_token=claim.lease_token,
            result=result,
            now=NOW + timedelta(seconds=1),
        )
        await session.commit()
        assert outcome.status == "retry"
        assert outcome.next_attempt_at == NOW + timedelta(seconds=901)

    async with delivery_session_factory() as session:
        row = await session.get(CommunicationDelivery, claim.delivery_id)
        assert row is not None
        assert row.status == "retry"
        assert row.attempts == 1
        assert row.finished_at is None
        assert row.last_error_category == "rate_limit secret"
        assert row.last_error_code == "retry after"
        assert row.last_error_message == "Safe message"
        assert row.worker_id is None

    delay = CommunicationDeliveryService.retry_delay_seconds(
        delivery_id=claim.delivery_id,
        attempts=1,
    )
    assert 30 <= delay <= 36
    assert delay == CommunicationDeliveryService.retry_delay_seconds(
        delivery_id=claim.delivery_id,
        attempts=1,
    )
    assert (
        CommunicationDeliveryService.retry_delay_seconds(
            delivery_id=claim.delivery_id,
            attempts=30,
        )
        == 3600
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("permanent", [True, False])
async def test_permanent_or_exhausted_failure_is_dead(
    delivery_session_factory,
    permanent,
):
    max_attempts = 3
    starting_attempts = 0 if permanent else max_attempts - 1
    async with delivery_session_factory() as session:
        session.add(
                _delivery(
                    1,
                    status="queued" if permanent else "retry",
                    attempts=starting_attempts,
                    max_attempts=max_attempts,
                )
        )
        await session.commit()
        claim = await CommunicationDeliveryService.claim_next(
            session,
            worker_id="worker",
            lease_seconds=60,
            now=NOW,
        )
        assert claim is not None
        await session.commit()

    result = (
        ProviderDeliveryResult.permanent_failure(
            category="recipient",
            code="gone",
            message="Recipient is gone",
        )
        if permanent
        else ProviderDeliveryResult.transient_failure(
            category="network",
            code="timeout",
            message="Timed out",
        )
    )
    async with delivery_session_factory() as session:
        outcome = await CommunicationDeliveryService.mark_failed(
            session,
            delivery_id=claim.delivery_id,
            worker_id="worker",
            lease_token=claim.lease_token,
            result=result,
            now=NOW + timedelta(seconds=1),
        )
        await session.commit()
        assert outcome.status == "dead"
        assert outcome.next_attempt_at is None

        row = await session.get(CommunicationDelivery, claim.delivery_id)
        assert row is not None
        assert row.finished_at is not None
        assert row.worker_id is None
        assert row.lease_token is None


@pytest.mark.asyncio
async def test_recovery_is_limited_ordered_and_separates_retry_from_dead(
    delivery_session_factory,
):
    async with delivery_session_factory() as session:
        session.add_all(
            [
                _delivery(
                    1,
                    status="running",
                    attempts=1,
                    worker_id="old-a",
                    lease_token="a" * 43,
                    lease_expires_at=NOW - timedelta(seconds=3),
                ),
                _delivery(
                    2,
                    status="running",
                    attempts=3,
                    max_attempts=3,
                    worker_id="old-b",
                    lease_token="b" * 43,
                    lease_expires_at=NOW - timedelta(seconds=2),
                ),
                _delivery(
                    3,
                    status="running",
                    attempts=1,
                    worker_id="old-c",
                    lease_token="c" * 43,
                    lease_expires_at=NOW - timedelta(seconds=1),
                ),
                _delivery(
                    4,
                    status="running",
                    attempts=1,
                    worker_id="active",
                    lease_token="d" * 43,
                    lease_expires_at=NOW + timedelta(seconds=1),
                ),
            ]
        )
        await session.commit()

    async with delivery_session_factory() as session:
        outcome = await CommunicationDeliveryService.recover_expired_leases(
            session,
            now=NOW,
            limit=2,
        )
        await session.commit()
        assert outcome.retry_count == 1
        assert outcome.dead_count == 1

    async with delivery_session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(CommunicationDelivery).order_by(
                        CommunicationDelivery.delivery_id
                    )
                )
            ).scalars()
        )
        assert [row.status for row in rows] == ["retry", "dead", "running", "running"]
        assert [row.attempts for row in rows] == [1, 3, 1, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_row",
    [
        _delivery(101, status="retry", attempts=3, max_attempts=3),
        _delivery(102, attempts=1, max_attempts=3),
        _delivery(103, status="sent", attempts=1, max_attempts=3),
        _delivery(
            104,
            status="retry",
            attempts=1,
            max_attempts=3,
            provider_message_id="not-allowed-before-sent",
        ),
    ],
)
async def test_delivery_schema_rejects_nonterminal_or_provider_state_drift(
    delivery_session_factory,
    invalid_row,
):
    if invalid_row.status == "sent":
        invalid_row.sent_at = NOW
        invalid_row.finished_at = NOW
        invalid_row.provider_message_id = None

    async with delivery_session_factory() as session:
        session.add(invalid_row)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
