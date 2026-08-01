from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

import pytest

from crud.catalog_revision import CatalogRevisionDAO
from models import (
    IntegrationOutboxEvent,
    Product,
    Storefront,
    StorefrontCatalogRevision,
    StorefrontDomain,
    Tenant,
)
from models.tenancy import TenantScope
from services.catalog_invalidation_contracts import (
    CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
)
from services.catalog_revision_service import CatalogRevisionService


async def _seed_second_storefront(
    session: AsyncSession,
    *,
    with_domain: bool,
) -> TenantScope:
    session.add(
        Tenant(
            id=2,
            slug="seller-b",
            display_name="Seller B",
            status="active",
            is_system=False,
        )
    )
    await session.flush()
    session.add(
        Storefront(
            id=2,
            tenant_id=2,
            slug="main",
            display_name="Seller B Main",
            status="active",
            is_default=True,
        )
    )
    await session.flush()
    if with_domain:
        session.add(
            StorefrontDomain(
                storefront_id=2,
                hostname="seller.mvn.by",
                status="active",
                is_primary=True,
            )
        )
    await session.commit()
    return TenantScope(tenant_id=2, storefront_id=2, is_system=False)


@pytest.mark.asyncio
async def test_global_invalidation_stages_one_exact_event_per_active_storefront(
    db_engine,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await _seed_second_storefront(session, with_domain=True)
        product = Product(
            title="Global cache model",
            slug="global-cache-model",
            price=1000,
        )
        session.add(product)
        await session.commit()

        staged = await CatalogRevisionService.stage_invalidation(
            session,
            reason="catalog_global_test",
            product_ids=[int(product.id)],
            slugs=[product.slug],
        )
        await session.commit()

        events = (
            await session.execute(
                select(IntegrationOutboxEvent)
                .where(
                    IntegrationOutboxEvent.event_type
                    == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
                )
                .order_by(IntegrationOutboxEvent.aggregate_id.asc())
            )
        ).scalars().all()

    assert staged["revision"] == 1
    assert len(events) == 2
    assert {event.aggregate_id for event in events} == {"1:1", "2:2"}
    by_aggregate = {event.aggregate_id: event for event in events}
    assert by_aggregate["1:1"].payload["origins"] == ["https://mvn.by"]
    assert by_aggregate["2:2"].payload["origins"] == [
        "https://seller.mvn.by"
    ]
    for event in events:
        payload = event.payload
        assert set(payload) == {
            "schema_version",
            "scope",
            "tenant_id",
            "storefront_id",
            "origins",
            "paths",
            "global_revision",
            "storefront_revision",
            "cache_key",
            "reason",
        }
        assert payload["scope"] == "global"
        assert payload["global_revision"] == 1
        assert payload["storefront_revision"] == 0
        assert payload["cache_key"] == "g1-s0"
        assert payload["paths"] == sorted(payload["paths"])
        assert "/product/global-cache-model/" in payload["paths"]
        assert event.status == "pending"
        assert event.attempts == 0
        assert event.available_at == event.occurred_at
        assert event.created_at == event.occurred_at
        assert event.updated_at == event.occurred_at


@pytest.mark.asyncio
async def test_scoped_invalidation_changes_only_exact_storefront_revision(
    db_engine,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        second_scope = await _seed_second_storefront(
            session,
            with_domain=False,
        )
        staged = await CatalogRevisionService.stage_invalidation(
            session,
            reason="tenant_offer_updated",
            tenant_scope=second_scope,
            slugs=["scoped-model"],
        )
        await session.commit()

        global_snapshot = await CatalogRevisionDAO.get_current(session)
        canonical_snapshot = await CatalogRevisionDAO.get_storefront_current(
            session,
            tenant_scope=TenantScope(
                tenant_id=1,
                storefront_id=1,
                is_system=True,
            ),
        )
        second_snapshot = await CatalogRevisionDAO.get_storefront_current(
            session,
            tenant_scope=second_scope,
        )
        events = (
            await session.execute(
                select(IntegrationOutboxEvent).where(
                    IntegrationOutboxEvent.event_type
                    == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
                )
            )
        ).scalars().all()

    assert staged["revision"] == 0
    assert staged["storefront_revision"] == 1
    assert staged["cache_key"] == "g0-s1"
    assert global_snapshot.revision == 0
    assert canonical_snapshot.revision == 0
    assert second_snapshot.revision == 1
    assert len(events) == 1
    assert events[0].aggregate_id == "2:2"
    assert events[0].payload["scope"] == "storefront"
    assert events[0].payload["origins"] == []
    assert events[0].payload["cache_key"] == "g0-s1"


@pytest.mark.asyncio
async def test_equal_revision_tokens_are_namespaced_by_storefront_identity(
    db_engine,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        second_scope = await _seed_second_storefront(
            session,
            with_domain=False,
        )
        scopes = (
            TenantScope(
                tenant_id=1,
                storefront_id=1,
                is_system=True,
            ),
            second_scope,
        )
        staged = []
        for index, scope in enumerate(scopes, start=1):
            staged.append(
                await CatalogRevisionService.stage_invalidation(
                    session,
                    reason=f"storefront_collision_test_{index}",
                    tenant_scope=scope,
                    slugs=[f"storefront-model-{index}"],
                )
            )
            await session.commit()

        events = (
            await session.execute(
                select(IntegrationOutboxEvent)
                .where(
                    IntegrationOutboxEvent.event_type
                    == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
                )
                .order_by(IntegrationOutboxEvent.aggregate_id.asc())
            )
        ).scalars().all()

    assert [item["cache_key"] for item in staged] == ["g0-s1", "g0-s1"]
    assert [event.aggregate_id for event in events] == ["1:1", "2:2"]
    assert [event.idempotency_key for event in events] == [
        "catalog:1:1:storefront:g0-s1",
        "catalog:2:2:storefront:g0-s1",
    ]
    assert len({event.deduplication_key for event in events}) == 2


@pytest.mark.asyncio
async def test_catalog_mutation_revision_and_outbox_roll_back_atomically(
    db_engine,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup_session:
        product = Product(
            title="Atomic catalog model",
            slug="atomic-catalog-model",
            price=1000,
        )
        setup_session.add(product)
        await setup_session.commit()
        product_id = int(product.id)

    async with factory() as mutation_session:
        product = await mutation_session.get(Product, product_id)
        assert product is not None
        product.price = 1500
        mutation_session.add(product)
        await CatalogRevisionService.stage_invalidation(
            mutation_session,
            reason="atomic_catalog_test",
            product_ids=[product_id],
        )
        await mutation_session.rollback()

    async with factory() as verification_session:
        product = await verification_session.get(Product, product_id)
        assert product is not None
        assert product.price == 1000
        assert (
            await CatalogRevisionDAO.get_current(verification_session)
        ).revision == 0
        assert (
            await verification_session.execute(
                select(StorefrontCatalogRevision)
            )
        ).scalars().all() == []
        assert (
            await verification_session.execute(
                select(IntegrationOutboxEvent).where(
                    IntegrationOutboxEvent.event_type
                    == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
                )
            )
        ).scalars().all() == []


@pytest.mark.asyncio
async def test_concurrent_first_global_revision_bumps_are_monotonic(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    barrier = asyncio.Barrier(2)

    async def stage(reason: str) -> int:
        async with factory() as session:
            await barrier.wait()
            result = await CatalogRevisionService.stage_invalidation(
                session,
                reason=reason,
            )
            await session.commit()
            return int(result["revision"])

    revisions = await asyncio.gather(
        stage("concurrent_global_a"),
        stage("concurrent_global_b"),
    )

    assert sorted(revisions) == [1, 2]
    async with factory() as session:
        current = await CatalogRevisionDAO.get_current(session)
        events = (
            await session.execute(
                select(IntegrationOutboxEvent).where(
                    IntegrationOutboxEvent.event_type
                    == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
                )
            )
        ).scalars().all()
        assert current.revision == 2
        assert len(events) == 2
        assert {event.payload["cache_key"] for event in events} == {
            "g1-s0",
            "g2-s0",
        }
