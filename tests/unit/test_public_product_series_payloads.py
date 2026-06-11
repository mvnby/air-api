from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from crud.product import ProductDAO
from models import Brand, Product, ProductLocalStock, ProductSeries
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
