from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import (
    CommunicationDelivery,
    ConsumerInbox,
    IntegrationOutboxEvent,
    StaffUser,
)
from services.communications.contracts import CommunicationRecipientV1
from services.communications.delivery_materializer import (
    CommunicationDeliveryMaterializer,
)
from services.communications.dispatcher import CommunicationOutboxDispatcher
from services.communications.template_registry import WebsiteTemplateRegistry


def _event(sequence: int, *, now: datetime) -> IntegrationOutboxEvent:
    return IntegrationOutboxEvent(
        event_id=f"{sequence:032x}",
        event_type="crm.public_contact_lead.created",
        schema_version=1,
        aggregate_type="lead",
        aggregate_id=str(sequence),
        aggregate_version=1,
        deduplication_key=f"dispatcher-concurrency:{sequence}",
        payload={
            "lead_id": sequence,
            "status": "new",
            "name": f"Клиент {sequence}",
            "phone": "+375291112233",
            "email": None,
            "address": None,
            "message": "Нужна консультация",
        },
        available_at=now,
        occurred_at=now,
        created_at=now,
        updated_at=now,
    )


async def _dispatch_once(factory, barrier: asyncio.Barrier, worker: str, now: datetime):
    async with factory() as session:
        await barrier.wait()
        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session,
            dispatcher_id=worker,
            now=now,
        )
        await session.commit()
        return outcome


async def _materialize_once(
    factory,
    barrier: asyncio.Barrier,
    event_id: str,
    now: datetime,
):
    async with factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        assert event is not None
        plan = WebsiteTemplateRegistry.plan(event)
        recipient = CommunicationRecipientV1(
            recipient_key="legacy-telegram:9001",
            destination="9001",
            source="legacy",
        )
        await barrier.wait()
        result = await CommunicationDeliveryMaterializer.materialize(
            session,
            event=event,
            plan=plan,
            recipients=[recipient],
            now=now,
        )
        await session.commit()
        return result


@pytest.mark.asyncio
async def test_postgres_concurrent_dispatchers_materialize_one_event_once(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    event = _event(701, now=now)
    async with factory() as setup_session:
        setup_session.add_all(
            [
                event,
                StaffUser(
                    display_name="Owner",
                    status="active",
                    roles=["owner"],
                    primary_role="owner",
                    telegram_id=7001,
                ),
            ]
        )
        await setup_session.commit()

    barrier = asyncio.Barrier(2)
    outcomes = await asyncio.gather(
        _dispatch_once(factory, barrier, "dispatcher-a", now),
        _dispatch_once(factory, barrier, "dispatcher-b", now),
    )

    materialized = [outcome for outcome in outcomes if outcome is not None]
    assert len(materialized) == 1
    assert materialized[0].event_id == event.event_id
    assert materialized[0].delivery_count == 1

    async with factory() as verification_session:
        stored_event = await verification_session.get(
            IntegrationOutboxEvent, event.event_id
        )
        assert stored_event is not None
        assert stored_event.status == "published"
        assert stored_event.attempts == 1
        assert (
            await verification_session.execute(
                select(func.count(CommunicationDelivery.delivery_id))
            )
        ).scalar_one() == 1
        assert (
            await verification_session.execute(
                select(func.count(ConsumerInbox.event_id))
            )
        ).scalar_one() == 1


@pytest.mark.asyncio
async def test_postgres_concurrent_dispatchers_skip_locked_to_distinct_events(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    events = [_event(711, now=now), _event(712, now=now)]
    async with factory() as setup_session:
        setup_session.add_all(
            [
                *events,
                StaffUser(
                    display_name="Owner",
                    status="active",
                    roles=["owner"],
                    primary_role="owner",
                    telegram_id=7002,
                ),
            ]
        )
        await setup_session.commit()

    barrier = asyncio.Barrier(2)
    outcomes = await asyncio.gather(
        _dispatch_once(factory, barrier, "dispatcher-a", now),
        _dispatch_once(factory, barrier, "dispatcher-b", now),
    )

    assert all(outcome is not None for outcome in outcomes)
    assert {outcome.event_id for outcome in outcomes if outcome is not None} == {
        event.event_id for event in events
    }
    async with factory() as verification_session:
        assert (
            await verification_session.execute(
                select(func.count(CommunicationDelivery.delivery_id))
            )
        ).scalar_one() == 2
        assert (
            await verification_session.execute(
                select(func.count(ConsumerInbox.event_id))
            )
        ).scalar_one() == 2


@pytest.mark.asyncio
async def test_postgres_concurrent_materialization_is_idempotent(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    event = _event(721, now=now)
    async with factory() as setup_session:
        setup_session.add(event)
        await setup_session.commit()

    barrier = asyncio.Barrier(2)
    results = await asyncio.gather(
        _materialize_once(factory, barrier, event.event_id, now),
        _materialize_once(factory, barrier, event.event_id, now),
    )

    assert sorted(result.created_count for result in results) == [0, 1]
    assert all(result.delivery_count == 1 for result in results)
    async with factory() as verification_session:
        assert (
            await verification_session.execute(
                select(func.count(CommunicationDelivery.delivery_id))
            )
        ).scalar_one() == 1
