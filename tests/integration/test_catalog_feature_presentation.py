import pytest
from sqlalchemy import select

from core.config import settings
from models import Brand, Feature, FeatureCategory, FeatureProductLink, FeatureSeriesLink, Product, ProductSeries
from schemas_features import FeatureLinkPayload, FeatureTargetLinkPayload, ManagerFeatureSeriesAssignmentPayload
from services.feature_assignment_service import FeatureAssignmentService
from services.feature_resolver_service import FeatureResolverService
from services.manager_brand_series_feature_service import ManagerBrandSeriesFeatureOperations
from services.catalog_revision_service import CatalogRevisionService


@pytest.mark.asyncio
async def test_same_feature_has_contextual_modes_and_product_override(db, async_client):
    category = FeatureCategory(slug="presentation", name="Комфорт")
    brand = Brand(slug="presentation", title="Presentation")
    db.add_all([category, brand])
    await db.flush()
    feature = Feature(slug="turbo-presentation", name="Турбо", category_id=category.id,
                      short_description="Быстро охлаждает комнату", full_description="Полное описание",
                      icon_caption="Быстрое охлаждение")
    basic = ProductSeries(brand_id=brand.id, slug="basic", title="Basic")
    premium = ProductSeries(brand_id=brand.id, slug="premium", title="Premium")
    db.add_all([feature, basic, premium])
    await db.flush()
    basic_product = Product(brand_id=brand.id, series_id=basic.id, slug="basic-p", title="Basic", price=1000)
    premium_product = Product(brand_id=brand.id, series_id=premium.id, slug="premium-p", title="Premium", price=2000)
    db.add_all([basic_product, premium_product])
    await db.flush()
    db.add_all([
        FeatureSeriesLink(series_id=basic.id, feature_id=feature.id, display_mode="detailed"),
        FeatureSeriesLink(series_id=premium.id, feature_id=feature.id, display_mode="icon", is_featured=True),
    ])
    await db.commit()
    products = [basic_product, premium_product]
    result = await FeatureResolverService.resolve_for_products(db, products)
    assert result[basic_product.id]["effective"][0].display_mode == "detailed"

    premium_feature = result[premium_product.id]["effective"][0]
    assert premium_feature.display_mode == "icon"
    assert premium_feature.icon_caption == "Быстрое охлаждение"
    assert premium_feature.full_description == "Полное описание"
    assert premium_feature.is_featured is True

    # A model text override preserves the series presentation until explicitly changed.
    override = FeatureProductLink(product_id=premium_product.id, feature_id=feature.id, override_title="Турбо модели")
    db.add(override)
    await db.commit()
    result = await FeatureResolverService.resolve_for_products(db, products)
    assert result[premium_product.id]["effective"][0].display_mode == "icon"
    override.display_mode = "compact"
    db.add(override)
    await db.commit()
    result = await FeatureResolverService.resolve_for_products(db, products)
    assert result[premium_product.id]["effective"][0].display_mode == "compact"
    assert result[premium_product.id]["effective"][0].is_featured is True
    assert result[basic_product.id]["effective"][0].display_mode == "detailed"

    # Existing generic editors omit the new field; explicit null resets to inheritance.
    await FeatureAssignmentService.replace_product_assignments(
        db, premium_product.id, [FeatureLinkPayload(feature_id=feature.id)],
    )
    assert override.display_mode == "compact"
    await FeatureAssignmentService.replace_product_assignments(
        db, premium_product.id, [FeatureLinkPayload(feature_id=feature.id, display_mode=None)],
    )
    assert override.display_mode is None
    await FeatureAssignmentService.upsert_target_link(
        db, feature_id=feature.id, target_type="series", target_id=premium.id,
        payload=FeatureTargetLinkPayload(is_featured=True),
    )
    result = await FeatureResolverService.resolve_for_products(db, products)
    assert result[premium_product.id]["effective"][0].display_mode == "icon"

    # Older series editors omit the new field; that must preserve the icon setting.
    changed = await ManagerBrandSeriesFeatureOperations._sync_series_feature_assignments(
        db, series=premium, brand_id=brand.id,
        assignments=[ManagerFeatureSeriesAssignmentPayload(feature_id=feature.id, is_featured=True)],
    )
    assert changed is False
    link = (await db.execute(select(FeatureSeriesLink).where(FeatureSeriesLink.series_id == premium.id))).scalar_one()
    assert link.display_mode == "icon"

    login = await async_client.post("/login/access-token", data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    updated = await async_client.put(f"/api/manager/brands/{brand.id}/series/{basic.id}", headers=headers,
                                    json={"feature_assignments": [{"feature_id": feature.id, "display_mode": "icon"}]})
    assert updated.status_code == 200, updated.text
    assert updated.json()["feature_assignments"][0]["display_mode"] == "icon"
    public = await async_client.get(f"/api/v1/products/{basic_product.slug}")
    assert public.status_code == 200, public.text
    assert public.json()["features"][0]["display_mode"] == "icon"
    assert public.json()["features"][0]["icon_caption"] == "Быстрое охлаждение"
    invalid = await async_client.put(f"/api/manager/brands/{brand.id}/series/{basic.id}", headers=headers,
                                    json={"feature_assignments": [{"feature_id": feature.id, "display_mode": "unknown"}]})
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_brand_official_source_can_be_saved_cleared_and_validated(async_client, db):
    login = await async_client.post("/login/access-token", data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = await async_client.post("/api/manager/brands", headers=headers, json={
        "title": "Official source", "official_url": " https://manufacturer.example/catalog#section ",
    })
    assert response.status_code == 200, response.text
    assert response.json()["official_url"] == "https://manufacturer.example/catalog"
    brand_id = response.json()["id"]
    before = await CatalogRevisionService.get_current(db)
    unchanged = await async_client.put(f"/api/manager/brands/{brand_id}", headers=headers,
                                      json={"official_url": "https://manufacturer.example/catalog"})
    assert unchanged.status_code == 200
    assert await CatalogRevisionService.get_current(db) == before
    invalid = await async_client.put(f"/api/manager/brands/{brand_id}", headers=headers,
                                    json={"official_url": "javascript:alert(1)"})
    assert invalid.status_code == 422
    cleared = await async_client.put(f"/api/manager/brands/{brand_id}", headers=headers, json={"official_url": None})
    assert cleared.status_code == 200
    assert cleared.json()["official_url"] is None
