from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import select

from crud.catalog_invalidation import CatalogInvalidationEventDAO
from models import IntegrationOutboxEvent
from services.catalog_invalidation_contracts import CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
from services.indexnow_service import INDEXNOW_EVENT_TYPE


class IndexNowEventDAO(CatalogInvalidationEventDAO):
    EVENT_TYPE = INDEXNOW_EVENT_TYPE

    @classmethod
    async def claimable_event(cls, session: AsyncSession, *, now: datetime):
        parent = aliased(IntegrationOutboxEvent)
        # Do not consume an attempt until the exact committed invalidation has
        # completed. Parent and child are staged in the same producer transaction.
        completed_purge = (
            select(parent.event_id)
            .where(
                parent.event_id == IntegrationOutboxEvent.payload["catalog_event_id"].as_string(),
                parent.event_type == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
                parent.status == "published",
                parent.aggregate_id == IntegrationOutboxEvent.aggregate_id,
            )
            .exists()
        )
        statement = (
            select(IntegrationOutboxEvent)
            .where(
                IntegrationOutboxEvent.event_type == cls.EVENT_TYPE,
                IntegrationOutboxEvent.status == "pending",
                IntegrationOutboxEvent.available_at <= now,
                IntegrationOutboxEvent.attempts < IntegrationOutboxEvent.max_attempts,
                completed_purge,
            )
            .order_by(IntegrationOutboxEvent.available_at, IntegrationOutboxEvent.event_id)
            .limit(1)
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        return (await session.execute(statement)).scalar_one_or_none()
