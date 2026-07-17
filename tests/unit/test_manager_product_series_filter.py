from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import Brand, Product, ProductSeries
from services.product_manager_service import ProductManagerService


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'manager_product_series_filter.db'}",
        echo=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_manager_product_list_filters_by_exact_series(sqlite_session: AsyncSession):
    brand = Brand(title="MDV", slug="mdv", is_published=True)
    sqlite_session.add(brand)
    await sqlite_session.flush()

    target_series = ProductSeries(title="Forest On", slug="forest-on", brand_id=brand.id)
    other_series = ProductSeries(title="Integra Pro", slug="integra-pro", brand_id=brand.id)
    sqlite_session.add_all([target_series, other_series])
    await sqlite_session.flush()

    sqlite_session.add_all(
        [
            Product(
                title="MDV Forest On 09",
                slug="mdv-forest-on-09",
                price=1600,
                brand_id=brand.id,
                series_id=target_series.id,
                is_published=True,
            ),
            Product(
                title="MDV Integra Pro 09",
                slug="mdv-integra-pro-09",
                price=1800,
                brand_id=brand.id,
                series_id=other_series.id,
                is_published=True,
            ),
        ]
    )
    await sqlite_session.commit()

    result = await ProductManagerService.get_manager_list(
        sqlite_session,
        page=1,
        limit=20,
        series_id=target_series.id,
        sort="title",
    )

    assert result["meta"]["total"] == 1
    assert [item["title"] for item in result["items"]] == ["MDV Forest On 09"]
