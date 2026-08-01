from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import IntegrationOutboxEvent
from services.catalog_invalidation_contracts import (
    CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
)


class CatalogInvalidationEventDAO:
    @staticmethod
    async def database_now(session: AsyncSession) -> datetime:
        if session.get_bind().dialect.name == "postgresql":
            # ``now()`` is fixed at transaction start in PostgreSQL. Leases need
            # wall-clock time even when a transaction stays open long enough to
            # perform claim bookkeeping or recovery.
            value = (
                await session.execute(select(func.clock_timestamp()))
            ).scalar_one()
            if value.tzinfo is None or value.utcoffset() is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return datetime.now(timezone.utc)

    @staticmethod
    async def claimable_event(
        session: AsyncSession,
        *,
        now: datetime,
    ) -> IntegrationOutboxEvent | None:
        statement = (
            select(IntegrationOutboxEvent)
            .where(
                IntegrationOutboxEvent.event_type
                == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
                IntegrationOutboxEvent.status == "pending",
                IntegrationOutboxEvent.available_at <= now,
                IntegrationOutboxEvent.attempts
                < IntegrationOutboxEvent.max_attempts,
            )
            .order_by(
                IntegrationOutboxEvent.priority.asc(),
                IntegrationOutboxEvent.available_at.asc(),
                IntegrationOutboxEvent.occurred_at.asc(),
                IntegrationOutboxEvent.event_id.asc(),
            )
            .limit(1)
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def expired_events(
        session: AsyncSession,
        *,
        now: datetime,
        limit: int,
    ) -> list[IntegrationOutboxEvent]:
        statement = (
            select(IntegrationOutboxEvent)
            .where(
                IntegrationOutboxEvent.event_type
                == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
                IntegrationOutboxEvent.status == "processing",
                IntegrationOutboxEvent.lease_expires_at.is_not(None),
                IntegrationOutboxEvent.lease_expires_at <= now,
            )
            .order_by(
                IntegrationOutboxEvent.lease_expires_at.asc(),
                IntegrationOutboxEvent.event_id.asc(),
            )
            .limit(limit)
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        return list((await session.execute(statement)).scalars().all())

    @staticmethod
    async def owned_event(
        session: AsyncSession,
        *,
        event_id: str,
        worker_id: str,
        lease_token: str,
        now: datetime,
    ) -> IntegrationOutboxEvent | None:
        statement = select(IntegrationOutboxEvent).where(
            IntegrationOutboxEvent.event_id == event_id,
            IntegrationOutboxEvent.event_type
            == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
            IntegrationOutboxEvent.status == "processing",
            IntegrationOutboxEvent.worker_id == worker_id,
            IntegrationOutboxEvent.lease_token == lease_token,
            IntegrationOutboxEvent.lease_expires_at.is_not(None),
            IntegrationOutboxEvent.lease_expires_at > now,
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalar_one_or_none()
