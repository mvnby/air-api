import asyncio

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import IntegrationOutboxEvent
from services.communications.contracts import PublicContactLeadCreatedPayloadV1
from services.communications.outbox_service import IntegrationOutboxService


@pytest.mark.asyncio
async def test_postgres_concurrent_identical_enqueue_creates_one_event(db_engine):
    assert db_engine.dialect.name == "postgresql"
    session_factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    barrier = asyncio.Barrier(2)

    async def enqueue_from(worker_name: str) -> str:
        async with session_factory() as session:
            await barrier.wait()
            event = await IntegrationOutboxService.enqueue(
                session,
                event_type="crm.public_contact_lead.created",
                aggregate_type="lead",
                aggregate_id=812,
                aggregate_version=1,
                correlation_id=worker_name,
                idempotency_key="concurrent-contact-812",
                payload=PublicContactLeadCreatedPayloadV1(
                    lead_id=812,
                    status="new",
                    name="Иван",
                    phone="+375291112233",
                    message="Нужна консультация",
                ),
            )
            await session.commit()
            return event.event_id

    event_ids = await asyncio.gather(
        enqueue_from("request-a"),
        enqueue_from("request-b"),
    )

    async with session_factory() as verification_session:
        event_count = (
            await verification_session.execute(
                select(func.count(IntegrationOutboxEvent.event_id)).where(
                    IntegrationOutboxEvent.aggregate_id == "812"
                )
            )
        ).scalar_one()

    assert event_ids[0] == event_ids[1]
    assert event_count == 1
