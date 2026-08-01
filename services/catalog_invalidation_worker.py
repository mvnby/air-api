from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session_maker
from services.catalog_invalidation_contracts import (
    CatalogCacheInvalidationRequestedV1,
)
from services.catalog_invalidation_event_service import (
    CatalogInvalidationClaim,
    CatalogInvalidationEventService,
    CatalogInvalidationLeaseLost,
)
from services.catalog_purge_service import (
    CloudflareCatalogPurgeService,
    CloudflarePurgeConfig,
    CloudflarePurgeConfigurationError,
    CloudflarePurgeResult,
    build_catalog_purge_urls_for_targets,
    cloudflare_catalog_purge_service,
)


logger = logging.getLogger(__name__)


class InvalidCatalogInvalidationEvent(ValueError):
    pass


class CatalogInvalidationPurgeFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class CatalogInvalidationRunOutcome:
    outcome: Literal[
        "idle",
        "published",
        "retry",
        "dead",
        "lease_lost",
        "configuration_blocked",
    ]
    event_id: str | None = None
    attempts: int | None = None
    next_attempt_at: datetime | None = None
    recovered_retry_count: int = 0
    recovered_dead_count: int = 0
    configuration_mode: str | None = None
    no_public_origin: bool = False


class CatalogInvalidationWorker:
    """Durably purge one exact storefront event outside its DB transaction."""

    def __init__(
        self,
        *,
        worker_id: str,
        session_factory: Callable[[], AsyncSession] = async_session_maker,
        purge_service: CloudflareCatalogPurgeService = (
            cloudflare_catalog_purge_service
        ),
        purge_config: CloudflarePurgeConfig | None = None,
        lease_seconds: int = 120,
        recovery_limit: int = 100,
    ) -> None:
        self._worker_id = CatalogInvalidationEventService._normalize_worker_id(
            worker_id
        )
        self._session_factory = session_factory
        self._purge_service = purge_service
        self._purge_config = purge_config
        self._lease_seconds = (
            CatalogInvalidationEventService._normalize_lease_seconds(
                lease_seconds
            )
        )
        self._recovery_limit = max(
            1,
            min(
                CatalogInvalidationEventService.MAX_RECOVERY_LIMIT,
                int(recovery_limit),
            ),
        )

    async def run_once(self) -> CatalogInvalidationRunOutcome:
        purge_config = self._purge_config or CloudflarePurgeConfig.from_env()
        activation_mode = purge_config.activation_mode
        if activation_mode != "live":
            # Activation preflight happens before claim. A disabled, dry-run or
            # incomplete provider configuration therefore consumes zero event
            # attempts and leaves durable work pending for a corrected rollout.
            return CatalogInvalidationRunOutcome(
                outcome="configuration_blocked",
                configuration_mode=activation_mode,
            )

        recovery = await self._recover_expired()
        claim = await self._claim()
        if claim is None:
            return CatalogInvalidationRunOutcome(
                outcome="idle",
                recovered_retry_count=recovery.retry_count,
                recovered_dead_count=recovery.dead_count,
            )

        try:
            payload = CatalogCacheInvalidationRequestedV1.model_validate(
                claim.payload
            )
        except ValidationError as exc:
            return await self._record_failure(
                claim,
                InvalidCatalogInvalidationEvent(
                    "Catalog invalidation payload is invalid"
                ),
                permanent=True,
                recovery=recovery,
            )

        urls = build_catalog_purge_urls_for_targets(
            payload.origins,
            payload.paths,
        )
        try:
            if urls:
                purge_config.ensure_origins_belong_to_zone(payload.origins)
                result = await self._purge_with_heartbeat(
                    claim,
                    payload,
                    urls,
                    purge_config,
                )
                self._require_complete_live_purge(result)
            else:
                # By contract an empty origin list is an explicit event for an
                # active storefront that is not publicly routable yet. It is a
                # successful no-op, not an accidental purge of a fallback host.
                logger.info(
                    "Catalog invalidation no-op for non-routable storefront "
                    "tenant_id=%s storefront_id=%s event_id=%s",
                    payload.tenant_id,
                    payload.storefront_id,
                    claim.event_id,
                )
        except CatalogInvalidationLeaseLost:
            return self._lease_lost(claim, recovery)
        except asyncio.CancelledError:
            raise
        except CloudflarePurgeConfigurationError as exc:
            return await self._record_failure(
                claim,
                exc,
                permanent=True,
                recovery=recovery,
            )
        except Exception as exc:
            return await self._record_failure(
                claim,
                exc,
                permanent=False,
                recovery=recovery,
            )

        try:
            transition = await self._acknowledge(claim)
        except CatalogInvalidationLeaseLost:
            return self._lease_lost(claim, recovery)
        return CatalogInvalidationRunOutcome(
            outcome=transition.outcome,
            event_id=claim.event_id,
            attempts=transition.attempts,
            recovered_retry_count=recovery.retry_count,
            recovered_dead_count=recovery.dead_count,
            no_public_origin=not payload.origins,
        )

    async def _recover_expired(self):
        async with self._session_factory() as session:
            async with session.begin():
                return await CatalogInvalidationEventService.recover_expired(
                    session,
                    limit=self._recovery_limit,
                )

    async def _claim(self) -> CatalogInvalidationClaim | None:
        async with self._session_factory() as session:
            async with session.begin():
                return await CatalogInvalidationEventService.claim_next(
                    session,
                    worker_id=self._worker_id,
                    lease_seconds=self._lease_seconds,
                )

    async def _acknowledge(self, claim: CatalogInvalidationClaim):
        async with self._session_factory() as session:
            async with session.begin():
                return await CatalogInvalidationEventService.acknowledge(
                    session,
                    claim=claim,
                )

    async def _record_failure(
        self,
        claim: CatalogInvalidationClaim,
        error: BaseException,
        *,
        permanent: bool,
        recovery,
    ) -> CatalogInvalidationRunOutcome:
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    transition = await CatalogInvalidationEventService.fail(
                        session,
                        claim=claim,
                        error=error,
                        permanent=permanent,
                    )
        except CatalogInvalidationLeaseLost:
            return self._lease_lost(claim, recovery)
        return CatalogInvalidationRunOutcome(
            outcome=transition.outcome,
            event_id=claim.event_id,
            attempts=transition.attempts,
            next_attempt_at=transition.next_attempt_at,
            recovered_retry_count=recovery.retry_count,
            recovered_dead_count=recovery.dead_count,
        )

    async def _purge_with_heartbeat(
        self,
        claim: CatalogInvalidationClaim,
        payload: CatalogCacheInvalidationRequestedV1,
        urls: tuple[str, ...],
        purge_config: CloudflarePurgeConfig,
    ) -> CloudflarePurgeResult:
        stop_heartbeat = asyncio.Event()
        purge_task = asyncio.create_task(
            self._purge_service.purge_urls(
                scope=f"{payload.scope}:{payload.reason}",
                revision=payload.global_revision,
                urls=urls,
                config=purge_config,
            )
        )
        heartbeat_task = asyncio.create_task(
            self._heartbeat(claim, stop_heartbeat)
        )
        try:
            done, _ = await asyncio.wait(
                {purge_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if purge_task in done:
                result = await purge_task
                stop_heartbeat.set()
                await heartbeat_task
                return result

            heartbeat_error = heartbeat_task.exception()
            purge_task.cancel()
            with suppress(asyncio.CancelledError):
                await purge_task
            if heartbeat_error is not None:
                raise heartbeat_error
            raise RuntimeError("Catalog invalidation heartbeat stopped early")
        except BaseException:
            stop_heartbeat.set()
            if not purge_task.done():
                purge_task.cancel()
            if not heartbeat_task.done():
                heartbeat_task.cancel()
            await asyncio.gather(
                purge_task,
                heartbeat_task,
                return_exceptions=True,
            )
            raise

    async def _heartbeat(
        self,
        claim: CatalogInvalidationClaim,
        stop_event: asyncio.Event,
    ) -> None:
        interval_seconds = max(1.0, self._lease_seconds / 3)
        while True:
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=interval_seconds,
                )
                return
            except TimeoutError:
                pass
            async with self._session_factory() as session:
                async with session.begin():
                    await CatalogInvalidationEventService.renew(
                        session,
                        claim=claim,
                        lease_seconds=self._lease_seconds,
                    )

    @staticmethod
    def _require_complete_live_purge(result: CloudflarePurgeResult) -> None:
        if result.mode != "live":
            raise CloudflarePurgeConfigurationError(
                f"Cloudflare purge is not live: {result.mode}"
            )
        if result.failed_batches:
            details = "; ".join(result.errors[:3])
            raise CatalogInvalidationPurgeFailed(
                "Cloudflare purge had partial batch failures"
                + (f": {details}" if details else "")
            )

    @staticmethod
    def _lease_lost(claim, recovery) -> CatalogInvalidationRunOutcome:
        return CatalogInvalidationRunOutcome(
            outcome="lease_lost",
            event_id=claim.event_id,
            attempts=claim.attempts,
            recovered_retry_count=recovery.retry_count,
            recovered_dead_count=recovery.dead_count,
        )
