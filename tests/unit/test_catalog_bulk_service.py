from __future__ import annotations

from copy import deepcopy

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

import models  # noqa: F401
from api_contracts.catalog_bulk import CatalogBulkChange, CatalogBulkPreviewRequest
from models import (
    Brand,
    Feature,
    FeatureCategory,
    FeatureProductLink,
    FeatureSeriesLink,
    Product,
    ProductSeries,
)
from services.catalog_bulk_service import CatalogBulkConflict, CatalogBulkService
from services.product_write_service import ProductWriteService


@pytest.fixture
async def bulk_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def make_products(session: AsyncSession, count: int = 2) -> list[Product]:
    products = [
        Product(
            title=f"Bulk {index}",
            slug=f"bulk-{index}",
            price=1_000 + index,
            specs={"area_m2": 20 + index},
            is_published=True,
        )
        for index in range(1, count + 1)
    ]
    session.add_all(products)
    await session.commit()
    return products


def request(product_ids: list[int], change: CatalogBulkChange) -> CatalogBulkPreviewRequest:
    return CatalogBulkPreviewRequest(product_ids=product_ids, change=change)


@pytest.mark.asyncio
async def test_preview_returns_actual_before_after_without_persisting(bulk_session):
    products = await make_products(bulk_session)
    change = CatalogBulkChange(kind="publication", is_published=False)

    preview = await CatalogBulkService.preview(
        bulk_session,
        request([int(product.id) for product in products], change),
        actor="manager:1",
    )

    assert preview["changed_count"] == 2
    assert [item["before"] for item in preview["items"]] == [
        {"is_published": True},
        {"is_published": True},
    ]
    assert [item["after"] for item in preview["items"]] == [
        {"is_published": False},
        {"is_published": False},
    ]
    bulk_session.expire_all()
    persisted = list((await bulk_session.execute(select(Product).order_by(Product.id))).scalars().all())
    assert [product.is_published for product in persisted] == [True, True]


@pytest.mark.asyncio
async def test_apply_requires_same_actor_and_rejects_stale_preview(bulk_session):
    product = (await make_products(bulk_session, count=1))[0]
    change = CatalogBulkChange(kind="publication", is_published=False)
    preview = await CatalogBulkService.preview(
        bulk_session,
        request([int(product.id)], change),
        actor="manager:1",
    )

    with pytest.raises(ValueError, match="недействителен"):
        await CatalogBulkService.apply(bulk_session, preview["token"], actor="manager:2")

    product.is_published = False
    bulk_session.add(product)
    await bulk_session.commit()

    with pytest.raises(CatalogBulkConflict, match="изменились"):
        await CatalogBulkService.apply(bulk_session, preview["token"], actor="manager:1")


@pytest.mark.asyncio
async def test_apply_rolls_back_all_products_when_a_later_writer_fails(bulk_session, monkeypatch):
    products = await make_products(bulk_session)
    change = CatalogBulkChange(kind="publication", is_published=False)
    preview = await CatalogBulkService.preview(
        bulk_session,
        request([int(product.id) for product in products], change),
        actor="manager:1",
    )
    original_update = ProductWriteService.update_product
    calls = 0

    async def fail_second_write(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("forced second write failure")
        return await original_update(*args, **kwargs)

    monkeypatch.setattr(ProductWriteService, "update_product", staticmethod(fail_second_write))
    with pytest.raises(RuntimeError, match="forced second write failure"):
        await CatalogBulkService.apply(bulk_session, preview["token"], actor="manager:1")

    bulk_session.expire_all()
    persisted = list((await bulk_session.execute(select(Product).order_by(Product.id))).scalars().all())
    assert [product.is_published for product in persisted] == [True, True]


@pytest.mark.asyncio
async def test_specs_remove_clears_aliases_and_derived_metadata(bulk_session):
    product = (await make_products(bulk_session, count=1))[0]
    product_id = int(product.id)
    product.specs = {
        "Обслуживаемая площадь": 25,
        "area_m2": 25,
        "Wi-Fi": True,
        "wifi_ready": True,
        "wifi_builtin": True,
        "wifi_state": "builtin",
        "__filter_wifi": True,
        "__typed_specs": {
            "area_m2": {"type": "number", "value": 25},
            "wifi_state": {"type": "state", "value": "builtin"},
        },
    }
    bulk_session.add(product)
    await bulk_session.commit()
    change = CatalogBulkChange(
        kind="specs",
        specs={"Площадь охлаждения": "", "Wi-Fi": ""},
        spec_mode="remove",
    )

    preview = await CatalogBulkService.preview(
        bulk_session,
        request([product_id], change),
        actor="manager:1",
    )
    assert preview["items"][0]["before"] == {
        "area_m2": 25,
        "wifi_builtin": True,
        "wifi_ready": True,
        "wifi_state": "builtin",
    }
    assert preview["items"][0]["after"] == {
        "area_m2": None,
        "wifi_builtin": False,
        "wifi_ready": False,
        "wifi_state": "none",
    }

    await CatalogBulkService.apply(bulk_session, preview["token"], actor="manager:1")
    bulk_session.expire_all()
    persisted = await bulk_session.get(Product, product_id)
    assert persisted is not None
    assert "area_m2" not in persisted.specs
    assert "Обслуживаемая площадь" not in persisted.specs
    assert persisted.specs["__filter_wifi"] is False
    assert "area_m2" not in persisted.specs.get("__typed_specs", {})
    assert persisted.specs["__typed_specs"]["wifi_state"]["value"] == "none"
    assert "brand" not in persisted.specs
    assert persisted.brand_id is None
    assert persisted.series_id is None


@pytest.mark.asyncio
async def test_specs_keep_authoritative_inverter_and_cooling_fields_in_sync(bulk_session):
    product = (await make_products(bulk_session, count=1))[0]
    product_id = int(product.id)
    product.is_inverter = False
    product.power_cooling = 2.0
    bulk_session.add(product)
    await bulk_session.commit()
    change = CatalogBulkChange(
        kind="specs",
        specs={"Инвертор": "да", "Мощность охлаждения": "3,5 кВт"},
    )

    preview = await CatalogBulkService.preview(
        bulk_session,
        request([product_id], change),
        actor="manager:1",
    )
    assert preview["items"][0]["before"]["is_inverter"] is False
    assert preview["items"][0]["after"]["is_inverter"] is True
    assert preview["items"][0]["before"]["power_cooling"] == 2.0
    assert preview["items"][0]["after"]["power_cooling"] == 3.5

    await CatalogBulkService.apply(bulk_session, preview["token"], actor="manager:1")
    bulk_session.expire_all()
    persisted = await bulk_session.get(Product, product_id)
    assert persisted is not None
    assert persisted.is_inverter is True
    assert persisted.power_cooling == 3.5
    assert persisted.specs["inverter"] is True
    assert persisted.specs["capacity_cooling_kw"] == "3.5"


@pytest.mark.asyncio
async def test_feature_inherit_restores_series_feature_and_is_idempotent(bulk_session):
    brand = Brand(title="Feature brand", slug="feature-brand")
    category = FeatureCategory(slug="feature-category", name="Feature category")
    bulk_session.add_all([brand, category])
    await bulk_session.flush()
    series = ProductSeries(title="Feature series", slug="feature-series", brand_id=brand.id)
    product = Product(
        title="Feature product",
        slug="feature-product",
        price=1_000,
        brand_id=brand.id,
        series_id=series.id,
        series_assignment_source="manual",
    )
    feature = Feature(
        slug="feature-inherit",
        name="Feature inherit",
        category_id=category.id,
        scope_type="series",
    )
    bulk_session.add_all([series, product, feature])
    await bulk_session.flush()
    product.series_id = series.id
    bulk_session.add_all([
        FeatureSeriesLink(series_id=series.id, feature_id=feature.id, is_enabled=True),
        FeatureProductLink(product_id=product.id, feature_id=feature.id, source="manual", is_enabled=False),
    ])
    await bulk_session.commit()
    feature_id = int(feature.id)
    change = CatalogBulkChange(kind="features", feature_ids=[feature_id], feature_mode="inherit")

    preview = await CatalogBulkService.preview(
        bulk_session,
        request([int(product.id)], change),
        actor="manager:1",
    )
    assert preview["changed_count"] == 1
    assert preview["items"][0]["before"]["features"] == []
    assert preview["items"][0]["after"]["features"] == [feature_id]
    await CatalogBulkService.apply(bulk_session, preview["token"], actor="manager:1")
    remaining = list((await bulk_session.execute(select(FeatureProductLink))).scalars().all())
    assert remaining == []

    repeated = await CatalogBulkService.preview(
        bulk_session,
        request([int(product.id)], change),
        actor="manager:1",
    )
    assert repeated["changed_count"] == 0
    result = await CatalogBulkService.apply(bulk_session, repeated["token"], actor="manager:1")
    assert result["updated"] == 0


@pytest.mark.asyncio
async def test_repeating_the_same_feature_add_is_a_real_noop(bulk_session):
    category = FeatureCategory(slug="noop-feature-category", name="Noop feature category")
    product = Product(title="Noop feature product", slug="noop-feature-product", price=1_000)
    bulk_session.add_all([category, product])
    await bulk_session.flush()
    feature = Feature(
        slug="noop-feature",
        name="Noop feature",
        category_id=category.id,
        scope_type="universal",
    )
    bulk_session.add(feature)
    await bulk_session.flush()
    bulk_session.add(
        FeatureProductLink(product_id=product.id, feature_id=feature.id, source="manual", is_enabled=True)
    )
    await bulk_session.commit()
    change = CatalogBulkChange(kind="features", feature_ids=[int(feature.id)], feature_mode="add")

    preview = await CatalogBulkService.preview(
        bulk_session,
        request([int(product.id)], change),
        actor="manager:1",
    )
    assert preview["changed_count"] == 0
    result = await CatalogBulkService.apply(bulk_session, preview["token"], actor="manager:1")
    assert result == {"updated": 0, "product_ids": []}


@pytest.mark.asyncio
async def test_relations_reject_series_from_another_brand_without_writing(bulk_session):
    product = (await make_products(bulk_session, count=1))[0]
    product_id = int(product.id)
    first_brand = Brand(title="First", slug="first")
    second_brand = Brand(title="Second", slug="second")
    bulk_session.add_all([first_brand, second_brand])
    await bulk_session.flush()
    foreign_series = ProductSeries(title="Foreign", slug="foreign", brand_id=second_brand.id)
    bulk_session.add(foreign_series)
    await bulk_session.commit()
    before = deepcopy(product.specs)
    change = CatalogBulkChange(
        kind="relations",
        brand_id=first_brand.id,
        series_id=foreign_series.id,
    )

    with pytest.raises(ValueError, match="не принадлежит"):
        await CatalogBulkService.preview(
            bulk_session,
            request([product_id], change),
            actor="manager:1",
        )
    bulk_session.expire_all()
    persisted = await bulk_session.get(Product, product_id)
    assert persisted is not None
    assert persisted.brand_id is None
    assert persisted.series_id is None
    assert persisted.specs == before


@pytest.mark.asyncio
async def test_bulk_explicit_category_synchronizes_filter_tags(bulk_session):
    from crud.product import ProductDAO
    product = (await make_products(bulk_session, count=1))[0]
    product_id = int(product.id)
    preview = await CatalogBulkService.preview(
        bulk_session,
        request([product_id], CatalogBulkChange(kind="category", category="cat-industrial")),
        actor="manager:1",
    )
    assert preview["changed_count"] == 1
    assert preview["items"][0]["after"]["tags"]
    await CatalogBulkService.apply(bulk_session, preview["token"], actor="manager:1")
    bulk_session.expire_all()
    persisted = await ProductDAO.get_by_id(bulk_session, product_id)
    assert persisted.catalog_category_override == "cat-industrial"
    assert "cat-industrial" in {tag.slug for tag in persisted.tags}
