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
    aggregate_ids = list(range(812, 820))
    for aggregate_id in aggregate_ids:
        barrier = asyncio.Barrier(2)

        async def enqueue_from(worker_name: str) -> tuple[str, bool]:
            async with session_factory() as session:
                await barrier.wait()
                result = await IntegrationOutboxService.enqueue_with_result(
                    session,
                    event_type="crm.public_contact_lead.created",
                    aggregate_type="lead",
                    aggregate_id=aggregate_id,
                    aggregate_version=1,
                    correlation_id=worker_name,
                    idempotency_key=f"concurrent-contact-{aggregate_id}",
                    payload=PublicContactLeadCreatedPayloadV1(
                        lead_id=aggregate_id,
                        status="new",
                        name="Иван",
                        phone="+375291112233",
                        message="Нужна консультация",
                    ),
                )
                await session.commit()
                return result.event.event_id, result.created

        results = await asyncio.gather(
            enqueue_from("request-a"),
            enqueue_from("request-b"),
        )
        assert results[0][0] == results[1][0]
        assert sorted(result[1] for result in results) == [False, True]

    async with session_factory() as verification_session:
        event_count = (
            await verification_session.execute(
                select(func.count(IntegrationOutboxEvent.event_id)).where(
                    IntegrationOutboxEvent.aggregate_id.in_(
                        [str(item) for item in aggregate_ids]
                    )
                )
            )
        ).scalar_one()

    assert event_count == len(aggregate_ids)
