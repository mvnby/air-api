"""Real producer transactions must only notify public or proven old-public URLs."""
from __future__ import annotations

import pytest
from sqlalchemy import delete
from sqlmodel import select

from core.config import settings
from models import Brand, IntegrationOutboxEvent, Product, ProductSeries
from services.catalog_revision_service import CatalogRevisionService
from services.indexnow_service import INDEXNOW_EVENT_TYPE
from services.manager_brand_service import ManagerBrandService
from services.product_manager_service import ProductManagerService
from services.product_write_service import ProductWriteService

ORIGIN = "https://mvn.by"
LISTINGS = {ORIGIN + "/catalog/", ORIGIN + "/brands/"}


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "INDEXNOW_ENABLED", True)
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", ORIGIN)


async def take_urls(session):
    events = (await session.execute(select(IntegrationOutboxEvent).where(
        IntegrationOutboxEvent.event_type == INDEXNOW_EVENT_TYPE,
    ))).scalars().all()
    urls = {url for event in events for url in event.payload["urls"]}
    await session.execute(delete(IntegrationOutboxEvent).where(
        IntegrationOutboxEvent.event_type == INDEXNOW_EVENT_TYPE,
    ))
    await session.commit()
    return urls


@pytest.mark.asyncio
async def test_new_and_duplicated_drafts_and_repeated_draft_edits_are_excluded(db):
    result = await ProductWriteService.create_product(db, {
        "title": "Private draft", "slug": "private-draft", "price": 1000, "is_published": False, "brand_id": None, "series_id": None,
    })
    assert await take_urls(db) == LISTINGS
    for price in [1100, 1200]:
        await ProductWriteService.update_product(db, result["id"], {"price": price}, sync_derived_fields=False)
        assert await take_urls(db) == LISTINGS
    source = Product(title="Public source", slug="public-source", price=1000, is_published=True)
    db.add(source)
    await db.commit()
    await ProductWriteService.duplicate_product(db, source.id, {"slug": "private-copy", "brand_id": None, "series_id": None}, make_unpublished=True)
    assert await take_urls(db) == LISTINGS


@pytest.mark.asyncio
async def test_publish_rename_unpublish_and_draft_delete_preserve_only_real_public_history(db):
    product = Product(title="Model", slug="private", price=1000, is_published=False)
    db.add(product)
    await db.commit()
    await ProductWriteService.update_product(db, product.id, {"slug": "published", "is_published": True}, sync_derived_fields=False)
    assert await take_urls(db) == LISTINGS | {ORIGIN + "/product/published/"}
    await ProductWriteService.update_product(db, product.id, {"slug": "renamed"}, sync_derived_fields=False)
    assert await take_urls(db) == LISTINGS | {ORIGIN + "/product/published/", ORIGIN + "/product/renamed/"}
    await ProductWriteService.update_product(db, product.id, {"is_published": False}, sync_derived_fields=False)
    assert await take_urls(db) == LISTINGS | {ORIGIN + "/product/renamed/"}
    await ProductWriteService.update_product(db, product.id, {"slug": "private-again", "price": 1300}, sync_derived_fields=False)
    assert await take_urls(db) == LISTINGS
    assert await ProductManagerService.delete_for_manager(db, product.id)
    assert await take_urls(db) == LISTINGS


@pytest.mark.asyncio
async def test_deleting_last_published_product_keeps_product_and_former_public_brand(db):
    brand = Brand(title="Brand", slug="public-brand", is_published=True)
    db.add(brand)
    await db.flush()
    product = Product(title="Model", slug="deleted", price=1000, is_published=True, brand_id=brand.id)
    db.add(product)
    await db.commit()
    assert await ProductManagerService.delete_for_manager(db, product.id)
    assert await take_urls(db) == LISTINGS | {ORIGIN + "/product/deleted/", ORIGIN + "/brands/public-brand/"}
    await CatalogRevisionService.stage_invalidation(db, "unknown_old_slug", slugs=["never-public", "deleted"])
    await db.commit()
    assert await take_urls(db) == LISTINGS


@pytest.mark.asyncio
async def test_common_filter_excludes_hidden_and_empty_brands_and_hidden_series(db):
    hidden = Brand(title="Hidden", slug="hidden-brand", is_published=False)
    empty = Brand(title="Empty", slug="empty-brand", is_published=True)
    public = Brand(title="Public", slug="public-brand", is_published=True)
    db.add_all([hidden, empty, public])
    await db.flush()
    db.add_all([
        Product(title="Hidden brand model", slug="visible-model", price=1000, is_published=True, brand_id=hidden.id),
        Product(title="Public brand model", slug="public-model", price=1000, is_published=True, brand_id=public.id),
        ProductSeries(brand_id=hidden.id, title="Hidden brand series", slug="otherwise-public", is_published=True),
        ProductSeries(brand_id=public.id, title="Hidden series", slug="hidden-series", is_published=False),
        ProductSeries(brand_id=public.id, title="Public series", slug="public-series", is_published=True),
    ])
    await db.commit()
    paths = [
        "/brands/hidden-brand/", "/brands/empty-brand/", "/brands/public-brand/",
        "/brands/hidden-brand/series/otherwise-public/", "/brands/public-brand/series/hidden-series/",
        "/brands/public-brand/series/public-series/", "/product/visible-model/",
    ]
    await CatalogRevisionService.stage_invalidation(db, "visibility_test", additional_paths=paths)
    await db.commit()
    assert await take_urls(db) == LISTINGS | {
        ORIGIN + "/brands/public-brand/", ORIGIN + "/brands/public-brand/series/public-series/", ORIGIN + "/product/visible-model/",
    }


@pytest.mark.asyncio
async def test_brand_rename_and_hide_keep_old_public_brand_and_series_urls(db):
    brand = Brand(title="Brand", slug="old-brand", is_published=True)
    db.add(brand)
    await db.flush()
    db.add_all([
        Product(title="Model", slug="model", price=1000, is_published=True, brand_id=brand.id),
        ProductSeries(brand_id=brand.id, title="Public series", slug="series", is_published=True),
        ProductSeries(brand_id=brand.id, title="Hidden series", slug="secret", is_published=False),
    ])
    await db.commit()
    await ManagerBrandService.update_brand(db, brand.id, {"slug": "new-brand"})
    assert await take_urls(db) == LISTINGS | {
        ORIGIN + f"/brands/{slug}/{suffix}" for slug in ["old-brand", "new-brand"] for suffix in ["", "series/series/"]
    }
    await ManagerBrandService.update_brand(db, brand.id, {"is_published": False})
    assert await take_urls(db) == LISTINGS | {ORIGIN + "/brands/new-brand/", ORIGIN + "/brands/new-brand/series/series/"}
    await ManagerBrandService.update_brand(db, brand.id, {"description": "Still private"})
    assert await take_urls(db) == LISTINGS


@pytest.mark.asyncio
async def test_series_publish_rename_unpublish_and_delete_preserve_explicit_history(db):
    brand = Brand(title="Brand", slug="brand", is_published=True)
    db.add(brand)
    await db.commit()
    series = await ManagerBrandService.create_brand_series(db, brand.id, {"title": "Draft", "slug": "draft", "is_published": False})
    assert await take_urls(db) == LISTINGS
    await ManagerBrandService.update_brand_series(db, brand.id, series["id"], {"description": "Private edit"})
    assert await take_urls(db) == LISTINGS
    await ManagerBrandService.update_brand_series(db, brand.id, series["id"], {"slug": "public", "is_published": True})
    assert await take_urls(db) == LISTINGS | {ORIGIN + "/brands/brand/series/public/"}
    await ManagerBrandService.update_brand_series(db, brand.id, series["id"], {"slug": "renamed"})
    assert await take_urls(db) == LISTINGS | {ORIGIN + "/brands/brand/series/public/", ORIGIN + "/brands/brand/series/renamed/"}
    await ManagerBrandService.update_brand_series(db, brand.id, series["id"], {"is_published": False})
    assert await take_urls(db) == LISTINGS | {ORIGIN + "/brands/brand/series/renamed/"}
    await ManagerBrandService.delete_brand_series(db, brand.id, series["id"])
    assert await take_urls(db) == LISTINGS
    public = await ManagerBrandService.create_brand_series(db, brand.id, {"title": "Public", "slug": "deleted"})
    await take_urls(db)
    await ManagerBrandService.delete_brand_series(db, brand.id, public["id"])
    assert await take_urls(db) == LISTINGS | {ORIGIN + "/brands/brand/series/deleted/"}
