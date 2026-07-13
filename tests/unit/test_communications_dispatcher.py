from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from core.config import settings
from models import (
    CommunicationDelivery,
    ConsumerInbox,
    IntegrationOutboxEvent,
    StaffUser,
)
from services.communications.contracts import (
    CommunicationRecipientV1,
    CommunicationTemplatePlanV1,
    PublicContactLeadCreatedPayloadV1,
)
from services.communications.delivery_materializer import CommunicationDeliveryMaterializer
from services.communications.dispatcher import CommunicationOutboxDispatcher
from services.communications.template_registry import (
    CONSUMER_NAME,
    CONTACT_LEAD_TEMPLATE_KEY,
    WebsiteTemplateRegistry,
)


@pytest.fixture
async def communications_session_factory(tmp_path):
    database_path = tmp_path / "communications.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _lead_payload(*, lead_id: int = 12, message: str = "Нужна консультация"):
    return PublicContactLeadCreatedPayloadV1(
        lead_id=lead_id,
        status="new",
        name="Иван <b>не HTML</b>",
        phone="+375291112233",
        email="ivan@example.com",
        message=message,
    ).model_dump(mode="json")


def _event(
    sequence: int,
    *,
    event_type: str = "crm.public_contact_lead.created",
    payload: dict | None = None,
    now: datetime | None = None,
    priority: int = 100,
    max_attempts: int = 8,
) -> IntegrationOutboxEvent:
    occurred_at = now or datetime.now(timezone.utc)
    return IntegrationOutboxEvent(
        event_id=f"{sequence:032x}",
        event_type=event_type,
        schema_version=1,
        aggregate_type="lead",
        aggregate_id=str(sequence),
        aggregate_version=1,
        deduplication_key=f"test:{sequence}",
        payload=payload if payload is not None else _lead_payload(lead_id=sequence),
        priority=priority,
        max_attempts=max_attempts,
        available_at=occurred_at,
        occurred_at=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _owner(telegram_id: int, *, status: str = "active", name: str = "Owner"):
    return StaffUser(
        display_name=name,
        status=status,
        roles=["owner"],
        primary_role="owner",
        telegram_id=telegram_id,
    )


@pytest.mark.asyncio
async def test_dispatch_materializes_deliveries_inbox_and_published_atomically(
    communications_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    dispatch_time = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    async with communications_session_factory() as session:
        event = _event(21, now=dispatch_time)
        event_id = event.event_id
        session.add_all([event, _owner(101), _owner(202, name="Second")])
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session,
            dispatcher_id="dispatcher-a",
            now=dispatch_time,
        )

        assert outcome is not None
        assert outcome.outcome == "materialized"
        assert outcome.delivery_count == 2
        assert event.status == "published"
        assert event.attempts == 1
        assert await session.get(ConsumerInbox, (CONSUMER_NAME, event.event_id))
        deliveries = list(
            (
                await session.execute(
                    select(CommunicationDelivery).order_by(
                        CommunicationDelivery.recipient_key
                    )
                )
            ).scalars()
        )
        assert [delivery.destination for delivery in deliveries] == ["101", "202"]
        await session.rollback()

    async with communications_session_factory() as verification_session:
        stored_event = await verification_session.get(
            IntegrationOutboxEvent, event_id
        )
        assert stored_event is not None
        assert stored_event.status == "pending"
        assert stored_event.attempts == 0
        assert (
            await verification_session.execute(
                select(func.count(CommunicationDelivery.delivery_id))
            )
        ).scalar_one() == 0
        assert await verification_session.get(
            ConsumerInbox, (CONSUMER_NAME, event_id)
        ) is None


@pytest.mark.asyncio
async def test_dispatch_ignores_unsupported_events_and_respects_priority(
    communications_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "700", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    async with communications_session_factory() as session:
        unsupported = _event(30, event_type="catalog.product.changed", now=now)
        low_priority = _event(31, now=now - timedelta(minutes=1), priority=100)
        high_priority = _event(32, now=now, priority=10)
        session.add_all([unsupported, low_priority, high_priority])
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session, dispatcher_id="dispatcher-a", now=now
        )
        await session.commit()

        assert outcome is not None
        assert outcome.event_id == high_priority.event_id
        assert unsupported.status == "pending"
        assert unsupported.attempts == 0
        assert low_priority.status == "pending"


@pytest.mark.asyncio
async def test_dispatch_retries_or_dead_letters_when_management_audience_is_empty(
    communications_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    async with communications_session_factory() as session:
        retry_event = _event(41, now=now, max_attempts=2)
        session.add(retry_event)
        await session.commit()

        retry = await CommunicationOutboxDispatcher.dispatch_next(
            session, dispatcher_id="dispatcher-a", now=now
        )
        await session.commit()

        assert retry is not None
        assert retry.outcome == "retry_scheduled"
        assert retry.next_attempt_at is not None
        assert retry_event.status == "pending"
        assert retry_event.last_error_code == "NoEligibleCommunicationRecipients"
        assert await session.get(
            ConsumerInbox, (CONSUMER_NAME, retry_event.event_id)
        ) is None

        dead = await CommunicationOutboxDispatcher.dispatch_next(
            session,
            dispatcher_id="dispatcher-a",
            now=retry.next_attempt_at,
        )
        await session.commit()

        assert dead is not None
        assert dead.outcome == "dead"
        assert retry_event.status == "dead"
        assert retry_event.attempts == 2


@pytest.mark.asyncio
async def test_retry_and_dead_state_remain_owned_by_outer_transaction(
    communications_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    async with communications_session_factory() as session:
        retry_event = _event(42, now=now, max_attempts=2)
        dead_event = _event(43, payload={"lead_id": 43}, now=now)
        session.add_all([retry_event, dead_event])
        await session.commit()

        retry = await CommunicationOutboxDispatcher.dispatch_next(
            session, dispatcher_id="dispatcher-a", now=now
        )
        assert retry is not None and retry.outcome == "retry_scheduled"
        await session.rollback()
        await session.refresh(retry_event)
        assert retry_event.status == "pending"
        assert retry_event.attempts == 0
        assert retry_event.last_error_code is None

        # Move the retryable event out of the selection window so the invalid
        # payload is deterministically selected next.
        retry_event.available_at = now + timedelta(days=1)
        await session.commit()
        dead = await CommunicationOutboxDispatcher.dispatch_next(
            session, dispatcher_id="dispatcher-a", now=now
        )
        assert dead is not None and dead.outcome == "dead"
        await session.rollback()
        await session.refresh(dead_event)
        assert dead_event.status == "pending"
        assert dead_event.attempts == 0
        assert dead_event.last_error_code is None


def test_retry_backoff_is_deterministic_growing_and_capped():
    event_id = f"{99:032x}"
    first = CommunicationOutboxDispatcher._retry_delay(
        event_id=event_id, attempts=1
    )
    repeated = CommunicationOutboxDispatcher._retry_delay(
        event_id=event_id, attempts=1
    )
    later = CommunicationOutboxDispatcher._retry_delay(
        event_id=event_id, attempts=5
    )
    capped = CommunicationOutboxDispatcher._retry_delay(
        event_id=event_id, attempts=100
    )

    assert first == repeated
    assert later > first
    assert capped.total_seconds() == CommunicationOutboxDispatcher._RETRY_MAX_SECONDS


@pytest.mark.asyncio
async def test_dispatch_marks_invalid_supported_payload_dead_without_deliveries(
    communications_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "700", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    async with communications_session_factory() as session:
        event = _event(51, payload={"lead_id": 51}, now=now)
        session.add(event)
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session, dispatcher_id="dispatcher-a", now=now
        )
        await session.commit()

        assert outcome is not None
        assert outcome.outcome == "dead"
        assert event.status == "dead"
        assert event.last_error_code == "InvalidCommunicationEventPayload"
        assert (
            await session.execute(select(func.count(CommunicationDelivery.delivery_id)))
        ).scalar_one() == 0


@pytest.mark.asyncio
async def test_dispatch_marks_inconsistent_inbox_dead_instead_of_poisoning_queue(
    communications_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "700", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    async with communications_session_factory() as session:
        event = _event(52, now=now)
        session.add(event)
        session.add(
            ConsumerInbox(
                consumer_name=CONSUMER_NAME,
                event_id=event.event_id,
                handler_version=1,
                received_at=now,
                processed_at=now,
            )
        )
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session, dispatcher_id="dispatcher-a", now=now
        )
        await session.commit()

        assert outcome is not None
        assert outcome.outcome == "dead"
        assert event.status == "dead"
        assert event.last_error_code == "ConsumerInboxConsistencyError"


@pytest.mark.asyncio
async def test_dispatch_rejects_invalid_id_and_ignores_future_event(
    communications_session_factory,
):
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    async with communications_session_factory() as session:
        future_event = _event(53, now=now + timedelta(minutes=1))
        session.add(future_event)
        await session.commit()

        with pytest.raises(ValueError, match="required"):
            await CommunicationOutboxDispatcher.dispatch_next(
                session, dispatcher_id="", now=now
            )
        with pytest.raises(ValueError, match="too long"):
            await CommunicationOutboxDispatcher.dispatch_next(
                session, dispatcher_id="x" * 129, now=now
            )
        assert (
            await CommunicationOutboxDispatcher.dispatch_next(
                session, dispatcher_id="dispatcher-a", now=now
            )
            is None
        )
        assert future_event.status == "pending"
        assert future_event.attempts == 0


@pytest.mark.asyncio
async def test_dispatch_marks_supported_future_schema_dead(
    communications_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "700", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    async with communications_session_factory() as session:
        event = _event(54, now=now)
        event.schema_version = 2
        session.add(event)
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session, dispatcher_id="dispatcher-a", now=now
        )
        await session.commit()

        assert outcome is not None
        assert outcome.outcome == "dead"
        assert event.last_error_code == "UnsupportedCommunicationEvent"


@pytest.mark.asyncio
async def test_dispatch_materializer_conflict_rolls_back_new_recipient_savepoint(
    communications_session_factory,
    monkeypatch,
):
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    event = _event(55, now=now)
    plan = WebsiteTemplateRegistry.plan(event)
    existing_recipients = [
        CommunicationRecipientV1(
            recipient_key=f"legacy-telegram:{destination}",
            destination=destination,
            source="legacy",
        )
        for destination in ("700", "701")
    ]
    async with communications_session_factory() as session:
        session.add(event)
        await session.flush()
        await CommunicationDeliveryMaterializer.materialize(
            session,
            event=event,
            plan=plan,
            recipients=existing_recipients,
            now=now,
        )
        await session.commit()
        monkeypatch.setattr(settings, "ADMIN_IDS", "700,702", raising=False)
        monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session, dispatcher_id="dispatcher-a", now=now
        )
        await session.commit()

        assert outcome is not None
        assert outcome.outcome == "dead"
        assert event.last_error_code == "DeliveryMaterializationConflict"
        destinations = list(
            (
                await session.execute(
                    select(CommunicationDelivery.destination).order_by(
                        CommunicationDelivery.destination
                    )
                )
            ).scalars()
        )
        assert destinations == ["700", "701"]


@pytest.mark.asyncio
async def test_dispatch_recovers_existing_inbox_without_duplicate_delivery(
    communications_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "700", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    async with communications_session_factory() as session:
        event = _event(61, now=now)
        plan = CommunicationTemplatePlanV1(
            template_key=CONTACT_LEAD_TEMPLATE_KEY,
            render_context=event.payload,
        )
        recipient = CommunicationRecipientV1(
            recipient_key="legacy-telegram:700",
            destination="700",
            source="legacy",
        )
        session.add(event)
        await session.flush()
        await CommunicationDeliveryMaterializer.materialize(
            session,
            event=event,
            plan=plan,
            recipients=[recipient],
            now=now,
        )
        session.add(
            ConsumerInbox(
                consumer_name=CONSUMER_NAME,
                event_id=event.event_id,
                handler_version=1,
                received_at=now,
                processed_at=now,
            )
        )
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session, dispatcher_id="dispatcher-a", now=now
        )
        await session.commit()

        assert outcome is not None
        assert outcome.outcome == "already_materialized"
        assert outcome.delivery_count == 1
        assert event.status == "published"
        assert (
            await session.execute(select(func.count(CommunicationDelivery.delivery_id)))
        ).scalar_one() == 1
