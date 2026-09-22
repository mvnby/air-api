import pytest

from models import (
    Brand,
    Feature,
    FeatureCategory,
    FeatureProductLink,
    FeatureSeriesLink,
    Product,
    ProductSeries,
)
from services.feature_resolver_service import FeatureResolverService


@pytest.mark.asyncio
async def test_mixed_series_wifi_claim_moves_to_builtin_variant(db):
    brand = Brand(title="TCL scope fixture", slug="tcl-scope-fixture", is_published=True)
    category = FeatureCategory(slug="wifi-scope-fixture", name="Управление")
    db.add_all([brand, category])
    await db.flush()
    series = ProductSeries(brand_id=brand.id, slug="mixed-wifi-scope", title="Mixed Wi-Fi", is_published=True)
    feature = Feature(
        slug="vstroennyi-wi-fi-modul-scope-fixture",
        name="Встроенный Wi-Fi-модуль",
        category_id=category.id,
        scope_type="universal",
    )
    db.add_all([series, feature])
    await db.flush()
    builtin = Product(
        title="Built-in variant", slug="builtin-wifi-scope", price=1,
        brand_id=brand.id, series_id=series.id,
        specs={"wifi_ready": True, "wifi_state": "builtin"},
    )
    ready = Product(
        title="Optional variant", slug="ready-wifi-scope", price=1,
        brand_id=brand.id, series_id=series.id,
        specs={"wifi_ready": "ready", "wifi_state": "ready"},
    )
    db.add_all([builtin, ready])
    await db.flush()
    series_link = FeatureSeriesLink(series_id=series.id, feature_id=feature.id, source="manual", is_enabled=True)
    db.add(series_link)
    await db.flush()

    before = await FeatureResolverService.resolve_for_products(db, [builtin, ready])
    assert feature.slug in {item.slug for item in before[ready.id]["effective"]}

    series_link.is_enabled = False
    db.add(FeatureProductLink(product_id=builtin.id, feature_id=feature.id, source="manual", is_enabled=True))
    await db.flush()
    after = await FeatureResolverService.resolve_for_products(db, [builtin, ready])

    assert feature.slug in {item.slug for item in after[builtin.id]["effective"]}
    assert feature.slug not in {item.slug for item in after[ready.id]["effective"]}
