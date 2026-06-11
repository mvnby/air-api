from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from crud.product import ProductDAO
from models import (
    Brand,
    Product,
    ProductLocalStock,
    ProductSeries,
    ProductTagLink,
    Tag,
    TagGroup,
)
from services.catalog import CatalogService
from services.product_response_mapper import map_product_to_response
from services.product_series_service import ProductSeriesService


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    db_path = tmp_path / "public_product_series_payloads.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _seed_series_products(session: AsyncSession) -> dict[str, Product]:
    brand = Brand(title="MDV", slug="mdv", is_published=True)
    session.add(brand)
    await session.flush()

    series = ProductSeries(
        title="Elite",
        slug="elite",
        brand_id=brand.id,
        description="Quiet inverter product line",
        hero_image="/media/series/elite.webp",
        features=["Quiet mode", "Wi-Fi ready"],
        is_published=True,
    )
    session.add(series)
    await session.flush()

    main = Product(
        title="MDV Elite 35",
        slug="mdv-elite-35",
        price=1900,
        area=35,
        power_cooling=3.5,
        brand_id=brand.id,
        series_id=series.id,
        is_published=True,
    )
    sibling_25 = Product(
        title="MDV Elite 25",
        slug="mdv-elite-25",
        price=1500,
        area=25,
        power_cooling=2.6,
        brand_id=brand.id,
        series_id=series.id,
        is_published=True,
    )
    sibling_50 = Product(
        title="MDV Elite 50",
        slug="mdv-elite-50",
        price=2600,
        area=50,
        power_cooling=5.2,
        brand_id=brand.id,
        series_id=series.id,
        is_published=True,
    )
    other = Product(
        title="MDV Other 25",
        slug="mdv-other-25",
        price=1300,
        area=25,
        brand_id=brand.id,
        is_published=True,
    )
    session.add_all([main, sibling_25, sibling_50, other])
    await session.flush()

    session.add(
        ProductLocalStock(
            product_id=main.id,
            warehouse_code="vitebsk",
            qty=2,
            updated_by="test",
        )
    )
    await session.commit()

    return {
        "main": main,
        "sibling_25": sibling_25,
        "sibling_50": sibling_50,
        "other": other,
    }


@pytest.mark.asyncio
async def test_public_product_queries_eager_load_series_and_siblings(sqlite_session):
    seeded = await _seed_series_products(sqlite_session)

    detail = await ProductDAO.get_by_slug(
        sqlite_session,
        seeded["main"].slug,
        is_published=True,
        load_image_variants=True,
    )

    assert detail is not None
    assert "series" not in inspect(detail).unloaded
    detail_payload = map_product_to_response(detail)
    assert detail_payload.series is not None
    assert detail_payload.series.model_dump() == {
        "id": detail.series_id,
        "title": "Elite",
        "slug": "elite",
        "description": "Quiet inverter product line",
        "hero_image": "/media/series/elite.webp",
        "features": ["Quiet mode", "Wi-Fi ready"],
    }

    catalog_products = await ProductDAO.get_filtered(
        sqlite_session,
        is_published=True,
        sort="area_asc",
        limit=10,
        load_image_variants=True,
    )
    catalog_main = next(item for item in catalog_products if item.slug == seeded["main"].slug)
    assert "series" not in inspect(catalog_main).unloaded
    assert map_product_to_response(catalog_main).series.slug == "elite"

    featured = await CatalogService.get_vitebsk_featured_products(sqlite_session, limit=3)
    featured_main = next(item for item in featured if item.slug == seeded["main"].slug)
    assert "series" not in inspect(featured_main).unloaded
    assert map_product_to_response(featured_main).series.slug == "elite"

    siblings = await ProductSeriesService.get_series_siblings(sqlite_session, detail, limit=8)
    assert [item.slug for item in siblings] == ["mdv-elite-25", "mdv-elite-50"]


@pytest.mark.asyncio
async def test_public_series_navigation_builds_slug_sibling_map(sqlite_session):
    seeded = await _seed_series_products(sqlite_session)

    navigation = await ProductSeriesService.get_series_navigation(sqlite_session)

    main_item = navigation.products[seeded["main"].slug]
    assert main_item.series is not None
    assert main_item.series.slug == "elite"
    assert [item.slug for item in main_item.series_siblings] == [
        "mdv-elite-25",
        "mdv-elite-50",
    ]

    sibling_item = navigation.products[seeded["sibling_25"].slug]
    assert [item.slug for item in sibling_item.series_siblings] == [
        "mdv-elite-35",
        "mdv-elite-50",
    ]
    assert seeded["other"].slug not in navigation.products


@pytest.mark.asyncio
async def test_public_series_navigation_covers_legacy_series_sources(sqlite_session):
    specs_main = Product(
        title="Legacy Line 35",
        slug="legacy-line-35",
        price=1700,
        area=35,
        specs={"series": "Legacy Line"},
        is_published=True,
    )
    specs_sibling = Product(
        title="Legacy Line 25",
        slug="legacy-line-25",
        price=1400,
        area=25,
        specs={"series": "Legacy Line"},
        is_published=True,
    )
    specs_single = Product(
        title="Solo Line 25",
        slug="solo-line-25",
        price=1200,
        area=25,
        specs={"series": "Solo Line"},
        is_published=True,
    )
    tag_single = Product(
        title="Tagged Series 25",
        slug="tagged-series-25",
        price=1300,
        area=25,
        is_published=True,
    )
    tag_group = TagGroup(title="Series", slug="series")
    tag = Tag(title="Tagged Series", slug="tagged-series")
    sqlite_session.add_all([specs_main, specs_sibling, specs_single, tag_single, tag_group])
    await sqlite_session.flush()

    tag.group_id = tag_group.id
    sqlite_session.add(tag)
    await sqlite_session.flush()
    sqlite_session.add(ProductTagLink(product_id=tag_single.id, tag_id=tag.id))
    await sqlite_session.commit()

    navigation = await ProductSeriesService.get_series_navigation(sqlite_session)

    assert [item.slug for item in navigation.products[specs_main.slug].series_siblings] == [
        "legacy-line-25",
    ]
    assert navigation.products[specs_single.slug].series is None
    assert navigation.products[specs_single.slug].series_siblings == []
    assert navigation.products[tag_single.slug].series is None
    assert navigation.products[tag_single.slug].series_siblings == []
