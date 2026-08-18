from __future__ import annotations

import json

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from crud.storefront_onboarding import StorefrontOnboardingDAO
from models import (
    Customer,
    IntegrationOutboxEvent,
    Lead,
    Order,
    Product,
    Storefront,
    StorefrontCatalogRevision,
    StorefrontDomain,
    Tenant,
    TenantAuditEvent,
    TenantOffer,
)
from services.catalog_invalidation_contracts import (
    CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
)
from services.storefront_onboarding_manifest import StorefrontOnboardingManifest
from services.storefront_onboarding_service import (
    StorefrontOnboardingBlockedError,
    StorefrontOnboardingService,
)


HOSTNAME = "polotsk.mvn.by"


def _manifest(offers: list[dict] | None = None) -> StorefrontOnboardingManifest:
    return StorefrontOnboardingManifest.normalize(
        {
            "version": 1,
            "tenant": {
                "slug": "polotsk",
                "display_name": "MVN Полоцк",
                "kind": "independent_seller",
                "is_system": False,
                "lifecycle": "managed",
            },
            "storefront": {
                "slug": "main",
                "display_name": "MVN Полоцк",
                "city": "Полоцк",
                "default_locale": "ru-BY",
                "currency": "BYN",
                "is_default": True,
            },
            "allowed_hostnames": [HOSTNAME],
            "offers": offers or [],
        }
    )


async def _seed_products(
    session: AsyncSession,
    *,
    count: int = 3,
) -> tuple[list[Product], list[dict]]:
    products = [
        Product(
            title=f"Polotsk product {index}",
            slug=f"polotsk-product-{index}",
            price=10_000 + index,
            is_published=True,
        )
        for index in range(count)
    ]
    session.add_all(products)
    await session.flush()
    offers = [
        {
            ("product_id" if index % 2 else "product_slug"): (
                int(product.id) if index % 2 else product.slug
            ),
            "price": 11_000 + index,
            "old_price": 12_000 + index,
            "is_published": index < 2,
        }
        for index, product in enumerate(products)
    ]
    return products, offers


async def _execute(
    session: AsyncSession,
    *,
    action: str,
    manifest: StorefrontOnboardingManifest,
) -> dict:
    plan = await StorefrontOnboardingService.plan(
        session,
        action=action,
        hostname=HOSTNAME,
        manifest=manifest,
    )
    assert plan["ready"] is True, plan["blockers"]
    return await StorefrontOnboardingService.execute(
        session,
        action=action,
        hostname=HOSTNAME,
        manifest=manifest,
        plan_token=plan["plan_token"],
    )


async def _count(session: AsyncSession, model) -> int:
    field = getattr(model, "id", None)
    if field is None:
        field = getattr(model, "event_id", None)
    if field is None:
        field = next(iter(model.__table__.primary_key.columns))
    return int((await session.execute(select(func.count(field)))).scalar_one())


@pytest.mark.asyncio
async def test_managed_tenant_full_lifecycle_is_reviewed_atomic_and_idempotent(
    db: AsyncSession,
) -> None:
    _, offers = await _seed_products(db)
    manifest = _manifest(offers)

    first_plan = await StorefrontOnboardingService.plan(
        db,
        action="bootstrap",
        hostname=HOSTNAME.upper() + ".",
        manifest=manifest,
    )
    repeated_plan = await StorefrontOnboardingService.plan(
        db,
        action="bootstrap",
        hostname=HOSTNAME,
        manifest=manifest,
    )
    assert first_plan["ready"] is True
    assert first_plan["plan_digest"] == repeated_plan["plan_digest"]
    assert first_plan["plan_token"] != repeated_plan["plan_token"]
    assert len(first_plan["changes"]) == 6
    assert first_plan["manifest_summary"]["tenant_is_system"] is False
    assert first_plan["manifest_summary"]["offer_count"] == 3
    json.dumps(first_plan)

    bootstrapped = await StorefrontOnboardingService.execute(
        db,
        action="bootstrap",
        hostname=HOSTNAME,
        manifest=manifest,
        plan_token=first_plan["plan_token"],
    )
    assert bootstrapped["changed_entities"] == 6
    assert bootstrapped["catalog_invalidation_staged"] is False
    assert bootstrapped["after"]["tenant"]["status"] == "active"
    assert bootstrapped["after"]["tenant"]["is_system"] is False
    assert bootstrapped["after"]["storefront"]["status"] == "draft"
    assert bootstrapped["after"]["domains"][0]["status"] == "pending"
    assert bootstrapped["after"]["domains"][0]["verified_at"] is None
    assert len(bootstrapped["after"]["offers"]) == 3
    assert await _count(db, TenantAuditEvent) == 6

    no_op = await _execute(db, action="bootstrap", manifest=manifest)
    assert no_op["changed_entities"] == 0
    assert await _count(db, TenantAuditEvent) == 6

    blocked_activation = await StorefrontOnboardingService.plan(
        db,
        action="activate",
        hostname=HOSTNAME,
        manifest=manifest,
    )
    assert blocked_activation["ready"] is False
    assert "verified before activation" in " ".join(
        blocked_activation["blockers"]
    )

    verified = await _execute(db, action="verify-domain", manifest=manifest)
    assert verified["changed_entities"] == 1
    assert verified["after"]["domains"][0]["status"] == "pending"
    assert verified["after"]["domains"][0]["verified_at"] is not None
    verify_no_op = await _execute(db, action="verify-domain", manifest=manifest)
    assert verify_no_op["changed_entities"] == 0

    activated = await _execute(db, action="activate", manifest=manifest)
    assert activated["changed_entities"] == 2
    assert activated["catalog_invalidation_staged"] is True
    assert activated["after"]["storefront"]["status"] == "active"
    assert activated["after"]["domains"][0]["status"] == "active"

    tenant = await db.scalar(select(Tenant).where(Tenant.slug == "polotsk"))
    storefront = await db.scalar(
        select(Storefront).where(
            Storefront.tenant_id == tenant.id,
            Storefront.slug == "main",
        )
    )
    revision = await db.get(
        StorefrontCatalogRevision,
        (int(tenant.id), int(storefront.id)),
    )
    events = list(
        (
            await db.execute(
                select(IntegrationOutboxEvent).where(
                    IntegrationOutboxEvent.event_type
                    == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
                    IntegrationOutboxEvent.aggregate_id
                    == f"{tenant.id}:{storefront.id}",
                )
            )
        ).scalars()
    )
    assert revision is not None and revision.revision == 1
    assert len(events) == 1
    assert events[0].payload["origins"] == ["https://polotsk.mvn.by"]
    assert events[0].payload["storefront_revision"] == 1
    assert await _count(db, TenantAuditEvent) == 9

    activation_no_op = await _execute(db, action="activate", manifest=manifest)
    assert activation_no_op["changed_entities"] == 0
    assert revision.revision == 1
    assert len(events) == 1


@pytest.mark.asyncio
async def test_stale_or_changed_manifest_token_is_rejected_before_writes(
    db: AsyncSession,
) -> None:
    products, offers = await _seed_products(db)
    manifest = _manifest(offers)
    plan = await StorefrontOnboardingService.plan(
        db,
        action="bootstrap",
        hostname=HOSTNAME,
        manifest=manifest,
    )
    products[0].is_published = False
    await db.flush()

    with pytest.raises(StorefrontOnboardingBlockedError, match="stale"):
        await StorefrontOnboardingService.execute(
            db,
            action="bootstrap",
            hostname=HOSTNAME,
            manifest=manifest,
            plan_token=plan["plan_token"],
        )

    assert await db.scalar(select(Tenant).where(Tenant.slug == "polotsk")) is None
    assert await _count(db, TenantOffer) == 0
    assert await _count(db, TenantAuditEvent) == 0


@pytest.mark.asyncio
async def test_hostname_owned_by_another_storefront_fails_closed(
    db: AsyncSession,
) -> None:
    foreign = Storefront(
        tenant_id=1,
        slug="foreign-polotsk",
        display_name="Foreign",
        status="draft",
        is_default=False,
    )
    db.add(foreign)
    await db.flush()
    db.add(
        StorefrontDomain(
            storefront_id=int(foreign.id),
            hostname=HOSTNAME,
            status="pending",
            is_primary=True,
        )
    )
    await db.flush()

    plan = await StorefrontOnboardingService.plan(
        db,
        action="bootstrap",
        hostname=HOSTNAME,
        manifest=_manifest(),
    )
    assert plan["ready"] is False
    assert "owned by another storefront" in " ".join(plan["blockers"])
    with pytest.raises(StorefrontOnboardingBlockedError, match="preflight"):
        await StorefrontOnboardingService.execute(
            db,
            action="bootstrap",
            hostname=HOSTNAME,
            manifest=_manifest(),
            plan_token=plan["plan_token"],
        )


@pytest.mark.asyncio
async def test_disable_preserves_rows_and_ignores_new_crm_traffic_for_token(
    db: AsyncSession,
) -> None:
    _, offers = await _seed_products(db)
    manifest = _manifest(offers)
    await _execute(db, action="bootstrap", manifest=manifest)
    await _execute(db, action="verify-domain", manifest=manifest)
    await _execute(db, action="activate", manifest=manifest)
    tenant = await db.scalar(select(Tenant).where(Tenant.slug == "polotsk"))
    storefront = await db.scalar(
        select(Storefront).where(Storefront.tenant_id == tenant.id)
    )
    customer = Customer(
        tenant_id=int(tenant.id),
        name="Polotsk customer",
        phone="+375290000001",
    )
    db.add(customer)
    await db.flush()
    db.add_all(
        [
            Lead(
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                request_text="before plan",
            ),
            Order(
                tenant_id=int(tenant.id),
                storefront_id=int(storefront.id),
                customer_id=int(customer.id),
                title="Polotsk order",
            ),
        ]
    )
    await db.flush()
    plan = await StorefrontOnboardingService.plan(
        db,
        action="disable",
        hostname=HOSTNAME,
        manifest=manifest,
    )
    db.add(
        Lead(
            tenant_id=int(tenant.id),
            storefront_id=int(storefront.id),
            request_text="after plan",
        )
    )
    await db.flush()

    disabled = await StorefrontOnboardingService.execute(
        db,
        action="disable",
        hostname=HOSTNAME,
        manifest=manifest,
        plan_token=plan["plan_token"],
    )
    assert disabled["catalog_invalidation_staged"] is True
    assert disabled["after"]["tenant"]["status"] == "disabled"
    assert disabled["after"]["storefront"]["status"] == "disabled"
    assert disabled["after"]["domains"][0]["status"] == "disabled"
    assert all(
        offer["status"] == "disabled" and offer["is_published"] is False
        for offer in disabled["after"]["offers"]
    )
    assert await _count(db, Tenant) == 2
    assert await _count(db, Storefront) == 2
    assert await _count(db, StorefrontDomain) == 1
    assert await _count(db, TenantOffer) == 3
    assert await _count(db, Customer) == 1
    assert await _count(db, Lead) == 2
    assert await _count(db, Order) == 1
    revision = await db.get(
        StorefrontCatalogRevision,
        (int(tenant.id), int(storefront.id)),
    )
    assert revision is not None and revision.revision == 2

    no_op = await _execute(db, action="disable", manifest=manifest)
    assert no_op["changed_entities"] == 0
    assert revision.revision == 2


@pytest.mark.asyncio
async def test_postgresql_advisory_locks_serialize_scope_and_hostname(
    db_engine,
) -> None:
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed:
        _, offers = await _seed_products(seed)
        manifest = _manifest(offers)
        await seed.commit()
    async with factory() as planner:
        plan = await StorefrontOnboardingService.plan(
            planner,
            action="bootstrap",
            hostname=HOSTNAME,
            manifest=manifest,
        )
        await planner.rollback()

    async with factory() as holder, factory() as contender:
        assert await StorefrontOnboardingDAO.try_acquire_transaction_locks(
            holder,
            tenant_slug="polotsk",
            storefront_slug="main",
            hostname=HOSTNAME,
        )
        with pytest.raises(StorefrontOnboardingBlockedError, match="Another"):
            await StorefrontOnboardingService.execute(
                contender,
                action="bootstrap",
                hostname=HOSTNAME,
                manifest=manifest,
                plan_token=plan["plan_token"],
            )
        await contender.rollback()
        await holder.rollback()


@pytest.mark.asyncio
async def test_activation_audit_revision_and_outbox_rollback_together(
    db_engine,
) -> None:
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed:
        _, offers = await _seed_products(seed)
        manifest = _manifest(offers)
        await _execute(seed, action="bootstrap", manifest=manifest)
        await _execute(seed, action="verify-domain", manifest=manifest)
        await seed.commit()

    async with factory() as transaction:
        activated = await _execute(
            transaction,
            action="activate",
            manifest=manifest,
        )
        assert activated["catalog_invalidation_staged"] is True
        assert await _count(transaction, StorefrontCatalogRevision) == 1
        assert await _count(transaction, IntegrationOutboxEvent) == 1
        activation_audits = int(
            (
                await transaction.execute(
                    select(func.count(TenantAuditEvent.id)).where(
                        TenantAuditEvent.action.in_(
                            {
                                "storefront.onboarding_activated",
                                "storefront_domain.onboarding_activated",
                            }
                        )
                    )
                )
            ).scalar_one()
        )
        assert activation_audits == 2
        await transaction.rollback()

    async with factory() as verification:
        tenant = await verification.scalar(
            select(Tenant).where(Tenant.slug == "polotsk")
        )
        storefront = await verification.scalar(
            select(Storefront).where(Storefront.tenant_id == tenant.id)
        )
        domain = await verification.scalar(
            select(StorefrontDomain).where(
                StorefrontDomain.storefront_id == storefront.id
            )
        )
        assert storefront.status == "draft"
        assert domain.status == "pending"
        assert domain.verified_at is not None
        assert await _count(verification, StorefrontCatalogRevision) == 0
        assert await _count(verification, IntegrationOutboxEvent) == 0
        activation_audits = int(
            (
                await verification.execute(
                    select(func.count(TenantAuditEvent.id)).where(
                        TenantAuditEvent.action.in_(
                            {
                                "storefront.onboarding_activated",
                                "storefront_domain.onboarding_activated",
                            }
                        )
                    )
                )
            ).scalar_one()
        )
        assert activation_audits == 0
