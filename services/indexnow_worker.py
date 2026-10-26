from __future__ import annotations

import asyncio
import logging

from pydantic import ValidationError

from core.config import settings
from core.database import async_session_maker
from services.catalog_invalidation_event_service import CatalogInvalidationLeaseLost
from services.indexnow_event_service import IndexNowEventService
from services.indexnow_service import IndexNowPayload, IndexNowRejected, IndexNowService


logger = logging.getLogger(__name__)


class IndexNowWorker:
    def __init__(self, *, session_factory=async_session_maker, provider=None, enabled=None):
        self._sessions = session_factory
        self._provider = provider or IndexNowService()
        self._enabled = enabled

    async def run_once(self) -> str:
        enabled = settings.INDEXNOW_ENABLED if self._enabled is None else self._enabled
        if not enabled:
            return "disabled"
        async with self._sessions() as session:
            async with session.begin():
                await IndexNowEventService.recover_expired(session, limit=100)
                claim = await IndexNowEventService.claim_next(
                    session, worker_id="scheduler-indexnow", lease_seconds=120,
                )
        if claim is None:
            return "idle"
        try:
            payload = IndexNowPayload.model_validate(claim.payload)
            # Bound the complete exchange well below the DB lease. HTTP I/O is
            # outside the transaction and cancellation leaves recoverable work.
            receipt = await asyncio.wait_for(self._provider.submit(payload.urls), timeout=45)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            try:
                async with self._sessions() as session:
                    async with session.begin():
                        transition = await IndexNowEventService.fail(
                            session,
                            claim=claim,
                            error=error,
                            permanent=isinstance(error, (ValidationError, IndexNowRejected)),
                        )
            except CatalogInvalidationLeaseLost:
                return "lease_lost"
            logger.warning("IndexNow send failed event=%s outcome=%s error=%s", claim.event_id, transition.outcome, type(error).__name__)
            return transition.outcome
        try:
            async with self._sessions() as session:
                async with session.begin():
                    await IndexNowEventService.acknowledge(session, claim=claim)
        except CatalogInvalidationLeaseLost:
            return "lease_lost"
        logger.info("IndexNow accepted event=%s urls=%s http_status=%s indexing_not_confirmed=true", claim.event_id, receipt.url_count, receipt.status_code)
        return "published"
