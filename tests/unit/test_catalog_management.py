from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from api_contracts.catalog_management import CatalogManagementFilters, CatalogManagementQuery
from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureCategory,
    FeatureProductLink,
    Product,
    ProductSeries,
)
from models.supplier import Supplier, SupplierOffer, ProductSupplierMapping
from services.catalog_management_service import CatalogManagementService
from services.product_supply_metrics_service import ProductSupplyMetricsService
from services.yandex_business_price_list_service import YandexBusinessPriceListService


@pytest.fixture
async def session(tmp_path: Path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'catalog-management.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(ProductSupplyMetricsService, "compute_for_products", AsyncMock(return_value={}))
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_drafts_search_series_and_selection_use_same_set(session):
    brand = Brand(title="Audit brand", slug="audit")
    session.add(brand)
    await session.flush()
    series = ProductSeries(title="Comfort", slug="comfort", brand_id=brand.id)
    session.add(series)
    await session.flush()
    target = Product(title="Draft unit", slug="draft", price=0, brand_id=brand.id, series_id=series.id, is_published=False)
    session.add_all([target, Product(title="Other", slug="other", price=100)])
    await session.commit()
    filters = CatalogManagementFilters(search="Audit Comfort", brand_ids=[brand.id], series_ids=[series.id], is_published=False, missing="price")
    result = await CatalogManagementService.query(session, CatalogManagementQuery(filters=filters, sort="title"))
    selected = await CatalogManagementService.selection(session, filters)
    assert result["meta"]["total"] == 1
    assert [item["id"] for item in result["items"]] == selected["product_ids"] == [target.id]


@pytest.mark.asyncio
async def test_supplier_filter_deduplicates_and_excludes_inactive_offers(session):
    supplier = Supplier(name="Test supply", code="test")
    session.add(supplier)
    product = Product(title="Model", slug="model", price=100)
    session.add(product)
    await session.flush()
    for external_id, active in [("first", True), ("second", True), ("disabled", False)]:
        session.add(SupplierOffer(supplier_id=supplier.id, external_id=external_id, qty=1, is_active=active))
        session.add(ProductSupplierMapping(product_id=product.id, supplier_id=supplier.id, external_id=external_id))
    await session.commit()
    result = await CatalogManagementService.query(session, CatalogManagementQuery(filters=CatalogManagementFilters(supplier_id=supplier.id, availability="in_stock"), sort="title"))
    assert result["meta"]["total"] == 1
    assert len(result["items"]) == 1
    supplier.is_active = False
    await session.commit()
    assert (await CatalogManagementService.selection(session, CatalogManagementFilters(supplier_id=supplier.id)))["total"] == 0


@pytest.mark.asyncio
async def test_filter_and_sort_are_applied_before_page_limit(session):
    session.add_all([Product(title=f"Unit {n}", slug=f"unit-{n}", price=n * 100, power_cooling=2.5 if n % 2 else 3.5, specs={"wifi_ready": "ready"}) for n in range(1, 7)])
    await session.commit()
    result = await CatalogManagementService.query(session, CatalogManagementQuery(filters=CatalogManagementFilters(cooling_btu_classes=[9], retail_min_byn=200, wifi="ready"), sort="price_desc", limit=1))
    assert result["meta"]["total"] == 2
    assert result["items"][0]["price"] == 500
    assert result["meta"]["pages"] == 2


def test_management_ranges_and_page_limits_are_validated():
    with pytest.raises(ValidationError):
        CatalogManagementFilters(area_min=50, area_max=20)
    with pytest.raises(ValidationError):
        CatalogManagementQuery(limit=101)
    with pytest.raises(ValidationError):
        CatalogManagementFilters(feature_id=1)
    with pytest.raises(ValidationError):
        CatalogManagementFilters(has_feature=True)


@pytest.mark.asyncio
async def test_effective_feature_filter_uses_inheritance_and_product_hide_for_count_pages_and_selection(session):
    brand = Brand(title="Feature brand", slug="feature-brand")
    category = FeatureCategory(slug="comfort", name="Comfort")
    session.add_all([brand, category])
    await session.flush()
    feature = Feature(name="Wi-Fi", slug="wifi", category_id=category.id, scope_type="brand", brand_id=brand.id)
    visible = Product(title="Visible", slug="visible", price=100, brand_id=brand.id)
    hidden = Product(title="Hidden", slug="hidden", price=200, brand_id=brand.id)
    other = Product(title="Other", slug="other-feature", price=300)
    session.add_all([feature, visible, hidden, other])
    await session.flush()
    session.add_all([
        FeatureBrandLink(brand_id=brand.id, feature_id=feature.id),
        FeatureProductLink(product_id=hidden.id, feature_id=feature.id, source="manual", is_enabled=False),
    ])
    await session.commit()

    present = CatalogManagementFilters(feature_id=feature.id, has_feature=True)
    page = await CatalogManagementService.query(session, CatalogManagementQuery(filters=present, sort="title", limit=1))
    selected = await CatalogManagementService.selection(session, present)
    assert page["meta"]["total"] == 1
    assert [item["id"] for item in page["items"]] == selected["product_ids"] == [visible.id]

    absent = await CatalogManagementService.selection(session, CatalogManagementFilters(feature_id=feature.id, has_feature=False))
    assert absent["product_ids"] == [hidden.id, other.id]


@pytest.mark.asyncio
async def test_yandex_membership_filter_reuses_current_offer_set_for_query_and_selection(session, monkeypatch):
    first = Product(title="In feed", slug="in-feed", price=100)
    second = Product(title="Outside feed", slug="outside-feed", price=100)
    session.add_all([first, second])
    await session.commit()
    monkeypatch.setattr(
        YandexBusinessPriceListService,
        "current_product_offer_ids",
        AsyncMock(return_value={first.id}),
    )
    filters = CatalogManagementFilters(in_yandex_feed=True)
    page = await CatalogManagementService.query(session, CatalogManagementQuery(filters=filters, sort="title"))
    selected = await CatalogManagementService.selection(session, filters)
    assert page["meta"]["total"] == 1
    assert [item["id"] for item in page["items"]] == selected["product_ids"] == [first.id]
    outside = await CatalogManagementService.selection(session, CatalogManagementFilters(in_yandex_feed=False))
    assert outside["product_ids"] == [second.id]
