from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from models import IntegrationOutboxEvent
from services.catalog_invalidation_contracts import (
    CatalogCacheInvalidationRequestedV1,
)
from services.catalog_invalidation_event_service import (
    CatalogInvalidationEventService,
    CatalogInvalidationLeaseLost,
)
from services.catalog_invalidation_worker import CatalogInvalidationWorker
from services.catalog_purge_service import (
    CloudflarePurgeConfig,
    CloudflarePurgeResult,
)
from services.communications.outbox_service import IntegrationOutboxService


LIVE_CONFIG = CloudflarePurgeConfig(
    zone_id="zone-123",
    api_token="test-token",
    enabled=True,
    dry_run=False,
    public_site_url="https://mvn.by",
    zone_hostnames=("mvn.by",),
    min_interval_seconds=0,
)


def _payload(
    *,
    revision: int,
    origins: list[str] | None = None,
) -> CatalogCacheInvalidationRequestedV1:
    return CatalogCacheInvalidationRequestedV1(
        scope="global",
        tenant_id=1,
        storefront_id=1,
        origins=["https://mvn.by"] if origins is None else origins,
        paths=["/catalog/", f"/product/model-{revision}/"],
        global_revision=revision,
        storefront_revision=0,
        cache_key=f"g{revision}-s0",
        reason="worker_integration_test",
    )


async def _enqueue_catalog_event(
    factory,
    *,
    revision: int,
    origins: list[str] | None = None,
) -> str:
    async with factory() as session:
        event = await CatalogInvalidationEventService.enqueue_requested(
            session,
            payload=_payload(revision=revision, origins=origins),
            idempotency_key=f"catalog-worker-test:{revision}",
        )
        await session.commit()
        return event.event_id


class SuccessfulPurgeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def purge_urls(self, *, urls, **kwargs):
        normalized = tuple(urls)
        self.calls.append(normalized)
        return CloudflarePurgeResult(
            mode="live",
            url_count=len(normalized),
            attempted_batches=1,
        )


@pytest.mark.asyncio
async def test_two_workers_claim_one_event_once_with_skip_locked(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    event_id = await _enqueue_catalog_event(factory, revision=1)
    purge_started = asyncio.Event()
    release_purge = asyncio.Event()

    class SlowPurgeService(SuccessfulPurgeService):
        async def purge_urls(self, *, urls, **kwargs):
            normalized = tuple(urls)
            self.calls.append(normalized)
            purge_started.set()
            await release_purge.wait()
            return CloudflarePurgeResult(
                mode="live",
                url_count=len(normalized),
                attempted_batches=1,
            )

    purge_service = SlowPurgeService()
    first_worker = CatalogInvalidationWorker(
        worker_id="catalog-worker-a",
        session_factory=factory,
        purge_service=purge_service,
        purge_config=LIVE_CONFIG,
        lease_seconds=30,
    )
    second_worker = CatalogInvalidationWorker(
        worker_id="catalog-worker-b",
        session_factory=factory,
        purge_service=purge_service,
        purge_config=LIVE_CONFIG,
        lease_seconds=30,
    )

    first_task = asyncio.create_task(first_worker.run_once())
    await asyncio.wait_for(purge_started.wait(), timeout=5)
    second_outcome = await second_worker.run_once()
    release_purge.set()
    first_outcome = await asyncio.wait_for(first_task, timeout=5)

    assert first_outcome.outcome == "published"
    assert second_outcome.outcome == "idle"
    assert len(purge_service.calls) == 1
    async with factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        assert event is not None
        assert event.status == "published"
        assert event.attempts == 1
        assert event.worker_id is None
        assert event.lease_token is None
        assert event.lease_expires_at is None


@pytest.mark.asyncio
async def test_partial_provider_failure_is_retried_and_error_is_sanitized(
    db_engine,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    event_id = await _enqueue_catalog_event(factory, revision=2)

    class PartialFailurePurgeService:
        async def purge_urls(self, *, urls, **kwargs):
            return CloudflarePurgeResult(
                mode="live",
                url_count=len(tuple(urls)),
                attempted_batches=3,
                failed_batches=1,
                errors=("provider-sensitive-detail",),
            )

    worker = CatalogInvalidationWorker(
        worker_id="catalog-worker-retry",
        session_factory=factory,
        purge_service=PartialFailurePurgeService(),
        purge_config=LIVE_CONFIG,
        lease_seconds=30,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "retry"
    assert outcome.attempts == 1
    assert outcome.next_attempt_at is not None
    async with factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        assert event is not None
        assert event.status == "pending"
        assert event.attempts == 1
        assert event.available_at > event.occurred_at
        assert event.last_error_code == "CatalogInvalidationPurgeFailed"
        assert event.last_error_message == (
            "Catalog invalidation failed: CatalogInvalidationPurgeFailed"
        )
        assert "provider-sensitive-detail" not in event.last_error_message
        assert event.worker_id is None
        assert event.lease_token is None


@pytest.mark.asyncio
async def test_expired_lease_recovery_defers_retry_without_duplicate_purge(
    db_engine,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    retry_event_id = await _enqueue_catalog_event(factory, revision=3)
    dead_event_id = await _enqueue_catalog_event(factory, revision=4)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with factory() as session:
        retry_event = await session.get(IntegrationOutboxEvent, retry_event_id)
        dead_event = await session.get(IntegrationOutboxEvent, dead_event_id)
        assert retry_event is not None
        assert dead_event is not None
        for event in (retry_event, dead_event):
            event.status = "processing"
            event.worker_id = "lost-worker"
            event.lease_token = f"lost-token-{event.event_id}"
            event.lease_expires_at = past
        retry_event.attempts = 1
        dead_event.attempts = dead_event.max_attempts
        await session.commit()

    purge_service = SuccessfulPurgeService()
    worker = CatalogInvalidationWorker(
        worker_id="catalog-worker-recovery",
        session_factory=factory,
        purge_service=purge_service,
        purge_config=LIVE_CONFIG,
        lease_seconds=30,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "idle"
    assert outcome.recovered_retry_count == 1
    assert outcome.recovered_dead_count == 1
    assert purge_service.calls == []
    async with factory() as session:
        retry_event = await session.get(IntegrationOutboxEvent, retry_event_id)
        dead_event = await session.get(IntegrationOutboxEvent, dead_event_id)
        assert retry_event is not None
        assert dead_event is not None
        assert retry_event.status == "pending"
        assert retry_event.attempts == 1
        assert retry_event.available_at > datetime.now(timezone.utc)
        assert retry_event.worker_id is None
        assert retry_event.lease_token is None
        assert dead_event.status == "dead"
        assert dead_event.worker_id is None
        assert dead_event.lease_token is None


@pytest.mark.asyncio
async def test_stale_lease_token_cannot_acknowledge_new_owner(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    event_id = await _enqueue_catalog_event(factory, revision=5)
    async with factory() as session:
        claim = await CatalogInvalidationEventService.claim_next(
            session,
            worker_id="catalog-worker-old",
            lease_seconds=30,
        )
        assert claim is not None
        await session.commit()

    async with factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        assert event is not None
        event.worker_id = "catalog-worker-new"
        event.lease_token = "replacement-token"
        event.lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)
        await session.commit()

    async with factory() as session:
        with pytest.raises(CatalogInvalidationLeaseLost):
            await CatalogInvalidationEventService.acknowledge(
                session,
                claim=claim,
            )
        await session.rollback()

    async with factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        assert event is not None
        assert event.status == "processing"
        assert event.worker_id == "catalog-worker-new"
        assert event.lease_token == "replacement-token"


@pytest.mark.asyncio
async def test_non_routable_event_is_explicit_published_noop(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    event_id = await _enqueue_catalog_event(
        factory,
        revision=6,
        origins=[],
    )

    class ForbiddenPurgeService:
        async def purge_urls(self, **kwargs):
            raise AssertionError("non-routable event must not call provider")

    worker = CatalogInvalidationWorker(
        worker_id="catalog-worker-noop",
        session_factory=factory,
        purge_service=ForbiddenPurgeService(),
        purge_config=LIVE_CONFIG,
        lease_seconds=30,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "published"
    assert outcome.no_public_origin is True
    async with factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        assert event is not None
        assert event.status == "published"
        assert event.attempts == 1


@pytest.mark.asyncio
async def test_origin_in_another_zone_is_terminal_configuration_failure(
    db_engine,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    event_id = await _enqueue_catalog_event(
        factory,
        revision=7,
        origins=["https://seller.example"],
    )
    purge_service = SuccessfulPurgeService()
    worker = CatalogInvalidationWorker(
        worker_id="catalog-worker-wrong-zone",
        session_factory=factory,
        purge_service=purge_service,
        purge_config=LIVE_CONFIG,
        lease_seconds=30,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "dead"
    assert outcome.attempts == 1
    assert purge_service.calls == []
    async with factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        assert event is not None
        assert event.status == "dead"
        assert event.last_error_code == "CloudflarePurgeConfigurationError"
        assert event.last_error_message == (
            "Catalog invalidation failed: CloudflarePurgeConfigurationError"
        )


@pytest.mark.asyncio
async def test_worker_ignores_unrelated_outbox_event_types(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        unrelated = await IntegrationOutboxService.enqueue(
            session,
            event_type="crm.unrelated.created.v1",
            aggregate_type="lead",
            aggregate_id="123",
            idempotency_key="unrelated-worker-test",
            payload={"schema_version": 1, "lead_id": 123},
        )
        await session.commit()
        unrelated_id = unrelated.event_id

    worker = CatalogInvalidationWorker(
        worker_id="catalog-worker-exact-type",
        session_factory=factory,
        purge_service=SuccessfulPurgeService(),
        purge_config=LIVE_CONFIG,
        lease_seconds=30,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "idle"
    async with factory() as session:
        event = await session.get(IntegrationOutboxEvent, unrelated_id)
        assert event is not None
        assert event.status == "pending"
        assert event.attempts == 0
