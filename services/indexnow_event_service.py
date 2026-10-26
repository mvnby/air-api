from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from crud.indexnow import IndexNowEventDAO
from models import IntegrationOutboxEvent
from services.catalog_invalidation_contracts import CatalogCacheInvalidationRequestedV1
from services.catalog_invalidation_event_service import CatalogInvalidationEventService
from services.communications.outbox_service import IntegrationOutboxService
from services.indexnow_service import INDEXNOW_EVENT_TYPE, IndexNowPayload, catalog_indexnow_urls


class IndexNowEventService(CatalogInvalidationEventService):
    """Reuse the tested DB-clock lease/retry fence with a distinct event type."""

    DAO = IndexNowEventDAO
    RETRY_BASE_SECONDS = 60

    @classmethod
    async def stage_catalog_notification(
        cls,
        session: AsyncSession,
        *,
        catalog_event: IntegrationOutboxEvent,
        payload: CatalogCacheInvalidationRequestedV1,
    ) -> None:
        urls = catalog_indexnow_urls(payload.origins, payload.paths)
        # Chunk by protocol limit; old/new slugs stay in the same durable stream.
        for offset in range(0, len(urls), 10000):
            now = await cls.DAO.database_now(session)
            result = await IntegrationOutboxService.enqueue_with_result(
                session,
                event_type=INDEXNOW_EVENT_TYPE,
                aggregate_type="storefront_catalog",
                aggregate_id=f"{payload.tenant_id}:{payload.storefront_id}",
                idempotency_key=f"indexnow:{catalog_event.event_id}:{offset // 10000}",
                payload=IndexNowPayload(
                    catalog_event_id=catalog_event.event_id,
                    tenant_id=payload.tenant_id,
                    storefront_id=payload.storefront_id,
                    urls=urls[offset:offset + 10000],
                ),
                occurred_at=now,
                priority=90,
                max_attempts=24,
            )
            if result.created:
                result.event.available_at = now + timedelta(seconds=30)
                result.event.created_at = now
                result.event.updated_at = now
                session.add(result.event)
        await session.flush()

    @staticmethod
    def _safe_error_message(error: BaseException) -> str:
        return f"IndexNow notification failed: {type(error).__name__}"[:1000]
