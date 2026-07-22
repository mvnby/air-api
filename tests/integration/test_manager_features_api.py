import pytest

from core.config import settings
from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureCategory,
    FeatureProductLink,
    FeatureRule,
    FeatureSeriesLink,
    Product,
    ProductSeries,
)


async def _auth_headers(async_client):
    response = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_feature_library_crud_archives_instead_of_deleting(async_client, db):
    category = FeatureCategory(slug="comfort-test", name="Комфорт", sort_order=10)
    brand = Brand(title="Feature Owner", slug="feature-owner", is_published=True)
    db.add(category)
    db.add(brand)
    await db.commit()
    await db.refresh(category)
    await db.refresh(brand)
    headers = await _auth_headers(async_client)

    create = await async_client.post(
        "/api/manager/features",
        headers=headers,
        json={
            "name": "Тихий режим",
            "category_id": category.id,
            "scope_type": "derived",
            "rules": [{"spec_key": "noise_db", "operator": "lte", "target_value": 20}],
        },
    )
    assert create.status_code == 201, create.text
    feature = create.json()
    assert feature["slug"] == "tikhii-rezhim"
    assert feature["rules"][0]["operator"] == "lte"

    update = await async_client.patch(
        f"/api/manager/features/{feature['id']}",
        headers=headers,
        json={"name": "Сверхтихий режим", "sort_order": 5},
    )
    assert update.status_code == 200, update.text
    assert update.json()["name"] == "Сверхтихий режим"

    brand_scope = await async_client.patch(
        f"/api/manager/features/{feature['id']}",
        headers=headers,
        json={"scope_type": "brand", "brand_id": brand.id},
    )
    assert brand_scope.status_code == 200, brand_scope.text
    assert brand_scope.json()["brand_id"] == brand.id
    universal_scope = await async_client.patch(
        f"/api/manager/features/{feature['id']}",
        headers=headers,
        json={"scope_type": "universal"},
    )
    assert universal_scope.status_code == 200, universal_scope.text
    assert universal_scope.json()["brand_id"] is None
    invalid_null = await async_client.patch(
        f"/api/manager/features/{feature['id']}",
        headers=headers,
        json={"sort_order": None},
    )
    assert invalid_null.status_code == 422

    archive = await async_client.delete(
        f"/api/manager/features/{feature['id']}", headers=headers
    )
    assert archive.status_code == 200, archive.text
    assert archive.json()["is_active"] is False
    assert archive.json()["archived_at"] is not None

    active = await async_client.get("/api/manager/features", headers=headers)
    assert all(item["id"] != feature["id"] for item in active.json()["items"])
    archived = await async_client.get(
        "/api/manager/features", headers=headers, params={"is_active": False}
    )
    assert [item["id"] for item in archived.json()["items"]] == [feature["id"]]


@pytest.mark.asyncio
async def test_feature_resolution_precedence_derived_apply_and_public_dto(async_client, db):
    category = FeatureCategory(slug="efficiency-test", name="Эффективность", sort_order=20)
    brand = Brand(title="Feature Brand", slug="feature-brand", is_published=True)
    db.add(category)
    db.add(brand)
    await db.flush()
    series = ProductSeries(
        brand_id=brand.id,
        title="Feature Series",
        slug="feature-series",
        is_published=True,
    )
    db.add(series)
    await db.flush()
    product = Product(
        title="Feature Product",
        slug="feature-product",
        price=2500,
        specs={"area_m2": 35, "wifi": True},
        brand_id=brand.id,
        series_id=series.id,
        is_published=True,
    )
    db.add(product)
    await db.flush()

    inherited = Feature(
        slug="air-flow-test",
        name="Воздушный поток",
        category_id=category.id,
        scope_type="universal",
        sort_order=30,
    )
    suppressed = Feature(
        slug="hidden-feature-test",
        name="Скрываемая фича",
        category_id=category.id,
        scope_type="universal",
        sort_order=40,
    )
    derived = Feature(
        slug="large-room-test",
        name="Для больших помещений",
        category_id=category.id,
        scope_type="derived",
        sort_order=50,
    )
    inherited_over_derived = Feature(
        slug="inherited-over-derived-test",
        name="Наследование приоритетнее derived",
        category_id=category.id,
        scope_type="derived",
        sort_order=60,
    )
    db.add(inherited)
    db.add(suppressed)
    db.add(derived)
    db.add(inherited_over_derived)
    await db.flush()
    db.add(FeatureBrandLink(brand_id=brand.id, feature_id=inherited.id, sort_order=20))
    db.add(FeatureSeriesLink(
        series_id=series.id,
        feature_id=inherited.id,
        sort_order=10,
        override_title="Поток серии",
    ))
    db.add(FeatureProductLink(
        product_id=product.id,
        feature_id=inherited.id,
        sort_order=0,
        override_title="Персональный поток",
    ))
    db.add(FeatureBrandLink(brand_id=brand.id, feature_id=suppressed.id))
    db.add(FeatureProductLink(
        product_id=product.id,
        feature_id=suppressed.id,
        is_enabled=False,
    ))
    db.add(FeatureRule(
        feature_id=derived.id,
        spec_key="area_m2",
        operator="gte",
        target_value=30,
    ))
    db.add(FeatureRule(
        feature_id=inherited_over_derived.id,
        spec_key="area_m2",
        operator="lt",
        target_value=10,
    ))
    db.add(FeatureBrandLink(
        brand_id=brand.id,
        feature_id=inherited_over_derived.id,
        override_title="Наследованное значение",
    ))
    db.add(FeatureProductLink(
        product_id=product.id,
        feature_id=inherited_over_derived.id,
        source="derived",
        override_title="Устаревшее derived-значение",
    ))
    await db.commit()
    headers = await _auth_headers(async_client)

    workspace = await async_client.get(
        f"/api/manager/products/{product.id}/features", headers=headers
    )
    assert workspace.status_code == 200, workspace.text
    body = workspace.json()
    assert [(item["slug"], item["source"]) for item in body["effective"]] == [
        ("air-flow-test", "product_override"),
        ("inherited-over-derived-test", "brand"),
    ]
    assert body["effective"][0]["name"] == "Персональный поток"
    assert body["effective"][1]["name"] == "Наследованное значение"
    assert body["disabled_feature_ids"] == [suppressed.id]
    assert body["manual_assignments"] == [
        {
            "feature_id": inherited.id,
            "source": "manual",
            "is_enabled": True,
            "sort_order": 0,
            "override_title": "Персональный поток",
            "override_description": None,
            "override_media_id": None,
            "override_image_url": None,
            "override_icon": None,
            "override_footnote": None,
        },
        {
            "feature_id": suppressed.id,
            "source": "manual",
            "is_enabled": False,
            "sort_order": 0,
            "override_title": None,
            "override_description": None,
            "override_media_id": None,
            "override_image_url": None,
            "override_icon": None,
            "override_footnote": None,
        },
    ]
    assert [item["slug"] for item in body["automatic_suggestions"]] == ["large-room-test"]

    manager_detail = await async_client.get(
        f"/api/manager/products/{product.id}", headers=headers
    )
    assert manager_detail.status_code == 200, manager_detail.text
    assert manager_detail.json()["features_workspace"]["effective"][0]["slug"] == "air-flow-test"

    applied = await async_client.post(
        f"/api/manager/products/{product.id}/features/suggestions/apply",
        headers=headers,
        json={"feature_ids": [derived.id]},
    )
    assert applied.status_code == 200, applied.text
    assert [item["source"] for item in applied.json()["effective"]] == [
        "product_override",
        "derived",
        "brand",
    ]
    repeated = await async_client.post(
        f"/api/manager/products/{product.id}/features/suggestions/apply",
        headers=headers,
        json={"feature_ids": [derived.id]},
    )
    assert repeated.status_code == 200, repeated.text

    public = await async_client.get(f"/api/v1/products/{product.slug}")
    assert public.status_code == 200, public.text
    public_features = public.json()["features"]
    assert [(item["slug"], item["source"]) for item in public_features] == [
        ("air-flow-test", "product_override"),
        ("large-room-test", "derived"),
        ("inherited-over-derived-test", "brand"),
    ]
    assert all("category" in item and "feature_sort_order" in item for item in public_features)

    removed = await async_client.delete(
        f"/api/manager/products/{product.id}/features/{derived.id}", headers=headers
    )
    assert removed.status_code == 200, removed.text
    assert [item["slug"] for item in removed.json()["automatic_suggestions"]] == [
        "large-room-test"
    ]
