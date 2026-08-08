from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from crud.orsha_storefront_bootstrap import OrshaStorefrontBootstrapDAO
from crud.tenant_offer import TenantOfferDAO
from models import (
    Customer,
    Lead,
    Order,
    Product,
    Storefront,
    StorefrontDomain,
    TenantAuditEvent,
    TenantOffer,
)
from models.tenancy import TenantScope
from services.catalog_revision_service import CatalogRevisionService
from services.orsha_storefront_bootstrap_service import (
    OrshaStorefrontBootstrapBlockedError,
    OrshaStorefrontBootstrapService,
)
from services.orsha_storefront_lifecycle_staging import (
    OrshaStorefrontLifecycleStagingService,
)
from services.tenant_offer_service import TenantOfferService


HOSTNAME = "orsha-internal.mvn.by"


async def _seed_products(
    session: AsyncSession,
    *,
    count: int = 5,
) -> tuple[list[Product], list[dict]]:
    products = [
        Product(
            title=f"Orsha Canary {index}",
            slug=f"orsha-canary-{index}",
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
            "is_published": index < 3,
        }
        for index, product in enumerate(products)
    ]
    return products, offers


async def _execute(
    session: AsyncSession,
    *,
    action: str,
    offers: list[dict] | tuple = (),
) -> dict:
    plan = await OrshaStorefrontBootstrapService.plan(
        session,
        action=action,
        hostname=HOSTNAME,
        offer_specs=offers,
    )
    assert plan["ready"] is True, plan["blockers"]
    return await OrshaStorefrontBootstrapService.execute(
        session,
        action=action,
        hostname=HOSTNAME,
        plan_token=plan["plan_token"],
        offer_specs=offers,
    )


async def _count(session: AsyncSession, model) -> int:
    return int((await session.execute(select(func.count(model.id)))).scalar_one())


@pytest.mark.asyncio
async def test_bootstrap_is_reviewed_bounded_atomic_and_idempotent(
    db: AsyncSession,
) -> None:
    _, offers = await _seed_products(db)

    first_plan = await OrshaStorefrontBootstrapService.plan(
        db,
        action="bootstrap",
        hostname=HOSTNAME.upper() + ".",
        offer_specs=offers,
    )
    repeated_plan = await OrshaStorefrontBootstrapService.plan(
        db,
        action="bootstrap",
        hostname=HOSTNAME,
        offer_specs=offers,
    )

    assert first_plan == repeated_plan
    assert first_plan["ready"] is True
    assert len(first_plan["changes"]) == 7
    assert "_loaded_state" not in first_plan
    json.dumps(first_plan)

    result = await OrshaStorefrontBootstrapService.execute(
        db,
        action="bootstrap",
        hostname=HOSTNAME,
        plan_token=first_plan["plan_token"],
        offer_specs=offers,
    )
    assert result["changed_entities"] == 7
    assert result["catalog_invalidation_staged"] is False
    assert result["after"]["storefront"]["status"] == "draft"
    assert result["after"]["domains"][0]["status"] == "pending"
    assert len(result["after"]["offers"]) == 5

    storefront = (
        await db.execute(select(Storefront).where(Storefront.slug == "orsha"))
    ).scalar_one()
    domain = (
        await db.execute(
            select(StorefrontDomain).where(
                StorefrontDomain.storefront_id == storefront.id
            )
        )
    ).scalar_one()
    stored_offers = (
        await db.execute(
            select(TenantOffer)
            .where(TenantOffer.storefront_id == storefront.id)
            .order_by(TenantOffer.product_id)
        )
    ).scalars().all()
    assert storefront.tenant_id == 1
    assert storefront.is_default is False
    assert domain.hostname == HOSTNAME
    assert domain.is_primary is True
    assert len(stored_offers) == 5
    assert await _count(db, TenantAuditEvent) == 7

    no_op_plan = await OrshaStorefrontBootstrapService.plan(
        db,
        action="bootstrap",
        hostname=HOSTNAME,
        offer_specs=offers,
    )
    assert no_op_plan["changes"] == []
    no_op = await OrshaStorefrontBootstrapService.execute(
        db,
        action="bootstrap",
        hostname=HOSTNAME,
        plan_token=no_op_plan["plan_token"],
        offer_specs=offers,
    )
    assert no_op["changed_entities"] == 0
    assert await _count(db, TenantAuditEvent) == 7


@pytest.mark.asyncio
async def test_stale_bootstrap_token_is_rejected_before_any_write(
    db: AsyncSession,
) -> None:
    products, offers = await _seed_products(db)
    reviewed = await OrshaStorefrontBootstrapService.plan(
        db,
        action="bootstrap",
        hostname=HOSTNAME,
        offer_specs=offers,
    )
    products[0].is_published = False
    await db.flush()

    with pytest.raises(OrshaStorefrontBootstrapBlockedError, match="stale"):
        await OrshaStorefrontBootstrapService.execute(
            db,
            action="bootstrap",
            hostname=HOSTNAME,
            plan_token=reviewed["plan_token"],
            offer_specs=offers,
        )

    assert (
        await db.execute(select(Storefront).where(Storefront.slug == "orsha"))
    ).scalar_one_or_none() is None
    assert await _count(db, TenantOffer) == 0
    assert await _count(db, TenantAuditEvent) == 0


@pytest.mark.asyncio
async def test_activation_is_separate_exact_and_stages_one_batch_invalidation(
    db: AsyncSession,
    monkeypatch,
) -> None:
    _, offers = await _seed_products(db)
    await _execute(db, action="bootstrap", offers=offers)
    staged: list[dict] = []

    async def capture_stage(_session, **kwargs):
        staged.append(kwargs)
        return True

    monkeypatch.setattr(
        CatalogRevisionService,
        "stage_invalidation",
        capture_stage,
        raising=False,
    )
    activated = await _execute(db, action="activate", offers=offers)

    assert activated["changed_entities"] == 2
    assert activated["catalog_invalidation_staged"] is True
    assert activated["after"]["storefront"]["status"] == "active"
    assert activated["after"]["domains"][0]["status"] == "active"
    assert activated["after"]["domains"][0]["verified_at"] is not None
    assert len(staged) == 1
    assert staged[0]["reason"] == "orsha_storefront_activated"
    assert len(staged[0]["product_ids"]) == 5

    audit_count = await _count(db, TenantAuditEvent)
    no_op = await _execute(db, action="activate", offers=offers)
    assert no_op["changed_entities"] == 0
    assert len(staged) == 1
    assert await _count(db, TenantAuditEvent) == audit_count


@pytest.mark.asyncio
async def test_disable_preserves_crm_and_ignores_new_traffic_for_plan_token(
    db: AsyncSession,
    monkeypatch,
) -> None:
    _, offers = await _seed_products(db)
    await _execute(db, action="bootstrap", offers=offers)
    staged: list[str] = []

    async def capture_stage(_session, **kwargs):
        staged.append(kwargs["reason"])
        return {"staged": True}

    monkeypatch.setattr(
        CatalogRevisionService,
        "stage_invalidation",
        capture_stage,
        raising=False,
    )
    await _execute(db, action="activate", offers=offers)
    assert staged == ["orsha_storefront_activated"]
    staged.clear()
    storefront = (
        await db.execute(select(Storefront).where(Storefront.slug == "orsha"))
    ).scalar_one()
    customer = Customer(tenant_id=1, name="Orsha Customer", phone="+375290000001")
    db.add(customer)
    await db.flush()
    db.add_all(
        [
            Lead(
                tenant_id=1,
                storefront_id=int(storefront.id),
                request_text="first canary lead",
            ),
            Order(
                tenant_id=1,
                storefront_id=int(storefront.id),
                customer_id=int(customer.id),
                title="Orsha canary order",
            ),
        ]
    )
    await db.flush()
    reviewed = await OrshaStorefrontBootstrapService.plan(
        db,
        action="disable",
        hostname=HOSTNAME,
    )
    db.add(
        Lead(
            tenant_id=1,
            storefront_id=int(storefront.id),
            request_text="arrived after reviewed disable plan",
        )
    )
    await db.flush()
    result = await OrshaStorefrontBootstrapService.execute(
        db,
        action="disable",
        hostname=HOSTNAME,
        plan_token=reviewed["plan_token"],
    )

    assert result["catalog_invalidation_staged"] is True
    assert staged == ["orsha_storefront_disabled"]
    assert result["after"]["storefront"]["status"] == "disabled"
    assert result["after"]["domains"][0]["status"] == "disabled"
    assert all(
        offer["status"] == "disabled" and offer["is_published"] is False
        for offer in result["after"]["offers"]
    )
    assert await _count(db, Customer) == 1
    assert await _count(db, Lead) == 2
    assert await _count(db, Order) == 1
    assert await _count(db, Storefront) == 2
    assert await _count(db, TenantOffer) == 5

    audit_count = await _count(db, TenantAuditEvent)
    no_op = await _execute(db, action="disable")
    assert no_op["changed_entities"] == 0
    assert await _count(db, TenantAuditEvent) == audit_count


@pytest.mark.asyncio
async def test_routable_lifecycle_changes_fail_closed_without_invalidation_staging(
    db: AsyncSession,
    monkeypatch,
) -> None:
    _, offers = await _seed_products(db)
    await _execute(db, action="bootstrap", offers=offers)
    monkeypatch.delattr(CatalogRevisionService, "stage_invalidation", raising=False)

    activation = await OrshaStorefrontBootstrapService.plan(
        db,
        action="activate",
        hostname=HOSTNAME,
        offer_specs=offers,
    )

    assert activation["ready"] is False
    assert "invalidation staging is unavailable" in " ".join(
        activation["blockers"]
    )
    with pytest.raises(OrshaStorefrontBootstrapBlockedError, match="preflight"):
        await OrshaStorefrontBootstrapService.execute(
            db,
            action="activate",
            hostname=HOSTNAME,
            plan_token=activation["plan_token"],
            offer_specs=offers,
        )
    status = await OrshaStorefrontBootstrapService.status(db, hostname=HOSTNAME)
    assert status["state"]["storefront"]["status"] == "draft"
    assert status["state"]["domains"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_wrong_hostname_owner_fails_closed(
    db: AsyncSession,
) -> None:
    _, offers = await _seed_products(db)
    foreign = Storefront(
        tenant_id=1,
        slug="foreign",
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

    foreign_plan = await OrshaStorefrontBootstrapService.plan(
        db,
        action="bootstrap",
        hostname=HOSTNAME,
        offer_specs=offers,
    )
    assert foreign_plan["ready"] is False
    assert "owned by another storefront" in " ".join(foreign_plan["blockers"])
    with pytest.raises(OrshaStorefrontBootstrapBlockedError, match="preflight"):
        await OrshaStorefrontBootstrapService.execute(
            db,
            action="bootstrap",
            hostname=HOSTNAME,
            plan_token=foreign_plan["plan_token"],
            offer_specs=offers,
        )


@pytest.mark.asyncio
async def test_wrong_storefront_identity_fails_closed(
    db: AsyncSession,
) -> None:
    _, offers = await _seed_products(db)
    wrong = Storefront(
        tenant_id=1,
        slug="orsha",
        display_name="Wrong owner metadata",
        status="draft",
        city="Minsk",
        is_default=False,
    )
    db.add(wrong)
    await db.flush()
    wrong_plan = await OrshaStorefrontBootstrapService.plan(
        db,
        action="bootstrap",
        hostname=HOSTNAME,
        offer_specs=offers,
    )
    assert wrong_plan["ready"] is False
    assert any("ownership data" in value for value in wrong_plan["blockers"])


@pytest.mark.asyncio
async def test_bootstrap_rejects_offers_outside_reviewed_allowlist(
    db: AsyncSession,
) -> None:
    products, offers = await _seed_products(db, count=6)
    reviewed_offers = offers[:5]
    await _execute(db, action="bootstrap", offers=reviewed_offers)
    storefront = (
        await db.execute(select(Storefront).where(Storefront.slug == "orsha"))
    ).scalar_one()
    db.add(
        TenantOffer(
            tenant_id=1,
            storefront_id=int(storefront.id),
            product_id=int(products[5].id),
            price=15_000,
            is_published=False,
            status="active",
            created_by_username="unexpected",
            updated_by_username="unexpected",
        )
    )
    await db.flush()

    plan = await OrshaStorefrontBootstrapService.plan(
        db,
        action="bootstrap",
        hostname=HOSTNAME,
        offer_specs=reviewed_offers,
    )

    assert plan["ready"] is False
    assert any("outside the reviewed allowlist" in value for value in plan["blockers"])


@pytest.mark.asyncio
async def test_postgresql_advisory_lock_serializes_lifecycle_execute(
    db_engine,
) -> None:
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed:
        _, offers = await _seed_products(seed)
        await seed.commit()
    async with factory() as planner:
        reviewed = await OrshaStorefrontBootstrapService.plan(
            planner,
            action="bootstrap",
            hostname=HOSTNAME,
            offer_specs=offers,
        )
        await planner.rollback()

    async with factory() as lock_holder, factory() as contender:
        assert await OrshaStorefrontBootstrapDAO.try_acquire_transaction_lock(
            lock_holder
        )
        with pytest.raises(
            OrshaStorefrontBootstrapBlockedError,
            match="already running",
        ):
            await OrshaStorefrontBootstrapService.execute(
                contender,
                action="bootstrap",
                hostname=HOSTNAME,
                plan_token=reviewed["plan_token"],
                offer_specs=offers,
            )
        await contender.rollback()
        await lock_holder.rollback()


@pytest.mark.asyncio
async def test_scope_row_lock_blocks_concurrent_manager_offer_writer(
    db_engine,
    monkeypatch,
) -> None:
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed:
        products, offers = await _seed_products(seed, count=6)
        initial_offers = offers[:5]
        await _execute(seed, action="bootstrap", offers=initial_offers)
        storefront = (
            await seed.execute(select(Storefront).where(Storefront.slug == "orsha"))
        ).scalar_one()
        storefront_id = int(storefront.id)
        first_product_id = int(products[0].id)
        extra_product_id = int(products[5].id)
        initial_price = initial_offers[0]["price"]
        audit_count = await _count(seed, TenantAuditEvent)
        await seed.commit()

    reviewed_offers = [dict(value) for value in initial_offers]
    reviewed_offers[0]["price"] = int(initial_price) + 500
    async with factory() as holder, factory() as contender:
        reviewed = await OrshaStorefrontBootstrapService.plan(
            holder,
            action="bootstrap",
            hostname=HOSTNAME,
            offer_specs=reviewed_offers,
        )
        assert reviewed["ready"] is True
        staged = await OrshaStorefrontBootstrapService.execute(
            holder,
            action="bootstrap",
            hostname=HOSTNAME,
            plan_token=reviewed["plan_token"],
            offer_specs=reviewed_offers,
        )
        assert staged["changed_entities"] == 1

        lock_scope_storefront = TenantOfferDAO.lock_scope_storefront
        writer_reached_scope_lock = asyncio.Event()

        async def signaling_scope_lock(session, *, tenant_scope):
            if session is contender:
                writer_reached_scope_lock.set()
            return await lock_scope_storefront(
                session,
                tenant_scope=tenant_scope,
            )

        monkeypatch.setattr(
            TenantOfferDAO,
            "lock_scope_storefront",
            signaling_scope_lock,
        )
        writer_task = asyncio.create_task(
            TenantOfferService.upsert_offer(
                contender,
                payload={
                    "product_id": extra_product_id,
                    "price": 16_000,
                    "old_price": None,
                    "is_published": False,
                    "status": "active",
                },
                tenant_scope=TenantScope(
                    tenant_id=1,
                    storefront_id=storefront_id,
                    is_system=True,
                ),
                actor_username="concurrent-manager",
                actor_staff_user_id=None,
            )
        )
        writer_result = None
        try:
            await asyncio.wait_for(writer_reached_scope_lock.wait(), timeout=1)
            await asyncio.sleep(0.1)
            assert writer_task.done() is False
        finally:
            await holder.rollback()
            writer_result = await asyncio.wait_for(writer_task, timeout=2)

    assert writer_result["product_id"] == extra_product_id
    async with factory() as verification:
        first_offer = (
            await verification.execute(
                select(TenantOffer).where(
                    TenantOffer.storefront_id == storefront_id,
                    TenantOffer.product_id == first_product_id,
                )
            )
        ).scalar_one()
        assert first_offer.price == initial_price
        assert (
            await verification.execute(
                select(TenantOffer).where(
                    TenantOffer.storefront_id == storefront_id,
                    TenantOffer.product_id == extra_product_id,
                )
            )
        ).scalar_one() is not None
        assert await _count(verification, TenantOffer) == 6
        assert await _count(verification, TenantAuditEvent) == audit_count + 1


@pytest.mark.asyncio
async def test_caller_rollback_removes_partial_state_when_audit_staging_fails(
    db_engine,
    monkeypatch,
) -> None:
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed:
        _, offers = await _seed_products(seed)
        await seed.commit()
    async with factory() as session:
        reviewed = await OrshaStorefrontBootstrapService.plan(
            session,
            action="bootstrap",
            hostname=HOSTNAME,
            offer_specs=offers,
        )

        def fail_audit(*_args, **_kwargs) -> None:
            raise RuntimeError("simulated audit failure")

        monkeypatch.setattr(
            OrshaStorefrontLifecycleStagingService,
            "_add_audit",
            fail_audit,
        )
        with pytest.raises(RuntimeError, match="simulated audit failure"):
            await OrshaStorefrontBootstrapService.execute(
                session,
                action="bootstrap",
                hostname=HOSTNAME,
                plan_token=reviewed["plan_token"],
                offer_specs=offers,
            )
        await session.rollback()

    async with factory() as verification:
        assert (
            await verification.execute(
                select(Storefront).where(Storefront.slug == "orsha")
            )
        ).scalar_one_or_none() is None
        assert await _count(verification, StorefrontDomain) == 0
        assert await _count(verification, TenantOffer) == 0
        assert await _count(verification, TenantAuditEvent) == 0
