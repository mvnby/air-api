from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from crud.public_catalog_checkout import PublicCatalogCheckoutDAO
from crud.tenant_offer import TenantOfferDAO
from models import Product, Storefront, TenantOffer
from models.tenancy import TenantScope
from services.orsha_storefront_bootstrap_service import (
    OrshaStorefrontBootstrapService,
)
from services.tenant_offer_service import TenantOfferService


_HOSTNAME = "orsha-internal.mvn.by"


async def _seed_active_orsha(session: AsyncSession) -> tuple[int, int, int]:
    products = [
        Product(
            title=f"Lock order product {index}",
            slug=f"lock-order-product-{index}",
            price=10_000 + index,
            is_published=True,
        )
        for index in range(5)
    ]
    session.add_all(products)
    await session.flush()
    offer_specs = [
        {
            "product_id": int(product.id),
            "price": 11_000 + index,
            "old_price": 12_000 + index,
            "is_published": True,
        }
        for index, product in enumerate(products)
    ]

    bootstrap = await OrshaStorefrontBootstrapService.plan(
        session,
        action="bootstrap",
        hostname=_HOSTNAME,
        offer_specs=offer_specs,
    )
    assert bootstrap["ready"] is True, bootstrap["blockers"]
    await OrshaStorefrontBootstrapService.execute(
        session,
        action="bootstrap",
        hostname=_HOSTNAME,
        plan_token=bootstrap["plan_token"],
        offer_specs=offer_specs,
    )
    await session.commit()

    activation = await OrshaStorefrontBootstrapService.plan(
        session,
        action="activate",
        hostname=_HOSTNAME,
        offer_specs=offer_specs,
    )
    assert activation["ready"] is True, activation["blockers"]
    await OrshaStorefrontBootstrapService.execute(
        session,
        action="activate",
        hostname=_HOSTNAME,
        plan_token=activation["plan_token"],
        offer_specs=offer_specs,
    )
    await session.commit()

    storefront = await session.scalar(
        select(Storefront).where(Storefront.slug == "orsha")
    )
    assert storefront is not None and storefront.id is not None
    offer = await session.scalar(
        select(TenantOffer).where(
            TenantOffer.storefront_id == int(storefront.id),
            TenantOffer.product_id == int(products[0].id),
        )
    )
    assert offer is not None and offer.id is not None
    return int(storefront.id), int(products[0].id), int(offer.id)


@pytest.mark.asyncio
async def test_checkout_and_offer_writer_share_storefront_first_lock_order(
    db_engine,
    monkeypatch,
) -> None:
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as seed:
        storefront_id, product_id, offer_id = await _seed_active_orsha(seed)

    scope = TenantScope(
        tenant_id=1,
        storefront_id=storefront_id,
        is_system=True,
        is_canonical_storefront=False,
    )
    checkout_has_storefront_lock = asyncio.Event()
    release_checkout = asyncio.Event()
    writer_reached_storefront_lock = asyncio.Event()
    original_checkout_lock = (
        PublicCatalogCheckoutDAO.lock_active_storefront_currency
    )
    original_writer_lock = TenantOfferDAO.lock_scope_storefront

    async def hold_checkout_after_storefront_lock(session, *, tenant_scope):
        currency = await original_checkout_lock(
            session,
            tenant_scope=tenant_scope,
        )
        if session.info.get("lock_order_role") == "checkout":
            checkout_has_storefront_lock.set()
            await release_checkout.wait()
        return currency

    async def signal_writer_before_storefront_lock(session, *, tenant_scope):
        if session.info.get("lock_order_role") == "writer":
            writer_reached_storefront_lock.set()
        return await original_writer_lock(
            session,
            tenant_scope=tenant_scope,
        )

    monkeypatch.setattr(
        PublicCatalogCheckoutDAO,
        "lock_active_storefront_currency",
        staticmethod(hold_checkout_after_storefront_lock),
    )
    monkeypatch.setattr(
        TenantOfferDAO,
        "lock_scope_storefront",
        staticmethod(signal_writer_before_storefront_lock),
    )

    async def checkout():
        async with factory() as session:
            session.info["lock_order_role"] = "checkout"
            snapshots = await PublicCatalogCheckoutDAO.get_offer_snapshots_by_ids(
                session,
                tenant_scope=scope,
                product_ids={product_id},
            )
            await session.commit()
            return snapshots[product_id]

    async def update_offer():
        async with factory() as session:
            session.info["lock_order_role"] = "writer"
            return await TenantOfferService.update_offer(
                session,
                offer_id=offer_id,
                payload={"price": 13_500, "old_price": 14_000},
                tenant_scope=scope,
                actor_username="lock-order-manager",
                actor_staff_user_id=None,
            )

    checkout_task = asyncio.create_task(checkout())
    await asyncio.wait_for(checkout_has_storefront_lock.wait(), timeout=2)
    writer_task = asyncio.create_task(update_offer())
    await asyncio.wait_for(writer_reached_storefront_lock.wait(), timeout=2)
    await asyncio.sleep(0.1)
    assert writer_task.done() is False

    release_checkout.set()
    snapshot, updated = await asyncio.wait_for(
        asyncio.gather(checkout_task, writer_task),
        timeout=5,
    )

    assert snapshot.unit_price == 11_000
    assert snapshot.currency == "BYN"
    assert updated["price"] == 13_500
    async with factory() as verification:
        stored = await verification.get(TenantOffer, offer_id)
        assert stored is not None
        assert stored.price == 13_500
