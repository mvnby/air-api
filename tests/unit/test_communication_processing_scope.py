from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    IntegrationOutboxEvent,
    StaffUser,
)
from services.communications.canary import CommunicationsTelegramCanary
from services.communications.delivery_service import CommunicationDeliveryService
from services.communications.dispatcher import CommunicationOutboxDispatcher
from services.communications.processing_scope import (
    ALL_EVENT_TYPES,
    ALL_TEMPLATE_KEYS,
    CANARY_EVENT_TYPES,
    CANARY_TEMPLATE_KEYS,
    STAFF_BOT_EVENT_TYPES,
    STAFF_BOT_TEMPLATE_KEYS,
    CommunicationProcessingScope,
)
from services.communications.recipient_directory import (
    OperationsCanaryRecipientDirectory,
)
from services.communications.template_registry import (
    CONTACT_LEAD_TEMPLATE_KEY,
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    INSTALLATION_ESTIMATE_TEMPLATE_KEY,
    ORDER_TEMPLATE_KEY,
    PUBLIC_CONTACT_LEAD_CREATED_EVENT,
    PUBLIC_ORDER_CREATED_EVENT,
    TELEGRAM_CANARY_REQUESTED_EVENT,
    TELEGRAM_CANARY_TEMPLATE_KEY,
    telegram_canary_event_id,
)
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_AVAILABILITY_REQUESTED_EVENT,
    TENANT_WEBSITE_AVAILABILITY_TEMPLATE_KEY,
    TENANT_WEBSITE_CHECKOUT_CREATED_EVENT,
    TENANT_WEBSITE_CHECKOUT_TEMPLATE_KEY,
    TENANT_WEBSITE_CONTACT_LEAD_CREATED_EVENT,
    TENANT_WEBSITE_CONTACT_TEMPLATE_KEY,
    TENANT_WEBSITE_REPAIR_DIAGNOSTIC_CREATED_EVENT,
    TENANT_WEBSITE_REPAIR_TEMPLATE_KEY,
)


RUN_ID_A = "123e4567-e89b-42d3-a456-426614174000"
RUN_ID_B = "123e4567-e89b-42d3-a456-426614174001"
NOW = datetime(2026, 7, 13, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
async def scope_session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scope.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _owner(name: str, telegram_id: int) -> StaffUser:
    return StaffUser(
        display_name=name,
        status="active",
        roles=["owner"],
        primary_role="owner",
        telegram_id=telegram_id,
    )


def _website_event() -> IntegrationOutboxEvent:
    return IntegrationOutboxEvent(
        event_id="f" * 32,
        event_type=PUBLIC_CONTACT_LEAD_CREATED_EVENT,
        schema_version=1,
        aggregate_type="lead",
        aggregate_id="81",
        aggregate_version=1,
        deduplication_key="scope:website:81",
        payload={
            "lead_id": 81,
            "status": "new",
            "name": "Scope test",
            "phone": "+375291112233",
            "email": None,
            "message": "Scope isolation",
        },
        priority=-20,
        max_attempts=8,
        available_at=NOW,
        occurred_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def _published_event(
    *,
    event_id: str,
    event_type: str,
    sequence: int,
) -> IntegrationOutboxEvent:
    return IntegrationOutboxEvent(
        event_id=event_id,
        event_type=event_type,
        schema_version=1,
        aggregate_type="scope-test",
        aggregate_id=str(sequence),
        deduplication_key=f"scope-delivery:{sequence}",
        payload={},
        status="published",
        priority=100,
        max_attempts=8,
        available_at=NOW,
        occurred_at=NOW,
        published_at=NOW,
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
        destination=str(1000 + sequence),
        template_key=template_key,
        template_version=1,
        render_context={},
        status=status,
        priority=priority,
        attempts=1 if running else 0,
        max_attempts=2,
        available_at=NOW,
        worker_id="old-worker" if running else None,
        lease_token="x" * 43 if running else None,
        lease_expires_at=NOW - timedelta(seconds=1) if running else None,
        created_at=NOW + timedelta(microseconds=sequence),
        updated_at=NOW,
    )


def _running_attempt(delivery: CommunicationDelivery) -> CommunicationDeliveryAttempt:
    return CommunicationDeliveryAttempt(
        delivery_id=delivery.delivery_id,
        attempt_no=1,
        started_at=NOW - timedelta(minutes=1),
        outcome="running",
    )


def test_processing_scope_factories_are_closed_immutable_allowlists():
    canary = CommunicationProcessingScope.canary(
        run_id=RUN_ID_A,
        control_revision=7,
    )
    full = CommunicationProcessingScope.all(
        control_revision=8,
        event_created_at_watermark=NOW,
    )
    staff_bot = CommunicationProcessingScope.staff_bot(control_revision=9)

    assert canary.outbox_event_types == CANARY_EVENT_TYPES
    assert canary.delivery_template_keys == CANARY_TEMPLATE_KEYS
    assert canary.exact_event_id == telegram_canary_event_id(RUN_ID_A)
    assert full.outbox_event_types == ALL_EVENT_TYPES
    assert full.delivery_template_keys == ALL_TEMPLATE_KEYS
    assert ALL_EVENT_TYPES == (
        INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
        TENANT_WEBSITE_CHECKOUT_CREATED_EVENT,
        TENANT_WEBSITE_CONTACT_LEAD_CREATED_EVENT,
        TENANT_WEBSITE_AVAILABILITY_REQUESTED_EVENT,
        TENANT_WEBSITE_REPAIR_DIAGNOSTIC_CREATED_EVENT,
    )
    assert ALL_TEMPLATE_KEYS == (
        INSTALLATION_ESTIMATE_TEMPLATE_KEY,
        TENANT_WEBSITE_CHECKOUT_TEMPLATE_KEY,
        TENANT_WEBSITE_CONTACT_TEMPLATE_KEY,
        TENANT_WEBSITE_AVAILABILITY_TEMPLATE_KEY,
        TENANT_WEBSITE_REPAIR_TEMPLATE_KEY,
    )
    assert PUBLIC_ORDER_CREATED_EVENT not in ALL_EVENT_TYPES
    assert PUBLIC_CONTACT_LEAD_CREATED_EVENT not in ALL_EVENT_TYPES
    assert TELEGRAM_CANARY_REQUESTED_EVENT not in ALL_EVENT_TYPES
    assert ORDER_TEMPLATE_KEY not in ALL_TEMPLATE_KEYS
    assert CONTACT_LEAD_TEMPLATE_KEY not in ALL_TEMPLATE_KEYS
    assert TELEGRAM_CANARY_TEMPLATE_KEY not in ALL_TEMPLATE_KEYS
    assert staff_bot.outbox_event_types == STAFF_BOT_EVENT_TYPES
    assert staff_bot.delivery_template_keys == STAFF_BOT_TEMPLATE_KEYS
    assert not set(STAFF_BOT_EVENT_TYPES).intersection(ALL_EVENT_TYPES)
    assert not set(STAFF_BOT_TEMPLATE_KEYS).intersection(ALL_TEMPLATE_KEYS)
    with pytest.raises(FrozenInstanceError):
        canary.control_revision = 9  # type: ignore[misc]


def test_all_scope_requires_an_aware_exact_utc_activation_watermark():
    with pytest.raises(ValueError, match="inconsistent"):
        CommunicationProcessingScope.all(
            control_revision=1,
            event_created_at_watermark=datetime(2026, 7, 27),
        )
    with pytest.raises(ValueError, match="normalized to UTC"):
        CommunicationProcessingScope.all(
            control_revision=1,
            event_created_at_watermark=datetime(
                2026,
                7,
                27,
                tzinfo=timezone(timedelta(hours=3)),
            ),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "mode": "unknown",
            "control_revision": 1,
            "outbox_event_types": CANARY_EVENT_TYPES,
            "delivery_template_keys": CANARY_TEMPLATE_KEYS,
        },
        {
            "mode": "canary",
            "control_revision": 1,
            "outbox_event_types": CANARY_EVENT_TYPES,
            "delivery_template_keys": CANARY_TEMPLATE_KEYS,
            "exact_event_id": telegram_canary_event_id(RUN_ID_B),
            "canary_run_id": RUN_ID_A,
        },
        {
            "mode": "all",
            "control_revision": 1,
            "outbox_event_types": CANARY_EVENT_TYPES,
            "delivery_template_keys": CANARY_TEMPLATE_KEYS,
        },
        {
            "mode": "all",
            "control_revision": -1,
            "outbox_event_types": ALL_EVENT_TYPES,
            "delivery_template_keys": ALL_TEMPLATE_KEYS,
        },
        {
            "mode": "all",
            "control_revision": "1",
            "outbox_event_types": ALL_EVENT_TYPES,
            "delivery_template_keys": ALL_TEMPLATE_KEYS,
        },
    ],
)
def test_processing_scope_rejects_ad_hoc_or_inconsistent_selectors(kwargs):
    with pytest.raises(ValueError):
        CommunicationProcessingScope(**kwargs)


def test_processing_scope_matches_the_complete_control_identity():
    scope = CommunicationProcessingScope.canary(
        run_id=RUN_ID_A,
        control_revision=3,
    )

    assert scope.matches_control(
        mode="canary",
        canary_run_id=RUN_ID_A,
        control_revision=3,
    )
    assert not scope.matches_control(
        mode="canary",
        canary_run_id=RUN_ID_A,
        control_revision=4,
    )
    assert not scope.matches_control(
        mode="canary",
        canary_run_id=RUN_ID_B,
        control_revision=3,
    )
    with pytest.raises(ValueError):
        CommunicationProcessingScope.canary(
            run_id="123e4567-e89b-12d3-a456-426614174000",
            control_revision=1,
        )


@pytest.mark.asyncio
async def test_canary_dispatch_scope_ignores_other_run_and_website_priority(
    scope_session_factory,
):
    scope_a = CommunicationProcessingScope.canary(
        run_id=RUN_ID_A,
        control_revision=1,
    )
    async with scope_session_factory() as session:
        session.add_all([_owner("Owner A", 101), _owner("Owner B", 202)])
        await session.flush()
        recipients = await OperationsCanaryRecipientDirectory.list_telegram(session)
        recipient_keys = tuple(item.recipient_key for item in recipients)
        run_a = await CommunicationsTelegramCanary.enqueue(
            session,
            run_id=RUN_ID_A,
            recipient_keys=recipient_keys,
            occurred_at=NOW,
        )
        run_b = await CommunicationsTelegramCanary.enqueue(
            session,
            run_id=RUN_ID_B,
            recipient_keys=recipient_keys,
            occurred_at=NOW - timedelta(minutes=1),
        )
        website = _website_event()
        session.add(website)
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session,
            dispatcher_id="scope-dispatcher",
            scope=scope_a,
            now=NOW,
        )
        await session.commit()

        assert outcome is not None
        assert outcome.event_id == run_a.event.event_id
        await session.refresh(run_b.event)
        await session.refresh(website)
        assert run_b.event.status == "pending"
        assert run_b.event.attempts == 0
        assert website.status == "pending"
        assert website.attempts == 0


@pytest.mark.asyncio
async def test_canary_claim_scope_ignores_other_run_and_website_priority(
    scope_session_factory,
):
    scope_a = CommunicationProcessingScope.canary(
        run_id=RUN_ID_A,
        control_revision=1,
    )
    delivery_a = _delivery(
        1,
        event_id=telegram_canary_event_id(RUN_ID_A),
        template_key=TELEGRAM_CANARY_TEMPLATE_KEY,
        status="queued",
        priority=100,
    )
    delivery_b = _delivery(
        2,
        event_id=telegram_canary_event_id(RUN_ID_B),
        template_key=TELEGRAM_CANARY_TEMPLATE_KEY,
        status="queued",
        priority=-100,
    )
    website = _delivery(
        3,
        event_id="e" * 32,
        template_key=CONTACT_LEAD_TEMPLATE_KEY,
        status="queued",
        priority=-200,
    )
    async with scope_session_factory() as session:
        session.add_all(
            [
                _published_event(
                    event_id=delivery_a.event_id,
                    event_type=TELEGRAM_CANARY_REQUESTED_EVENT,
                    sequence=1,
                ),
                _published_event(
                    event_id=delivery_b.event_id,
                    event_type=TELEGRAM_CANARY_REQUESTED_EVENT,
                    sequence=2,
                ),
                _published_event(
                    event_id=website.event_id,
                    event_type=PUBLIC_CONTACT_LEAD_CREATED_EVENT,
                    sequence=3,
                ),
                delivery_a,
                delivery_b,
                website,
            ]
        )
        await session.commit()

        claim = await CommunicationDeliveryService.claim_next(
            session,
            worker_id="scope-worker",
            scope=scope_a,
            now=NOW,
        )
        await session.commit()

        assert claim is not None
        assert claim.delivery_id == delivery_a.delivery_id
        await session.refresh(delivery_b)
        await session.refresh(website)
        assert delivery_b.status == "queued"
        assert website.status == "queued"


@pytest.mark.asyncio
async def test_canary_recovery_scope_leaves_other_expired_leases_untouched(
    scope_session_factory,
):
    scope_a = CommunicationProcessingScope.canary(
        run_id=RUN_ID_A,
        control_revision=1,
    )
    delivery_a = _delivery(
        11,
        event_id=telegram_canary_event_id(RUN_ID_A),
        template_key=TELEGRAM_CANARY_TEMPLATE_KEY,
        status="running",
        priority=100,
    )
    delivery_b = _delivery(
        12,
        event_id=telegram_canary_event_id(RUN_ID_B),
        template_key=TELEGRAM_CANARY_TEMPLATE_KEY,
        status="running",
        priority=-100,
    )
    website = _delivery(
        13,
        event_id="d" * 32,
        template_key=CONTACT_LEAD_TEMPLATE_KEY,
        status="running",
        priority=-200,
    )
    async with scope_session_factory() as session:
        session.add_all(
            [
                _published_event(
                    event_id=delivery_a.event_id,
                    event_type=TELEGRAM_CANARY_REQUESTED_EVENT,
                    sequence=11,
                ),
                _published_event(
                    event_id=delivery_b.event_id,
                    event_type=TELEGRAM_CANARY_REQUESTED_EVENT,
                    sequence=12,
                ),
                _published_event(
                    event_id=website.event_id,
                    event_type=PUBLIC_CONTACT_LEAD_CREATED_EVENT,
                    sequence=13,
                ),
                delivery_a,
                delivery_b,
                website,
            ]
        )
        session.add_all(
            [
                _running_attempt(delivery_a),
                _running_attempt(delivery_b),
                _running_attempt(website),
            ]
        )
        await session.commit()

        recovery = await CommunicationDeliveryService.recover_expired_leases(
            session,
            scope=scope_a,
            now=NOW,
        )
        await session.commit()

        assert recovery.retry_count == 1
        assert recovery.dead_count == 0
        await session.refresh(delivery_a)
        await session.refresh(delivery_b)
        await session.refresh(website)
        assert delivery_a.status == "retry"
        assert delivery_b.status == "running"
        assert website.status == "running"
