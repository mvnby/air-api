from __future__ import annotations

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from crud.shared_catalog_grant import SharedCatalogGrantDAO
from models import (
    IntegrationOutboxEvent,
    Product,
    Storefront,
    StorefrontCatalogRevision,
    StorefrontDomain,
    Tenant,
    TenantAuditEvent,
    TenantCatalogGrant,
    TenantOffer,
)
from models.tenancy import TenantScope
from services.public_catalog_visibility_service import (
    PublicCatalogVisibilityService,
)
from services.shared_catalog_grant_manifest import SharedCatalogGrantManifest
from services.shared_catalog_grant_planner import SharedCatalogGrantBlockedError
from services.shared_catalog_grant_service import SharedCatalogGrantService
from services.tenant_offer_catalog_invalidation import (
    TenantOfferCatalogInvalidationAdapter,
)
from services.tenant_offer_service import TenantOfferService


def _manifest(*, batch_size: int = 2) -> SharedCatalogGrantManifest:
    return SharedCatalogGrantManifest.normalize(
        {
            "version": 1,
            "tenant_slug": "polotsk",
            "storefront_slug": "main",
            "mode": "all_published",
            "price_policy": "inherit_master",
            "owner_type": "system",
            "actor_username": "system:catalog-grant-sync",
            "batch_size": batch_size,
        }
    )


async def _seed_scope(
    session: AsyncSession,
) -> tuple[Tenant, Storefront, list[Product]]:
    tenant = Tenant(
        slug="polotsk",
        display_name="Двина Климат",
        kind="independent_seller",
        status="active",
        is_system=False,
    )
    session.add(tenant)
    await session.flush()
    storefront = Storefront(
        tenant_id=int(tenant.id),
        slug="main",
        display_name="Двина Климат",
        status="draft",
        city="Полоцк",
        is_default=True,
    )
    session.add(storefront)
    products = [
        Product(
            title=f"Shared product {index}",
            slug=f"shared-grant-product-{index}",
            price=10_000 + index,
            old_price=11_000 + index,
            is_published=True,
        )
        for index in range(3)
    ]
    session.add_all(products)
    await session.flush()
    return tenant, storefront, products


async def _execute(
    session: AsyncSession,
    *,
    desired_status: str,
    manifest: SharedCatalogGrantManifest,
) -> dict:
    plan = await SharedCatalogGrantService.plan(
        session,
        desired_status=desired_status,
        manifest=manifest,
    )
    assert plan["ready"] is True, plan["blockers"]
    return await SharedCatalogGrantService.execute(
        session,
        desired_status=desired_status,
        manifest=manifest,
        plan_token=plan["plan_token"],
    )


@pytest.mark.asyncio
async def test_bounded_sync_is_hidden_until_complete_and_preserves_manual_price(
    db: AsyncSession,
) -> None:
    tenant, storefront, products = await _seed_scope(db)
    manual = TenantOffer(
        tenant_id=int(tenant.id),
        storefront_id=int(storefront.id),
        product_id=int(products[0].id),
        price=9_500,
        old_price=10_500,
        is_published=False,
        status="disabled",
        created_by_username="onboarding",
        updated_by_username="onboarding",
    )
    db.add(manual)
    await db.flush()
    manifest = _manifest(batch_size=2)

    first_plan = await SharedCatalogGrantService.plan(
        db,
        desired_status="active",
        manifest=manifest,
    )
    assert first_plan["offer_change_count"] == 3
    assert first_plan["batch_change_count"] == 2
    assert first_plan["has_more"] is True
    assert first_plan["grant_change"]["after_status"] == "syncing"
    first = await SharedCatalogGrantService.execute(
        db,
        desired_status="active",
        manifest=manifest,
        plan_token=first_plan["plan_token"],
    )
    assert first["grant_status"] == "syncing"
    assert first["offer_changes"] == 2
    scope = TenantScope(
        tenant_id=int(tenant.id),
        storefront_id=int(storefront.id),
        is_canonical_storefront=False,
    )
    assert (
        await PublicCatalogVisibilityService.get_visible_product_by_id(
            db,
            tenant_scope=scope,
            product_id=int(products[0].id),
        )
        is None
    )
    second = await _execute(
        db,
        desired_status="active",
        manifest=manifest,
    )
    assert second["grant_status"] == "active"
    assert second["complete"] is True
    offers = list(
        (
            await db.execute(
                select(TenantOffer)
                .where(
                    TenantOffer.tenant_id == tenant.id,
                    TenantOffer.storefront_id == storefront.id,
                )
                .order_by(TenantOffer.product_id.asc())
            )
        ).scalars()
    )
    assert len(offers) == 3
    assert all(offer.catalog_grant_id is not None for offer in offers)
    assert offers[0].price == 9_500
    assert offers[0].price_source == "manual"
    assert [offer.price_source for offer in offers[1:]] == [
        "inherited_master",
        "inherited_master",
    ]
    projection = await PublicCatalogVisibilityService.get_visible_product_by_id(
        db,
        tenant_scope=scope,
        product_id=int(products[2].id),
    )
    assert projection is not None and projection.price == products[2].price
    audit_count = int(
        (
            await db.execute(
                select(func.count(TenantAuditEvent.id)).where(
                    TenantAuditEvent.action == "tenant_catalog_grant.synced"
                )
            )
        ).scalar_one()
    )
    assert audit_count == 2

    no_op = await _execute(
        db,
        desired_status="active",
        manifest=manifest,
    )
    assert no_op["changed"] is False
    assert no_op["offer_changes"] == 0


@pytest.mark.asyncio
async def test_unpublish_is_fail_closed_and_sync_updates_inherited_projection(
    db: AsyncSession,
) -> None:
    tenant, storefront, products = await _seed_scope(db)
    manifest = _manifest(batch_size=10)
    await _execute(db, desired_status="active", manifest=manifest)
    scope = TenantScope(
        tenant_id=int(tenant.id),
        storefront_id=int(storefront.id),
        is_canonical_storefront=False,
    )
    product = products[1]
    product.is_published = False
    product.price = 12_345
    product.old_price = 13_345
    await db.flush()

    assert (
        await PublicCatalogVisibilityService.get_visible_product_by_id(
            db,
            tenant_scope=scope,
            product_id=int(product.id),
        )
        is None
    )
    disabled = await _execute(db, desired_status="active", manifest=manifest)
    assert disabled["offer_changes"] == 1
    offer = await db.scalar(
        select(TenantOffer).where(
            TenantOffer.tenant_id == tenant.id,
            TenantOffer.storefront_id == storefront.id,
            TenantOffer.product_id == product.id,
        )
    )
    assert offer.status == "disabled"
    assert offer.is_published is False

    product.is_published = True
    await db.flush()
    assert (
        await PublicCatalogVisibilityService.get_visible_product_by_id(
            db,
            tenant_scope=scope,
            product_id=int(product.id),
        )
        is None
    )
    restored = await _execute(db, desired_status="active", manifest=manifest)
    assert restored["offer_changes"] == 1
    assert offer.status == "active"
    assert offer.price == 12_345
    assert offer.old_price == 13_345

    foreign_tenant = Tenant(
        slug="foreign",
        display_name="Foreign",
        status="active",
        is_system=False,
    )
    db.add(foreign_tenant)
    await db.flush()
    foreign_storefront = Storefront(
        tenant_id=int(foreign_tenant.id),
        slug="main",
        display_name="Foreign",
        status="active",
        is_default=True,
    )
    db.add(foreign_storefront)
    await db.flush()
    assert (
        await PublicCatalogVisibilityService.get_visible_product_by_id(
            db,
            tenant_scope=TenantScope(
                tenant_id=int(foreign_tenant.id),
                storefront_id=int(foreign_storefront.id),
                is_canonical_storefront=False,
            ),
            product_id=int(product.id),
        )
        is None
    )


@pytest.mark.asyncio
async def test_operator_price_override_changes_provenance_but_status_only_does_not(
    db: AsyncSession,
) -> None:
    tenant, storefront, products = await _seed_scope(db)
    manifest = _manifest(batch_size=10)
    await _execute(db, desired_status="active", manifest=manifest)
    offer = await db.scalar(
        select(TenantOffer).where(
            TenantOffer.tenant_id == tenant.id,
            TenantOffer.storefront_id == storefront.id,
            TenantOffer.product_id == products[0].id,
        )
    )
    grant_id = int(offer.catalog_grant_id)
    scope = TenantScope(
        tenant_id=int(tenant.id),
        storefront_id=int(storefront.id),
        is_canonical_storefront=False,
    )

    await TenantOfferService.update_offer(
        db,
        offer_id=int(offer.id),
        payload={"status": "disabled"},
        tenant_scope=scope,
        actor_username="root",
        actor_staff_user_id=None,
    )
    assert offer.price_source == "inherited_master"
    await TenantOfferService.update_offer(
        db,
        offer_id=int(offer.id),
        payload={
            "price": 9_000,
            "old_price": 9_500,
            "status": "active",
            "is_published": True,
        },
        tenant_scope=scope,
        actor_username="root",
        actor_staff_user_id=None,
    )
    assert offer.price_source == "manual"
    assert offer.catalog_grant_id == grant_id

    products[0].price = 20_000
    products[0].old_price = 21_000
    await db.flush()
    no_overwrite = await _execute(
        db,
        desired_status="active",
        manifest=manifest,
    )
    assert no_overwrite["offer_changes"] == 0
    assert offer.price == 9_000
    assert offer.old_price == 9_500


@pytest.mark.asyncio
async def test_active_resync_keeps_existing_catalog_visible_and_invalidates_change(
    db: AsyncSession,
) -> None:
    tenant, storefront, products = await _seed_scope(db)
    manifest = _manifest(batch_size=10)
    await _execute(db, desired_status="active", manifest=manifest)
    storefront.status = "active"
    db.add(
        StorefrontDomain(
            storefront_id=int(storefront.id),
            hostname="polotsk.mvn.by",
            status="active",
            is_primary=True,
        )
    )
    await db.flush()
    scope = TenantScope(
        tenant_id=int(tenant.id),
        storefront_id=int(storefront.id),
        is_canonical_storefront=False,
    )
    product = products[0]
    product.price = 15_000
    product.old_price = 16_000
    await db.flush()

    before = await PublicCatalogVisibilityService.get_visible_product_by_id(
        db,
        tenant_scope=scope,
        product_id=int(product.id),
    )
    assert before is not None
    plan = await SharedCatalogGrantService.plan(
        db,
        desired_status="active",
        manifest=manifest,
    )
    assert plan["ready"] is True
    assert plan["grant"]["status"] == "active"
    assert plan["grant_change"] is None
    synced = await SharedCatalogGrantService.execute(
        db,
        desired_status="active",
        manifest=manifest,
        plan_token=plan["plan_token"],
    )
    assert synced["grant_status"] == "active"
    assert synced["offer_changes"] == 1
    assert synced["catalog_invalidation_staged"] is True
    after = await PublicCatalogVisibilityService.get_visible_product_by_id(
        db,
        tenant_scope=scope,
        product_id=int(product.id),
    )
    assert after is not None and after.price == 15_000


@pytest.mark.asyncio
async def test_active_disable_hides_entire_grant_and_stages_revision_outbox_atomically(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, storefront, _products = await _seed_scope(db)
    manifest = _manifest(batch_size=2)
    await _execute(db, desired_status="active", manifest=manifest)
    await _execute(db, desired_status="active", manifest=manifest)
    storefront.status = "active"
    db.add(
        StorefrontDomain(
            storefront_id=int(storefront.id),
            hostname="polotsk.mvn.by",
            status="active",
            is_primary=True,
        )
    )
    await db.commit()

    original_stage = TenantOfferCatalogInvalidationAdapter.stage

    async def fail_invalidation(*args, **kwargs):
        raise RuntimeError("simulated outbox failure")

    monkeypatch.setattr(
        TenantOfferCatalogInvalidationAdapter,
        "stage",
        fail_invalidation,
    )
    plan = await SharedCatalogGrantService.plan(
        db,
        desired_status="disabled",
        manifest=manifest,
    )
    with pytest.raises(RuntimeError, match="simulated outbox failure"):
        await SharedCatalogGrantService.execute(
            db,
            desired_status="disabled",
            manifest=manifest,
            plan_token=plan["plan_token"],
        )
    await db.rollback()
    grant = await db.scalar(select(TenantCatalogGrant))
    assert grant.status == "active"
    assert await db.scalar(select(StorefrontCatalogRevision)) is None
    assert await db.scalar(select(IntegrationOutboxEvent)) is None

    monkeypatch.setattr(
        TenantOfferCatalogInvalidationAdapter,
        "stage",
        staticmethod(original_stage),
    )
    disabled = await _execute(db, desired_status="disabled", manifest=manifest)
    assert disabled["grant_status"] == "disabled"
    assert disabled["catalog_invalidation_staged"] is True
    revision = await db.get(
        StorefrontCatalogRevision,
        (int(tenant.id), int(storefront.id)),
    )
    assert revision is not None and revision.revision == 1
    assert await db.scalar(select(IntegrationOutboxEvent)) is not None
    visible_count = int(
        (
            await db.execute(
                select(func.count(TenantOffer.id)).where(
                    TenantOffer.tenant_id == tenant.id,
                    TenantOffer.storefront_id == storefront.id,
                    TenantOffer.status == "active",
                )
            )
        ).scalar_one()
    )
    assert visible_count == 1  # cleanup is bounded, grant status is the visibility fence
    scope = TenantScope(
        tenant_id=int(tenant.id),
        storefront_id=int(storefront.id),
        is_canonical_storefront=False,
    )
    for product_id in (
        await db.execute(select(Product.id).order_by(Product.id.asc()))
    ).scalars():
        assert (
            await PublicCatalogVisibilityService.get_visible_product_by_id(
                db,
                tenant_scope=scope,
                product_id=int(product_id),
            )
            is None
        )


@pytest.mark.asyncio
async def test_postgresql_advisory_lock_serializes_same_scope(db_engine) -> None:
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed:
        await _seed_scope(seed)
        await seed.commit()
    manifest = _manifest(batch_size=2)
    async with factory() as planner:
        plan = await SharedCatalogGrantService.plan(
            planner,
            desired_status="active",
            manifest=manifest,
        )
        await planner.rollback()
    async with factory() as holder, factory() as contender:
        assert await SharedCatalogGrantDAO.try_acquire_transaction_lock(
            holder,
            tenant_slug="polotsk",
            storefront_slug="main",
        )
        with pytest.raises(SharedCatalogGrantBlockedError, match="Another"):
            await SharedCatalogGrantService.execute(
                contender,
                desired_status="active",
                manifest=manifest,
                plan_token=plan["plan_token"],
            )
        await contender.rollback()
        await holder.rollback()
