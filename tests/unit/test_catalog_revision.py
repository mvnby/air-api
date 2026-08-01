import os
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "password")

from core.database import get_session
from models import IntegrationOutboxEvent, Product, Storefront, Tenant
from routers.api_catalog_revision import router as catalog_revision_router
from routers.api_products import router as api_products_router
from services.catalog_revision_service import CatalogRevisionService
from services.manager_brand_service import ManagerBrandService
from services.product_service import ProductService
from services.product_write_service import ProductWriteService


@pytest_asyncio.fixture
async def sqlite_session(tmp_path: Path):
    db_path = tmp_path / "catalog_revision.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        tenant = Tenant(
            id=1,
            slug="mvn",
            display_name="MVN",
            kind="operator",
            status="active",
            is_system=True,
        )
        session.add(tenant)
        await session.flush()
        session.add(
            Storefront(
                id=1,
                tenant_id=1,
                slug="main",
                display_name="MVN",
                status="active",
                is_default=True,
            )
        )
        await session.commit()
        yield session

    await engine.dispose()


def _make_public_app(session: AsyncSession) -> FastAPI:
    app = FastAPI()
    app.include_router(catalog_revision_router, prefix="/api")
    app.include_router(api_products_router, prefix="/api")

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    return app


@pytest.mark.asyncio
async def test_public_revision_endpoint_shape_and_reads_do_not_bump(sqlite_session):
    app = _make_public_app(sqlite_session)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/api/v1/catalog/revision")
        second = await client.get("/api/v1/catalog/revision")
        conditional = await client.get(
            "/api/v1/catalog/revision",
            headers={"If-None-Match": 'W/"catalog-g0-s0"'},
        )

    assert first.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    assert set(first_payload) == {
        "revision",
        "storefront_revision",
        "cache_key",
        "updated_at",
    }
    assert first_payload["revision"] == 0
    assert first_payload["storefront_revision"] == 0
    assert first_payload["cache_key"] == "g0-s0"
    assert first_payload == second_payload
    assert first.headers["X-Catalog-Revision"] == "0"
    assert first.headers["X-Storefront-Catalog-Revision"] == "0"
    assert first.headers["ETag"] == 'W/"catalog-g0-s0"'
    assert first.headers["Cache-Control"] == "private, no-cache, max-age=0"
    assert first.headers["Vary"] == "X-MVN-Storefront-Host"
    assert conditional.status_code == 200

    before_manager_read = await CatalogRevisionService.get_current(sqlite_session)
    brands = await ManagerBrandService.list_brands(sqlite_session)
    after_manager_read = await CatalogRevisionService.get_current(sqlite_session)
    assert brands == []
    assert after_manager_read == before_manager_read


@pytest.mark.asyncio
async def test_product_update_and_brand_update_bump_revision(sqlite_session):
    product = Product(
        title="Revision Product",
        slug="revision-product",
        description="Demo",
        price=1000,
        specs={"area_m2": 25},
        is_published=True,
    )
    sqlite_session.add(product)
    await sqlite_session.commit()
    await sqlite_session.refresh(product)

    before = await CatalogRevisionService.get_current(sqlite_session)

    result = await ProductWriteService.update_product(
        sqlite_session,
        product.id,
        {"price": 1250},
    )
    assert result == {"message": "Product updated", "id": product.id}

    after_product_update = await CatalogRevisionService.get_current(sqlite_session)
    assert after_product_update["revision"] == before["revision"] + 1
    assert after_product_update["updated_at"] >= before["updated_at"]

    brand = await ManagerBrandService.create_brand(
        sqlite_session,
        {"title": "Revision Brand", "slug": "revision-brand"},
    )
    after_brand_create = await CatalogRevisionService.get_current(sqlite_session)

    await ManagerBrandService.update_brand(
        sqlite_session,
        brand["id"],
        {"title": "Revision Brand Updated"},
    )
    after_brand_update = await CatalogRevisionService.get_current(sqlite_session)
    assert after_brand_create["revision"] == after_product_update["revision"] + 1
    assert after_brand_update["revision"] == after_brand_create["revision"] + 1


@pytest.mark.asyncio
async def test_static_rebuild_status_tracks_catalog_publication(sqlite_session):
    initial = await CatalogRevisionService.get_static_rebuild_status(sqlite_session)
    assert initial["current_revision"] == 0
    assert initial["published_revision"] == 0
    assert initial["needs_rebuild"] is False
    assert initial["state"] == "fresh"

    bumped = await CatalogRevisionService.bump(sqlite_session, scope="test_catalog_change")
    stale = await CatalogRevisionService.get_static_rebuild_status(sqlite_session)
    assert stale["current_revision"] == bumped["revision"]
    assert stale["published_revision"] == 0
    assert stale["needs_rebuild"] is True
    assert stale["state"] == "stale"

    queued = await CatalogRevisionService.mark_static_rebuild_requested(
        sqlite_session,
        bumped["revision"],
    )
    assert queued["requested_revision"] == bumped["revision"]
    assert queued["needs_rebuild"] is True
    assert queued["state"] == "queued"

    fresh = await CatalogRevisionService.mark_static_rebuild_completed(
        sqlite_session,
        bumped["revision"],
    )
    assert fresh["published_revision"] == bumped["revision"]
    assert fresh["needs_rebuild"] is False
    assert fresh["state"] == "fresh"

    failed_revision = (
        await CatalogRevisionService.bump(sqlite_session, scope="test_failed_rebuild")
    )["revision"]
    failed = await CatalogRevisionService.mark_static_rebuild_failed(
        sqlite_session,
        failed_revision,
        "deploy failed",
    )
    assert failed["requested_revision"] == failed_revision
    assert failed["last_error"] == "deploy failed"
    assert failed["needs_rebuild"] is True
    assert failed["state"] == "stale"


@pytest.mark.asyncio
async def test_product_update_rolls_back_when_revision_bump_fails(sqlite_session, monkeypatch):
    product = Product(
        title="Rollback Revision Product",
        slug="rollback-revision-product",
        description="Demo",
        price=1000,
        specs={"area_m2": 25},
        is_published=True,
    )
    sqlite_session.add(product)
    await sqlite_session.commit()
    await sqlite_session.refresh(product)

    before = await CatalogRevisionService.get_current(sqlite_session)

    async def fail_bump(*args, **kwargs):
        raise RuntimeError("revision bump failed")

    monkeypatch.setattr(CatalogRevisionService, "bump", fail_bump)

    with pytest.raises(RuntimeError, match="revision bump failed"):
        await ProductWriteService.update_product(
            sqlite_session,
            product.id,
            {"price": 1250},
        )

    await sqlite_session.rollback()
    await sqlite_session.refresh(product)
    after = await CatalogRevisionService.get_current(sqlite_session)

    assert product.price == 1000
    assert after == before


@pytest.mark.asyncio
async def test_product_update_stages_durable_invalidation_without_network(
    sqlite_session,
    monkeypatch,
):
    product = Product(
        title="Post Commit Purge Product",
        slug="post-commit-purge-product",
        description="Demo",
        price=1000,
        specs={"area_m2": 25},
        is_published=True,
    )
    sqlite_session.add(product)
    await sqlite_session.commit()
    await sqlite_session.refresh(product)

    before = await CatalogRevisionService.get_current(sqlite_session)
    purge_calls: list[dict] = []

    async def fail_purge(**kwargs):
        purge_calls.append(kwargs)
        raise RuntimeError("cloudflare is temporarily unavailable")

    monkeypatch.setattr(
        "services.catalog_purge_service.CloudflareCatalogPurgeService.purge_urls",
        fail_purge,
    )

    result = await ProductWriteService.update_product(
        sqlite_session,
        product.id,
        {"price": 1250},
    )
    after = await CatalogRevisionService.get_current(sqlite_session)

    assert result == {"message": "Product updated", "id": product.id}
    assert after["revision"] == before["revision"] + 1
    assert purge_calls == []
    event = (
        await sqlite_session.execute(select(IntegrationOutboxEvent))
    ).scalar_one()
    assert event.status == "pending"
    assert event.payload["scope"] == "global"
    assert event.payload["reason"] == "product_update"
    assert event.payload["global_revision"] == after["revision"]
    assert "/product/post-commit-purge-product/" in event.payload["paths"]


@pytest.mark.asyncio
async def test_product_price_update_resolves_product_slug_for_outbox(sqlite_session):
    product = Product(
        title="Price Purge Product",
        slug="price-purge-product",
        description="Demo",
        price=1000,
        specs={"area_m2": 25},
        is_published=True,
    )
    sqlite_session.add(product)
    await sqlite_session.commit()
    await sqlite_session.refresh(product)

    updated = await ProductService.update_price(sqlite_session, product.id, 1300)

    assert updated is True
    event = (
        await sqlite_session.execute(select(IntegrationOutboxEvent))
    ).scalar_one()
    assert event.payload["reason"] == "product_price"
    assert "/product/price-purge-product/" in event.payload["paths"]


@pytest.mark.asyncio
async def test_public_product_detail_still_hides_unpublished_product(sqlite_session):
    product = Product(
        title="Hidden Revision Product",
        slug="hidden-revision-product",
        description="Draft",
        price=1000,
        specs={"area_m2": 25},
        is_published=False,
    )
    sqlite_session.add(product)
    await sqlite_session.commit()

    app = _make_public_app(sqlite_session)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/products/{product.slug}")

    assert response.status_code == 404
