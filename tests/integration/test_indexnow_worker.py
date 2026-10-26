import asyncio
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from core.config import settings
from crud.indexnow import IndexNowEventDAO
from models import IntegrationOutboxEvent, Product, Storefront, StorefrontDomain, Tenant
from services.catalog_invalidation_contracts import CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
from services.catalog_invalidation_event_service import CatalogInvalidationEventService
from services.catalog_revision_service import CatalogRevisionService
from services.indexnow_event_service import IndexNowEventService
from services.indexnow_service import INDEXNOW_EVENT_TYPE, IndexNowProviderError, IndexNowReceipt
from services.indexnow_worker import IndexNowWorker
from services.product_write_service import ProductWriteService


async def stage(factory, monkeypatch):
    monkeypatch.setattr(settings, "INDEXNOW_ENABLED", True)
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", "https://mvn.by")
    async with factory() as session:
        await CatalogRevisionService.stage_invalidation(session, "indexnow_test", slugs=["old-model", "new-model"])
        await session.commit()
        events = (await session.execute(select(IntegrationOutboxEvent))).scalars().all()
        parent = next(event for event in events if event.event_type == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT)
        child = next(event for event in events if event.event_type == INDEXNOW_EVENT_TYPE)
        child.available_at = await IndexNowEventDAO.database_now(session)
        session.add(child)
        await session.commit()
        return parent.event_id, child.event_id


async def finish_purge(factory):
    async with factory() as session:
        claim = await CatalogInvalidationEventService.claim_next(session, worker_id="purger", lease_seconds=120)
        assert claim is not None
        await CatalogInvalidationEventService.acknowledge(session, claim=claim)
        await session.commit()


class Provider:
    def __init__(self):
        self.calls = []

    async def submit(self, urls):
        self.calls.append(urls)
        return IndexNowReceipt(202, len(urls))


@pytest.mark.asyncio
async def test_notification_waits_for_purge_then_is_accepted_once(db_engine, monkeypatch):
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    parent_id, child_id = await stage(factory, monkeypatch)
    provider = Provider()
    worker = IndexNowWorker(session_factory=factory, provider=provider, enabled=True)
    assert await worker.run_once() == "idle"
    async with factory() as session:
        assert (await session.get(IntegrationOutboxEvent, child_id)).attempts == 0
    await finish_purge(factory)
    assert await worker.run_once() == "published"
    assert await worker.run_once() == "idle"
    assert provider.calls == [[
        "https://mvn.by/brands/", "https://mvn.by/catalog/",
        "https://mvn.by/product/new-model/", "https://mvn.by/product/old-model/",
    ]]
    async with factory() as session:
        assert (await session.get(IntegrationOutboxEvent, parent_id)).status == "published"
        child = await session.get(IntegrationOutboxEvent, child_id)
        assert child.status == "published"
        assert child.attempts == 1


@pytest.mark.asyncio
async def test_provider_failure_preserves_work_without_changing_purge(db_engine, monkeypatch):
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    parent_id, child_id = await stage(factory, monkeypatch)
    await finish_purge(factory)

    class Unavailable:
        async def submit(self, urls):
            raise IndexNowProviderError("HTTP 429 provider-sensitive-details")

    assert await IndexNowWorker(session_factory=factory, provider=Unavailable(), enabled=True).run_once() == "retry"
    async with factory() as session:
        child = await session.get(IntegrationOutboxEvent, child_id)
        assert child.status == "pending"
        assert child.attempts == 1
        assert child.available_at > await IndexNowEventDAO.database_now(session)
        assert "provider-sensitive" not in child.last_error_message
        assert (await session.get(IntegrationOutboxEvent, parent_id)).status == "published"
        child.available_at = await IndexNowEventDAO.database_now(session)
        session.add(child)
        await session.commit()
    assert await IndexNowWorker(session_factory=factory, provider=Provider(), enabled=True).run_once() == "published"


@pytest.mark.asyncio
async def test_concurrent_workers_do_not_send_same_event_twice(db_engine, monkeypatch):
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    await stage(factory, monkeypatch)
    await finish_purge(factory)
    started, release = asyncio.Event(), asyncio.Event()

    class Slow(Provider):
        async def submit(self, urls):
            started.set()
            await release.wait()
            return await super().submit(urls)

    provider = Slow()
    first = asyncio.create_task(IndexNowWorker(session_factory=factory, provider=provider, enabled=True).run_once())
    await asyncio.wait_for(started.wait(), timeout=5)
    assert await IndexNowWorker(session_factory=factory, provider=provider, enabled=True).run_once() == "idle"
    release.set()
    assert await asyncio.wait_for(first, timeout=5) == "published"
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_disabled_and_rollback_do_not_create_notifications(db_engine, monkeypatch):
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(settings, "INDEXNOW_ENABLED", False)
    async with factory() as session:
        await CatalogRevisionService.stage_invalidation(session, "disabled_test", slugs=["a"])
        await session.commit()
        children = (await session.execute(select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.event_type == INDEXNOW_EVENT_TYPE))).scalars().all()
        assert children == []
        monkeypatch.setattr(settings, "INDEXNOW_ENABLED", True)
        await CatalogRevisionService.stage_invalidation(session, "rollback_test", slugs=["b"])
        await session.rollback()
        children = (await session.execute(select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.event_type == INDEXNOW_EVENT_TYPE))).scalars().all()
        assert children == []


@pytest.mark.asyncio
async def test_expired_lease_recovery_is_isolated_from_catalog_events(db_engine, monkeypatch):
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    parent_id, child_id = await stage(factory, monkeypatch)
    await finish_purge(factory)
    async with factory() as session:
        claim = await IndexNowEventService.claim_next(session, worker_id="crashed", lease_seconds=120)
        await session.commit()
        child = await session.get(IntegrationOutboxEvent, child_id)
        child.lease_expires_at = await IndexNowEventDAO.database_now(session) - timedelta(seconds=1)
        session.add(child)
        await session.commit()
        recovered = await IndexNowEventService.recover_expired(session, limit=10)
        await session.commit()
        assert recovered.retry_count == 1
        assert (await session.get(IntegrationOutboxEvent, parent_id)).status == "published"
        assert (await session.get(IntegrationOutboxEvent, child_id)).status == "pending"


@pytest.mark.asyncio
async def test_manager_product_rename_keeps_old_and_new_urls_and_excludes_partners(db_engine, monkeypatch):
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(settings, "INDEXNOW_ENABLED", True)
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", "https://mvn.by")
    async with factory() as session:
        session.add(Tenant(id=2, slug="partner", display_name="Partner", status="active", is_system=False))
        await session.flush()
        session.add(Storefront(id=2, tenant_id=2, slug="main", display_name="Partner", status="active", is_default=True))
        await session.flush()
        session.add(StorefrontDomain(storefront_id=2, hostname="partner.mvn.by", status="active", is_primary=True))
        product = Product(title="Test model", slug="original", price=1000, is_published=True)
        session.add(product)
        await session.commit()
        await ProductWriteService.update_product(session, product.id, {"slug": "renamed", "price": 1100})
        events = (await session.execute(select(IntegrationOutboxEvent))).scalars().all()
        assert len([e for e in events if e.event_type == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT]) == 2
        notifications = [e for e in events if e.event_type == INDEXNOW_EVENT_TYPE]
        assert len(notifications) == 1
        assert notifications[0].aggregate_id == "1:1"
        assert "https://mvn.by/product/original/" in notifications[0].payload["urls"]
        assert "https://mvn.by/product/renamed/" in notifications[0].payload["urls"]
