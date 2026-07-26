from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    IntegrationOutboxEvent,
)
from services.communications.delivery_service import CommunicationDeliveryService
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.template_registry import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    INSTALLATION_ESTIMATE_TEMPLATE_KEY,
    ORDER_TEMPLATE_KEY,
    PUBLIC_ORDER_CREATED_EVENT,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def session_factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'delivery-scope.sqlite3'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(IntegrationOutboxEvent.__table__.create)
        await connection.run_sync(CommunicationDelivery.__table__.create)
        await connection.run_sync(CommunicationDeliveryAttempt.__table__.create)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _scope_case(
    mode: str,
) -> tuple[CommunicationProcessingScope, str, str]:
    if mode == "all":
        return (
            CommunicationProcessingScope.all(control_revision=1),
            INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
            INSTALLATION_ESTIMATE_TEMPLATE_KEY,
        )
    scope = CommunicationProcessingScope.staff_bot(control_revision=1)
    return scope, scope.outbox_event_types[0], scope.delivery_template_keys[0]


def _event(
    *,
    event_id: str,
    event_type: str,
    status: str = "published",
) -> IntegrationOutboxEvent:
    return IntegrationOutboxEvent(
        event_id=event_id,
        event_type=event_type,
        schema_version=1,
        aggregate_type="test",
        aggregate_id=event_id,
        deduplication_key=f"scope-integrity:{event_id}",
        payload={},
        status=status,
        available_at=NOW,
        occurred_at=NOW,
        published_at=NOW if status == "published" else None,
        created_at=NOW,
        updated_at=NOW,
    )


def _delivery(
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
        destination=str(100000 + sequence),
        template_key=template_key,
        template_version=1,
        render_context={},
        status=status,
        priority=priority,
        attempts=1 if running else 0,
        max_attempts=3,
        available_at=NOW,
        worker_id="expired-worker" if running else None,
        lease_token=("x" * 43) if running else None,
        lease_expires_at=NOW - timedelta(seconds=1) if running else None,
        created_at=NOW + timedelta(microseconds=sequence),
        updated_at=NOW,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["all", "staff_bot"])
async def test_claim_requires_published_allowed_event_and_allowed_template(
    session_factory,
    mode,
):
    scope, allowed_event_type, allowed_template_key = _scope_case(mode)
    event_ids = {
        "forbidden": f"{mode}:forbidden".encode().hex().ljust(32, "0")[:32],
        "missing": f"{mode}:missing".encode().hex().ljust(32, "0")[:32],
        "unpublished": f"{mode}:pending".encode().hex().ljust(32, "0")[:32],
        "wrong_template": f"{mode}:template".encode().hex().ljust(32, "0")[:32],
        "allowed": f"{mode}:allowed".encode().hex().ljust(32, "0")[:32],
    }
    deliveries = (
        _delivery(
            1,
            event_id=event_ids["forbidden"],
            template_key=allowed_template_key,
            status="queued",
            priority=-400,
        ),
        _delivery(
            2,
            event_id=event_ids["missing"],
            template_key=allowed_template_key,
            status="queued",
            priority=-300,
        ),
        _delivery(
            3,
            event_id=event_ids["unpublished"],
            template_key=allowed_template_key,
            status="queued",
            priority=-200,
        ),
        _delivery(
            4,
            event_id=event_ids["wrong_template"],
            template_key=ORDER_TEMPLATE_KEY,
            status="queued",
            priority=-100,
        ),
        _delivery(
            5,
            event_id=event_ids["allowed"],
            template_key=allowed_template_key,
            status="queued",
            priority=100,
        ),
    )
    async with session_factory() as session:
        session.add_all(
            [
                _event(
                    event_id=event_ids["forbidden"],
                    event_type=PUBLIC_ORDER_CREATED_EVENT,
                ),
                _event(
                    event_id=event_ids["unpublished"],
                    event_type=allowed_event_type,
                    status="pending",
                ),
                _event(
                    event_id=event_ids["wrong_template"],
                    event_type=allowed_event_type,
                ),
                _event(
                    event_id=event_ids["allowed"],
                    event_type=allowed_event_type,
                ),
                *deliveries,
            ]
        )
        await session.commit()

        claim = await CommunicationDeliveryService.claim_next(
            session,
            scope=scope,
            worker_id="scope-integrity-worker",
            now=NOW,
        )
        await session.commit()

        assert claim is not None
        assert claim.delivery_id == deliveries[-1].delivery_id
        for excluded in deliveries[:-1]:
            await session.refresh(excluded)
            assert excluded.status == "queued"
            assert excluded.attempts == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["all", "staff_bot"])
async def test_recovery_requires_published_allowed_event_and_allowed_template(
    session_factory,
    mode,
):
    scope, allowed_event_type, allowed_template_key = _scope_case(mode)
    event_ids = {
        "forbidden": f"{mode}:r-forbidden".encode().hex().ljust(32, "0")[:32],
        "missing": f"{mode}:r-missing".encode().hex().ljust(32, "0")[:32],
        "unpublished": f"{mode}:r-dead".encode().hex().ljust(32, "0")[:32],
        "wrong_template": f"{mode}:r-template".encode().hex().ljust(32, "0")[:32],
        "allowed": f"{mode}:r-allowed".encode().hex().ljust(32, "0")[:32],
    }
    deliveries = tuple(
        _delivery(
            sequence,
            event_id=event_ids[key],
            template_key=(
                ORDER_TEMPLATE_KEY if key == "wrong_template" else allowed_template_key
            ),
            status="running",
            priority=priority,
        )
        for sequence, key, priority in (
            (11, "forbidden", -400),
            (12, "missing", -300),
            (13, "unpublished", -200),
            (14, "wrong_template", -100),
            (15, "allowed", 100),
        )
    )
    async with session_factory() as session:
        session.add_all(
            [
                _event(
                    event_id=event_ids["forbidden"],
                    event_type=PUBLIC_ORDER_CREATED_EVENT,
                ),
                _event(
                    event_id=event_ids["unpublished"],
                    event_type=allowed_event_type,
                    status="dead",
                ),
                _event(
                    event_id=event_ids["wrong_template"],
                    event_type=allowed_event_type,
                ),
                _event(
                    event_id=event_ids["allowed"],
                    event_type=allowed_event_type,
                ),
                *deliveries,
                *[
                    CommunicationDeliveryAttempt(
                        delivery_id=delivery.delivery_id,
                        attempt_no=1,
                        started_at=NOW - timedelta(minutes=1),
                        outcome="running",
                    )
                    for delivery in deliveries
                ],
            ]
        )
        await session.commit()

        recovered = await CommunicationDeliveryService.recover_expired_leases(
            session,
            scope=scope,
            now=NOW,
        )
        await session.commit()

        assert recovered.retry_count == 1
        assert recovered.dead_count == 0
        await session.refresh(deliveries[-1])
        assert deliveries[-1].status == "retry"
        for excluded in deliveries[:-1]:
            await session.refresh(excluded)
            assert excluded.status == "running"
            assert excluded.worker_id == "expired-worker"
