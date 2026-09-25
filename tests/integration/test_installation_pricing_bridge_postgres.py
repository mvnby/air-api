"""PostgreSQL serialization of first publication and legacy installation checkout."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import func, select

from crud.public_write_idempotency import PublicWriteIdempotencyDAO
from crud.service_estimate import ServiceEstimateDAO
from models import InstallationPriceBook, InstallationRate, Order, Product, ServiceEstimate, ServiceTariff, ServiceTariffRule
from models.tenancy import TenantScope
from schemas import ManagerInstallEstimateSavePayload
from schemas_public_checkout import OrderPayload
from services.installation_price_book_service import InstallationPriceBookService as Book
from services.installation_pricing_service import InstallationPricingError
from services.service_estimate_service import ServiceEstimateService
from services.website_order_service import WebsiteOrderService


async def _seed_legacy_and_draft(session: AsyncSession) -> tuple[int, int]:
    product = Product(
        title="Legacy wall AC", slug="bridge-race-wall-ac", price=2000,
        product_kind="complete_split_system", is_published=True,
        specs={"type": "сплит-система", "indoor_type": "настенный",
               "capacity_cooling_kw": 3.5, "area_m2": 35},
    )
    rate = InstallationRate(
        category="Wall", power_range="07-12", base_price=250,
        extra_pipe_price=50, included_pipe_meters=3, is_fixed=True,
    )
    tariff = ServiceTariff(
        tenant_id=1, service_kind="installation",
        selector_label="Монтаж настенного комплекта", short_name="Монтаж настенного комплекта",
        installation_code="installation.wall.2_4", installation_price_mode="fixed",
        installation_match={"indoor_type": "wall", "capacity_min_kw": "2",
                            "capacity_max_kw": "4", "pipe_liquid": '1/4"',
                            "pipe_gas": '3/8"'},
        base_price=500, included_route_meters=3,
        included_holes_by_type={"diamond": 1},
    )
    session.add_all([product, rate, tariff])
    await session.flush()
    session.add_all([
        ServiceTariffRule(
            tariff_id=tariff.id, rule_type="per_meter_over_included",
            component_code="route.extra_m", name="Трасса", unit="м", unit_price=10.25,
        ),
        ServiceTariffRule(
            tariff_id=tariff.id, rule_type="per_hole_manual",
            component_code="hole.diamond.extra", name="Отверстие", unit_price=50,
        ),
    ])
    await session.commit()
    return int(product.id), int(rate.id)


def _legacy_payload(product_id: int, rate_id: int) -> OrderPayload:
    return OrderPayload.model_validate({
        "customer": {"name": "Legacy Buyer", "phone": "+375291112233"},
        "items": [{"product_id": product_id, "quantity": 1,
                   "with_installation": True, "installation_rate_id": rate_id,
                   "installation_price": 250, "installation_meta": {"meters": 3},
                   "installation_options": []}],
    })


@pytest.mark.asyncio
async def test_first_publication_commits_before_legacy_checkout_prices(db_engine, monkeypatch):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True,
                        is_canonical_storefront=True)
    async with factory() as setup:
        product_id, rate_id = await _seed_legacy_and_draft(setup)
    payload = _legacy_payload(product_id, rate_id)

    publisher_has_lock = asyncio.Event()
    release_publisher = asyncio.Event()
    checkout_claimed = asyncio.Event()
    checkout_entered_mutation = asyncio.Event()
    original_build = Book.build_entries_from_drafts.__func__
    original_claim = PublicWriteIdempotencyDAO.claim
    original_mutation = WebsiteOrderService._create_order_mutation

    async def pause_publisher(cls, session, current_scope):
        if session.info.get("publisher_race"):
            publisher_has_lock.set()
            await release_publisher.wait()
        return await original_build(cls, session, current_scope)

    async def watch_claim(session, **kwargs):
        result = await original_claim(session, **kwargs)
        if session.info.get("checkout_race"):
            checkout_claimed.set()
        return result

    async def watch_mutation(*args, **kwargs):
        checkout_entered_mutation.set()
        return await original_mutation(*args, **kwargs)

    monkeypatch.setattr(Book, "build_entries_from_drafts", classmethod(pause_publisher))
    monkeypatch.setattr(PublicWriteIdempotencyDAO, "claim", staticmethod(watch_claim))
    monkeypatch.setattr(WebsiteOrderService, "_create_order_mutation", staticmethod(watch_mutation))

    async def publish():
        async with factory() as session:
            session.info["publisher_race"] = True
            return await Book.publish(session, scope, actor="race-publisher")

    async def checkout():
        async with factory() as session:
            session.info["checkout_race"] = True
            return await WebsiteOrderService.create_order(
                session, payload, tenant_scope=scope, idempotency_key="bridge-first-publish-race",
            )

    publication = asyncio.create_task(publish())
    try:
        await asyncio.wait_for(publisher_has_lock.wait(), timeout=3)
        order_task = asyncio.create_task(checkout())
        await asyncio.wait_for(checkout_claimed.wait(), timeout=3)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(checkout_entered_mutation.wait(), timeout=0.3)
    finally:
        release_publisher.set()

    published = await asyncio.wait_for(publication, timeout=5)
    result = await asyncio.wait_for(
        asyncio.gather(order_task, return_exceptions=True), timeout=5,
    )
    assert published.revision == 1
    assert isinstance(result[0], InstallationPricingError)
    assert result[0].code == "book_preview_required"
    async with factory() as verify:
        assert await verify.scalar(select(func.count(Order.id))) == 0
        assert await verify.scalar(select(func.count(InstallationPriceBook.id))) == 1


@pytest.mark.asyncio
async def test_legacy_checkout_holds_publication_lock_until_order_commits(db_engine, monkeypatch):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True,
                        is_canonical_storefront=True)
    async with factory() as setup:
        product_id, rate_id = await _seed_legacy_and_draft(setup)
    payload = _legacy_payload(product_id, rate_id)

    order_created_before_commit = asyncio.Event()
    release_checkout = asyncio.Event()
    publication_started = asyncio.Event()
    publisher_has_lock = asyncio.Event()
    original_mutation = WebsiteOrderService._create_order_mutation
    original_build = Book.build_entries_from_drafts.__func__

    async def pause_checkout(*args, **kwargs):
        order = await original_mutation(*args, **kwargs)
        order_created_before_commit.set()
        await release_checkout.wait()
        return order

    async def watch_publisher(cls, session, current_scope):
        if session.info.get("publisher_race"):
            publisher_has_lock.set()
        return await original_build(cls, session, current_scope)

    monkeypatch.setattr(WebsiteOrderService, "_create_order_mutation", staticmethod(pause_checkout))
    monkeypatch.setattr(Book, "build_entries_from_drafts", classmethod(watch_publisher))

    async def checkout():
        async with factory() as session:
            return await WebsiteOrderService.create_order(
                session, payload, tenant_scope=scope, idempotency_key="bridge-checkout-first-race",
            )

    async def publish():
        async with factory() as session:
            session.info["publisher_race"] = True
            publication_started.set()
            return await Book.publish(session, scope, actor="race-publisher")

    order_task = asyncio.create_task(checkout())
    try:
        await asyncio.wait_for(order_created_before_commit.wait(), timeout=3)
        publication = asyncio.create_task(publish())
        await asyncio.wait_for(publication_started.wait(), timeout=3)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(publisher_has_lock.wait(), timeout=0.3)
    finally:
        release_checkout.set()

    order = await asyncio.wait_for(order_task, timeout=5)
    published = await asyncio.wait_for(publication, timeout=5)
    assert order.id is not None and published.revision == 1
    async with factory() as verify:
        assert await verify.scalar(select(func.count(Order.id))) == 1
        assert await verify.scalar(select(func.count(InstallationPriceBook.id))) == 1


@pytest.mark.asyncio
async def test_legacy_estimate_save_holds_first_publication_until_commit(db_engine, monkeypatch):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True,
                        is_canonical_storefront=True)
    async with factory() as setup:
        await _seed_legacy_and_draft(setup)
        tariff_id = int(await setup.scalar(select(ServiceTariff.id)))
    payload = ManagerInstallEstimateSavePayload(tariff_id=tariff_id)

    estimate_ready_before_commit = asyncio.Event()
    release_estimate = asyncio.Event()
    publication_started = asyncio.Event()
    publisher_has_lock = asyncio.Event()
    original_create = ServiceEstimateDAO.create
    original_build = Book.build_entries_from_drafts.__func__

    async def pause_create(session, estimate, items):
        estimate_ready_before_commit.set()
        await release_estimate.wait()
        return await original_create(session, estimate, items)

    async def watch_publisher(cls, session, current_scope):
        if session.info.get("publisher_race"):
            publisher_has_lock.set()
        return await original_build(cls, session, current_scope)

    monkeypatch.setattr(ServiceEstimateDAO, "create", staticmethod(pause_create))
    monkeypatch.setattr(Book, "build_entries_from_drafts", classmethod(watch_publisher))

    async def save_estimate():
        async with factory() as session:
            return await ServiceEstimateService.create_install_estimate(
                session, payload, created_by="manager", tenant_scope=scope,
            )

    async def publish():
        async with factory() as session:
            session.info["publisher_race"] = True
            publication_started.set()
            return await Book.publish(session, scope, actor="race-publisher")

    saving = asyncio.create_task(save_estimate())
    try:
        await asyncio.wait_for(estimate_ready_before_commit.wait(), timeout=3)
        publication = asyncio.create_task(publish())
        await asyncio.wait_for(publication_started.wait(), timeout=3)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(publisher_has_lock.wait(), timeout=0.3)
    finally:
        release_estimate.set()

    saved = await asyncio.wait_for(saving, timeout=5)
    published = await asyncio.wait_for(publication, timeout=5)
    assert saved.id is not None and published.revision == 1
    async with factory() as verify:
        assert await verify.scalar(select(func.count(ServiceEstimate.id))) == 1
