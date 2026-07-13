from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import CommunicationDelivery, CommunicationDeliveryAttempt
from services.communications.delivery_service import (
    CommunicationDeliveryLeaseLost,
    CommunicationDeliveryService,
)
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.providers.base import ProviderDeliveryResult
from services.communications.template_registry import (
    CONTACT_LEAD_TEMPLATE_KEY,
    TELEGRAM_CANARY_TEMPLATE_KEY,
    telegram_canary_event_id,
)

ALL_SCOPE = CommunicationProcessingScope.all(control_revision=0)
RUN_ID_A = "123e4567-e89b-42d3-a456-426614174000"
RUN_ID_B = "123e4567-e89b-42d3-a456-426614174001"


@pytest.fixture
async def communication_db_engine():
    database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    assert database_url
    assert "test" in database_url.lower() or environment == "test"
    schema_name = f"communication_c1_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))

    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(CommunicationDelivery.__table__.create)
        await connection.run_sync(CommunicationDeliveryAttempt.__table__.create)
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        await admin_engine.dispose()


async def _seed_deliveries(
    communication_db_engine,
    count: int,
    *,
    expired: bool = False,
) -> None:
    factory = sessionmaker(
        communication_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    now = datetime.now(timezone.utc)
    async with factory() as session:
        for sequence in range(1, count + 1):
            running_values = (
                {
                    "status": "running",
                    "attempts": 1,
                    "worker_id": f"expired-worker-{sequence}",
                    "lease_token": f"expired-token-{sequence}".ljust(40, "x"),
                    "lease_expires_at": now - timedelta(seconds=count - sequence + 1),
                }
                if expired
                else {
                    "status": "queued",
                    "attempts": 0,
                    "worker_id": None,
                    "lease_token": None,
                    "lease_expires_at": None,
                }
            )
            session.add(
                CommunicationDelivery(
                    delivery_id=f"{sequence:032x}",
                    event_id=f"{sequence + 1000:032x}",
                    channel="telegram",
                    recipient_key=f"staff:{sequence}",
                    destination=str(100000 + sequence),
                    template_key="telegram.website_contact_lead_created",
                    template_version=1,
                    render_context={"lead_id": sequence},
                    priority=100,
                    max_attempts=3,
                    available_at=now - timedelta(seconds=1),
                    created_at=now + timedelta(microseconds=sequence),
                    updated_at=now,
                    **running_values,
                )
            )
            if expired:
                session.add(
                    CommunicationDeliveryAttempt(
                        delivery_id=f"{sequence:032x}",
                        attempt_no=1,
                        started_at=now - timedelta(minutes=1),
                        outcome="running",
                    )
                )
        await session.commit()


@pytest.mark.asyncio
async def test_postgres_claim_skips_locked_row_and_claims_distinct_delivery(
    communication_db_engine,
):
    assert communication_db_engine.dialect.name == "postgresql"
    await _seed_deliveries(communication_db_engine, 2)
    factory = sessionmaker(
        communication_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with factory() as session_a, factory() as session_b:
        claim_a = await CommunicationDeliveryService.claim_next(
            session_a,
            scope=ALL_SCOPE,
            worker_id="worker-a",
            lease_seconds=60,
        )
        assert claim_a is not None

        claim_b = await asyncio.wait_for(
            CommunicationDeliveryService.claim_next(
                session_b,
                scope=ALL_SCOPE,
                worker_id="worker-b",
                lease_seconds=60,
            ),
            timeout=3,
        )
        assert claim_b is not None
        assert claim_b.delivery_id != claim_a.delivery_id
        assert claim_b.lease_token != claim_a.lease_token
        await session_b.commit()
        await session_a.commit()

    async with factory() as verification:
        rows = [
            await verification.get(CommunicationDelivery, f"{sequence:032x}")
            for sequence in (1, 2)
        ]
        assert all(row is not None and row.status == "running" for row in rows)
        assert [row.attempts for row in rows if row is not None] == [1, 1]
        attempts = [
            await verification.get(
                CommunicationDeliveryAttempt,
                (f"{sequence:032x}", 1),
            )
            for sequence in (1, 2)
        ]
        assert all(
            attempt is not None and attempt.outcome == "running"
            for attempt in attempts
        )


@pytest.mark.asyncio
async def test_postgres_locked_single_claim_rolls_back_without_consuming_attempt(
    communication_db_engine,
):
    assert communication_db_engine.dialect.name == "postgresql"
    await _seed_deliveries(communication_db_engine, 1)
    factory = sessionmaker(
        communication_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with factory() as session_a, factory() as session_b:
        claim_a = await CommunicationDeliveryService.claim_next(
            session_a,
            scope=ALL_SCOPE,
            worker_id="worker-a",
            lease_seconds=60,
        )
        assert claim_a is not None
        claim_while_locked = await asyncio.wait_for(
            CommunicationDeliveryService.claim_next(
                session_b,
                scope=ALL_SCOPE,
                worker_id="worker-b",
                lease_seconds=60,
            ),
            timeout=3,
        )
        assert claim_while_locked is None
        await session_b.rollback()
        await session_a.rollback()

        claim_after_rollback = await CommunicationDeliveryService.claim_next(
            session_b,
            scope=ALL_SCOPE,
            worker_id="worker-b",
            lease_seconds=60,
        )
        assert claim_after_rollback is not None
        assert claim_after_rollback.delivery_id == claim_a.delivery_id
        assert claim_after_rollback.attempts == 1
        assert claim_after_rollback.lease_token != claim_a.lease_token
        await session_b.commit()

    async with factory() as verification:
        attempt = await verification.get(
            CommunicationDeliveryAttempt,
            (claim_a.delivery_id, 1),
        )
        assert attempt is not None
        assert attempt.outcome == "running"


@pytest.mark.asyncio
async def test_postgres_concurrent_recovery_skips_locked_expired_delivery(
    communication_db_engine,
):
    assert communication_db_engine.dialect.name == "postgresql"
    await _seed_deliveries(communication_db_engine, 2, expired=True)
    factory = sessionmaker(
        communication_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with factory() as session_a, factory() as session_b:
        recovery_a = await CommunicationDeliveryService.recover_expired_leases(
            session_a,
            scope=ALL_SCOPE,
            limit=1,
        )
        recovery_b = await asyncio.wait_for(
            CommunicationDeliveryService.recover_expired_leases(
                session_b,
                scope=ALL_SCOPE,
                limit=1,
            ),
            timeout=3,
        )
        assert recovery_a.retry_count == 1
        assert recovery_b.retry_count == 1
        await session_b.commit()
        await session_a.commit()

    async with factory() as verification:
        rows = [
            await verification.get(CommunicationDelivery, f"{sequence:032x}")
            for sequence in (1, 2)
        ]
        assert all(row is not None and row.status == "retry" for row in rows)
        assert [row.attempts for row in rows if row is not None] == [1, 1]
        attempts = [
            await verification.get(
                CommunicationDeliveryAttempt,
                (f"{sequence:032x}", 1),
            )
            for sequence in (1, 2)
        ]
        assert all(
            attempt is not None
            and attempt.outcome == "retry"
            and attempt.error_code == "lease_expired"
            and attempt.ambiguous is True
            for attempt in attempts
        )


@pytest.mark.asyncio
async def test_postgres_canary_scope_isolates_claim_and_recovery_mixed_queue(
    communication_db_engine,
):
    assert communication_db_engine.dialect.name == "postgresql"
    scope_a = CommunicationProcessingScope.canary(
        run_id=RUN_ID_A,
        control_revision=11,
    )
    factory = sessionmaker(
        communication_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    now = datetime.now(timezone.utc)

    def delivery(
        sequence: int,
        *,
        event_id: str,
        template_key: str,
        status: str,
        priority: int,
    ) -> CommunicationDelivery:
        running = status == "running"
        return CommunicationDelivery(
            delivery_id=f"{sequence:032x}",
            event_id=event_id,
            channel="telegram",
            recipient_key=f"staff:{sequence}",
            destination=str(200000 + sequence),
            template_key=template_key,
            template_version=1,
            render_context={},
            status=status,
            priority=priority,
            attempts=1 if running else 0,
            max_attempts=3,
            available_at=now - timedelta(seconds=1),
            worker_id="expired-worker" if running else None,
            lease_token="x" * 43 if running else None,
            lease_expires_at=now - timedelta(seconds=1) if running else None,
            created_at=now + timedelta(microseconds=sequence),
            updated_at=now,
        )

    queued_a = delivery(
        101,
        event_id=telegram_canary_event_id(RUN_ID_A),
        template_key=TELEGRAM_CANARY_TEMPLATE_KEY,
        status="queued",
        priority=100,
    )
    queued_b = delivery(
        102,
        event_id=telegram_canary_event_id(RUN_ID_B),
        template_key=TELEGRAM_CANARY_TEMPLATE_KEY,
        status="queued",
        priority=-100,
    )
    queued_website = delivery(
        103,
        event_id="a" * 32,
        template_key=CONTACT_LEAD_TEMPLATE_KEY,
        status="queued",
        priority=-200,
    )
    running_a = delivery(
        111,
        event_id=telegram_canary_event_id(RUN_ID_A),
        template_key=TELEGRAM_CANARY_TEMPLATE_KEY,
        status="running",
        priority=100,
    )
    running_b = delivery(
        112,
        event_id=telegram_canary_event_id(RUN_ID_B),
        template_key=TELEGRAM_CANARY_TEMPLATE_KEY,
        status="running",
        priority=-100,
    )
    running_website = delivery(
        113,
        event_id="b" * 32,
        template_key=CONTACT_LEAD_TEMPLATE_KEY,
        status="running",
        priority=-200,
    )
    async with factory() as session:
        session.add_all(
            [
                queued_a,
                queued_b,
                queued_website,
                running_a,
                running_b,
                running_website,
            ]
        )
        session.add_all(
            [
                CommunicationDeliveryAttempt(
                    delivery_id=item.delivery_id,
                    attempt_no=1,
                    started_at=now - timedelta(minutes=1),
                    outcome="running",
                )
                for item in (running_a, running_b, running_website)
            ]
        )
        await session.commit()

        claim = await CommunicationDeliveryService.claim_next(
            session,
            scope=scope_a,
            worker_id="canary-a-worker",
            now=now,
        )
        recovery = await CommunicationDeliveryService.recover_expired_leases(
            session,
            scope=scope_a,
            now=now,
        )
        await session.commit()

        assert claim is not None
        assert claim.delivery_id == queued_a.delivery_id
        assert recovery.retry_count == 1
        assert recovery.dead_count == 0
        for untouched in (queued_b, queued_website):
            await session.refresh(untouched)
            assert untouched.status == "queued"
            assert untouched.attempts == 0
        await session.refresh(running_a)
        assert running_a.status == "retry"
        for untouched in (running_b, running_website):
            await session.refresh(untouched)
            assert untouched.status == "running"
            assert untouched.worker_id == "expired-worker"


@pytest.mark.asyncio
async def test_postgres_recovery_rotates_token_and_fences_stale_attempt(
    communication_db_engine,
):
    assert communication_db_engine.dialect.name == "postgresql"
    await _seed_deliveries(communication_db_engine, 1, expired=True)
    factory = sessionmaker(
        communication_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    stale_worker = "expired-worker-1"
    stale_token = "expired-token-1".ljust(40, "x")

    async with factory() as session:
        recovery = await CommunicationDeliveryService.recover_expired_leases(session, scope=ALL_SCOPE)
        assert recovery.retry_count == 1
        await session.commit()
        recovered = await session.get(CommunicationDelivery, f"{1:032x}")
        assert recovered is not None
        retry_at = recovered.available_at

    async with factory() as session:
        claim = await CommunicationDeliveryService.claim_next(
            session,
            scope=ALL_SCOPE,
            worker_id=stale_worker,
            lease_seconds=60,
            now=retry_at,
        )
        assert claim is not None
        assert claim.lease_token != stale_token
        assert claim.attempts == 2
        await session.commit()

    async with factory() as session:
        with pytest.raises(CommunicationDeliveryLeaseLost):
            await CommunicationDeliveryService.mark_sent(
                session,
                delivery_id=claim.delivery_id,
                worker_id=stale_worker,
                lease_token=stale_token,
                provider_message_id="stale-message",
                now=retry_at + timedelta(seconds=1),
            )
        await session.rollback()

    async with factory() as session:
        await CommunicationDeliveryService.mark_sent(
            session,
            delivery_id=claim.delivery_id,
            worker_id=stale_worker,
            lease_token=claim.lease_token,
            provider_message_id="current-message",
            now=retry_at + timedelta(seconds=1),
        )
        await session.commit()
        attempts = [
            await session.get(
                CommunicationDeliveryAttempt,
                (claim.delivery_id, attempt_no),
            )
            for attempt_no in (1, 2)
        ]
        assert [attempt.outcome for attempt in attempts if attempt is not None] == [
            "retry",
            "sent",
        ]
        assert attempts[0] is not None and attempts[0].ambiguous is True


@pytest.mark.asyncio
async def test_postgres_concurrent_terminal_transitions_have_single_winner(
    communication_db_engine,
):
    assert communication_db_engine.dialect.name == "postgresql"
    await _seed_deliveries(communication_db_engine, 1)
    factory = sessionmaker(
        communication_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        claim = await CommunicationDeliveryService.claim_next(
            session,
            scope=ALL_SCOPE,
            worker_id="terminal-worker",
            lease_seconds=60,
        )
        assert claim is not None
        await session.commit()

    barrier = asyncio.Barrier(2)

    async def mark_sent():
        async with factory() as session:
            await barrier.wait()
            try:
                await CommunicationDeliveryService.mark_sent(
                    session,
                    delivery_id=claim.delivery_id,
                    worker_id="terminal-worker",
                    lease_token=claim.lease_token,
                    provider_message_id="winner-message",
                )
                await session.commit()
                return "sent"
            except Exception:
                await session.rollback()
                raise

    async def mark_dead():
        async with factory() as session:
            await barrier.wait()
            try:
                await CommunicationDeliveryService.mark_failed(
                    session,
                    delivery_id=claim.delivery_id,
                    worker_id="terminal-worker",
                    lease_token=claim.lease_token,
                    result=ProviderDeliveryResult.permanent_failure(
                        category="recipient",
                        code="gone",
                        message="Recipient is gone",
                    ),
                )
                await session.commit()
                return "dead"
            except Exception:
                await session.rollback()
                raise

    results = await asyncio.wait_for(
        asyncio.gather(mark_sent(), mark_dead(), return_exceptions=True),
        timeout=5,
    )
    winners = [result for result in results if isinstance(result, str)]
    losers = [result for result in results if isinstance(result, BaseException)]
    assert len(winners) == 1
    assert len(losers) == 1
    assert isinstance(losers[0], CommunicationDeliveryLeaseLost)

    async with factory() as verification:
        row = await verification.get(CommunicationDelivery, claim.delivery_id)
        assert row is not None
        assert row.status in {"sent", "dead"}
        assert row.worker_id is None
        assert row.lease_token is None
        assert row.lease_expires_at is None
        attempt = await verification.get(
            CommunicationDeliveryAttempt,
            (claim.delivery_id, 1),
        )
        assert attempt is not None
        assert attempt.outcome == row.status
        assert attempt.finished_at is not None
