from decimal import Decimal

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import IntegrationOutboxEvent
from services.communications.contracts import (
    PublicContactLeadCreatedPayloadV1,
    PublicOrderCreatedPayloadV1,
    PublicOrderCustomerSnapshotV1,
)
from services.communications.outbox_service import (
    IntegrationOutboxService,
    OutboxEventConflictError,
)


@pytest.fixture
async def outbox_session_factory(tmp_path):
    database_path = tmp_path / "outbox.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(IntegrationOutboxEvent.__table__.create)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _lead_payload(*, message: str = "Нужна консультация"):
    return PublicContactLeadCreatedPayloadV1(
        lead_id=12,
        status="new",
        name="Иван",
        phone="+375291112233",
        message=message,
    )


def test_deduplication_identity_is_canonical_and_requires_a_discriminator():
    first = IntegrationOutboxService.build_deduplication_key(
        event_type="crm.event",
        schema_version=1,
        aggregate_type="order",
        aggregate_id="foo",
        aggregate_version=1,
        idempotency_key="av2:x",
    )
    second = IntegrationOutboxService.build_deduplication_key(
        event_type="crm.event",
        schema_version=1,
        aggregate_type="order",
        aggregate_id="foo:av1",
        aggregate_version=2,
        idempotency_key="x",
    )

    assert first != second
    assert first.startswith("sha256:")
    assert len(first) == 71

    with pytest.raises(ValueError, match="aggregate_version or idempotency_key"):
        IntegrationOutboxService.build_deduplication_key(
            event_type="crm.event",
            schema_version=1,
            aggregate_type="order",
            aggregate_id="foo",
            aggregate_version=None,
            idempotency_key=None,
        )


@pytest.mark.asyncio
async def test_enqueue_is_deterministic_and_does_not_commit(outbox_session_factory):
    async with outbox_session_factory() as session:
        first = await IntegrationOutboxService.enqueue(
            session,
            event_type="crm.public_contact_lead.created",
            aggregate_type="lead",
            aggregate_id=12,
            aggregate_version=1,
            idempotency_key="contact-request-12",
            payload=_lead_payload(),
        )
        duplicate = await IntegrationOutboxService.enqueue(
            session,
            event_type="crm.public_contact_lead.created",
            aggregate_type="lead",
            aggregate_id=12,
            aggregate_version=1,
            idempotency_key="contact-request-12",
            payload=_lead_payload(),
        )

        assert duplicate is first
        assert first.event_id == duplicate.event_id
        assert (
            await session.execute(select(func.count(IntegrationOutboxEvent.event_id)))
        ).scalar_one() == 1
        await session.rollback()

    async with outbox_session_factory() as verification_session:
        count = (
            await verification_session.execute(
                select(func.count(IntegrationOutboxEvent.event_id))
            )
        ).scalar_one()
        assert count == 0


@pytest.mark.asyncio
async def test_same_event_key_with_different_payload_is_a_conflict(
    outbox_session_factory,
):
    async with outbox_session_factory() as session:
        await IntegrationOutboxService.enqueue(
            session,
            event_type="crm.public_contact_lead.created",
            aggregate_type="lead",
            aggregate_id=12,
            aggregate_version=1,
            payload=_lead_payload(message="Первая версия"),
        )

        with pytest.raises(OutboxEventConflictError):
            await IntegrationOutboxService.enqueue(
                session,
                event_type="crm.public_contact_lead.created",
                aggregate_type="lead",
                aggregate_id=12,
                aggregate_version=1,
                payload=_lead_payload(message="Другая версия"),
            )


@pytest.mark.asyncio
async def test_aggregate_versions_produce_different_event_ids(outbox_session_factory):
    payload = PublicOrderCreatedPayloadV1(
        order_id=41,
        status="negotiation",
        customer=PublicOrderCustomerSnapshotV1(
            name="Иван",
            phone="+375291112233",
        ),
        total_amount=Decimal("1280.50"),
    )
    async with outbox_session_factory() as session:
        version_one = await IntegrationOutboxService.enqueue(
            session,
            event_type="crm.public_order.changed",
            aggregate_type="order",
            aggregate_id=41,
            aggregate_version=1,
            payload=payload,
        )
        version_two = await IntegrationOutboxService.enqueue(
            session,
            event_type="crm.public_order.changed",
            aggregate_type="order",
            aggregate_id=41,
            aggregate_version=2,
            payload=payload,
        )

        assert version_one.event_id != version_two.event_id
        assert version_one.deduplication_key != version_two.deduplication_key
