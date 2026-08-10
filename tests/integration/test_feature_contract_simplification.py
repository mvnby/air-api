import pytest
from sqlmodel import select

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
from services.feature_resolver_service import FeatureResolverService
from services.feature_contract_legacy_report_service import FeatureContractLegacyReportService


async def _auth_headers(async_client):
    response = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_universal_rule_replacement_product_exception_and_featured_sort(async_client, db):
    category = FeatureCategory(slug="contract-rule", name="Contract")
    brand = Brand(title="Contract Brand", slug="contract-brand")
    db.add_all([category, brand])
    await db.flush()
    series = ProductSeries(brand_id=brand.id, title="Contract Series", slug="contract-series")
    db.add(series)
    await db.flush()
    product = Product(
        title="Contract Product",
        slug="contract-product",
        price=1000,
        brand_id=brand.id,
        series_id=series.id,
        specs={"is_inverter": True},
    )
    db.add(product)
    await db.flush()
    universal = Feature(
        slug="contract-inverter",
        name="Inverter",
        category_id=category.id,
        scope_type="universal",
        sort_order=1,
    )
    secondary = Feature(
        slug="contract-secondary",
        name="Secondary",
        category_id=category.id,
        scope_type="universal",
        sort_order=0,
    )
    legacy_ruleless = Feature(
        slug="contract-ruleless-derived",
        name="Ruleless derived",
        category_id=category.id,
        scope_type="universal",
    )
    db.add_all([universal, secondary, legacy_ruleless])
    await db.flush()
    db.add(
        FeatureRule(
            feature_id=universal.id,
            spec_key="is_inverter",
            operator="eq",
            target_value=True,
        )
    )
    branded = Feature(
        slug="contract-3dc",
        name="3D DC Inverter",
        category_id=category.id,
        scope_type="brand",
        brand_id=brand.id,
        replaces_feature_id=universal.id,
        sort_order=50,
    )
    db.add(branded)
    await db.flush()
    db.add_all(
        [
            FeatureSeriesLink(
                series_id=series.id,
                feature_id=branded.id,
                is_featured=True,
                sort_order=50,
            ),
            FeatureSeriesLink(
                series_id=series.id,
                feature_id=secondary.id,
                is_featured=False,
                sort_order=0,
            ),
            FeatureProductLink(
                product_id=product.id,
                feature_id=legacy_ruleless.id,
                source="derived",
            ),
        ]
    )
    await db.commit()

    resolved = await FeatureResolverService.resolve_for_products(db, [product])
    effective = resolved[int(product.id)]["effective"]
    assert [(item.slug, item.is_featured) for item in effective] == [
        ("contract-3dc", True),
        ("contract-secondary", False),
    ]

    db.add(
        FeatureProductLink(
            product_id=product.id,
            feature_id=branded.id,
            source="manual",
            is_enabled=False,
        )
    )
    await db.commit()
    resolved = await FeatureResolverService.resolve_for_products(db, [product])
    assert [(item.slug, item.source) for item in resolved[int(product.id)]["effective"]] == [
        ("contract-secondary", "series"),
        ("contract-inverter", "derived"),
    ]

    public = await async_client.get(f"/api/v1/products/{product.slug}")
    assert public.status_code == 200, public.text
    dto = {item["slug"]: item for item in public.json()["features"]}
    assert dto["contract-inverter"]["source"] == "derived"
    assert dto["contract-inverter"]["is_featured"] is False


@pytest.mark.asyncio
async def test_manager_feature_scope_owner_and_series_assignment_contract(async_client, db):
    category = FeatureCategory(slug="contract-manager", name="Manager")
    brand = Brand(title="Manager Brand", slug="manager-brand")
    other = Brand(title="Other Brand", slug="other-brand")
    db.add_all([category, brand, other])
    await db.flush()
    series = ProductSeries(brand_id=brand.id, title="Manager Series", slug="manager-series")
    db.add(series)
    await db.commit()
    headers = await _auth_headers(async_client)

    universal = await async_client.post(
        "/api/manager/features",
        headers=headers,
        json={"name": "Manager Universal", "category_id": category.id, "scope_type": "universal"},
    )
    assert universal.status_code == 201, universal.text
    branded = await async_client.post(
        "/api/manager/features",
        headers=headers,
        json={
            "name": "Manager Branded",
            "category_id": category.id,
            "scope_type": "brand",
            "brand_id": brand.id,
            "replaces_feature_id": universal.json()["id"],
        },
    )
    assert branded.status_code == 201, branded.text
    assert branded.json()["replaces_feature_id"] == universal.json()["id"]
    assert (
        await db.execute(
            select(FeatureBrandLink).where(FeatureBrandLink.feature_id == branded.json()["id"])
        )
    ).scalar_one_or_none() is None

    legacy_scope = await async_client.post(
        "/api/manager/features",
        headers=headers,
        json={"name": "No Product Scope", "category_id": category.id, "scope_type": "product"},
    )
    assert legacy_scope.status_code == 422

    feature_ids = [universal.json()["id"], branded.json()["id"]]
    for index in range(2):
        response = await async_client.post(
            "/api/manager/features",
            headers=headers,
            json={"name": f"Manager Extra {index}", "category_id": category.id},
        )
        assert response.status_code == 201
        feature_ids.append(response.json()["id"])
    too_many = await async_client.put(
        f"/api/manager/brands/{brand.id}/series/{series.id}",
        headers=headers,
        json={
            "feature_assignments": [
                {"feature_id": feature_id, "is_featured": True} for feature_id in feature_ids
            ]
        },
    )
    assert too_many.status_code == 400

    assigned = await async_client.put(
        f"/api/manager/brands/{brand.id}/series/{series.id}",
        headers=headers,
        json={
            "feature_assignments": [
                {"feature_id": universal.json()["id"], "is_featured": False},
                {"feature_id": branded.json()["id"], "is_featured": True},
            ]
        },
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["feature_assignments"] == [
        {"feature_id": branded.json()["id"], "is_featured": True},
        {"feature_id": universal.json()["id"], "is_featured": False},
    ]
    assert assigned.json()["catalog_features"][0]["id"] == branded.json()["id"]
    assert assigned.json()["catalog_features"][0]["is_featured"] is True
    missing_series_delete = await async_client.delete(
        f"/api/manager/features/{universal.json()['id']}/series/999999999",
        headers=headers,
    )
    assert missing_series_delete.status_code == 404


@pytest.mark.asyncio
async def test_series_update_preserves_existing_legacy_assignment_but_rejects_new_one(
    async_client,
    db,
):
    category = FeatureCategory(slug="legacy-series-save", name="Legacy series save")
    brand = Brand(title="Legacy Save Brand", slug="legacy-save-brand")
    db.add_all([category, brand])
    await db.flush()
    series = ProductSeries(
        brand_id=brand.id,
        title="Legacy Save Series",
        slug="legacy-save-series",
    )
    db.add(series)
    await db.flush()
    existing_legacy = Feature(
        slug="legacy-save-derived",
        name="Existing derived feature",
        category_id=category.id,
        scope_type="derived",
    )
    new_legacy = Feature(
        slug="legacy-save-new-derived",
        name="New derived feature",
        category_id=category.id,
        scope_type="derived",
    )
    universal = Feature(
        slug="legacy-save-universal",
        name="Universal feature",
        category_id=category.id,
        scope_type="universal",
    )
    db.add_all([existing_legacy, new_legacy, universal])
    await db.flush()
    db.add(
        FeatureSeriesLink(
            series_id=series.id,
            feature_id=existing_legacy.id,
            source="manual",
            is_enabled=True,
            sort_order=10,
        )
    )
    await db.commit()
    headers = await _auth_headers(async_client)

    saved = await async_client.put(
        f"/api/manager/brands/{brand.id}/series/{series.id}",
        headers=headers,
        json={
            "feature_assignments": [
                {"feature_id": existing_legacy.id, "is_featured": False},
                {"feature_id": universal.id, "is_featured": True},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["feature_assignments"] == [
        {"feature_id": universal.id, "is_featured": True},
        {"feature_id": existing_legacy.id, "is_featured": False},
    ]

    rejected = await async_client.put(
        f"/api/manager/brands/{brand.id}/series/{series.id}",
        headers=headers,
        json={
            "feature_assignments": [
                {"feature_id": existing_legacy.id, "is_featured": False},
                {"feature_id": universal.id, "is_featured": True},
                {"feature_id": new_legacy.id, "is_featured": False},
            ]
        },
    )
    assert rejected.status_code == 400
    assert str(new_legacy.id) in rejected.json()["detail"]


@pytest.mark.asyncio
async def test_disabled_legacy_derived_link_does_not_hide_series_or_brand(db):
    category = FeatureCategory(slug="legacy-derived-priority", name="Priority")
    brand = Brand(title="Priority Brand", slug="priority-brand")
    db.add_all([category, brand])
    await db.flush()
    series = ProductSeries(brand_id=brand.id, title="Priority Series", slug="priority-series")
    db.add(series)
    await db.flush()
    product = Product(
        title="Priority Product",
        slug="priority-product",
        price=1000,
        brand_id=brand.id,
        series_id=series.id,
    )
    db.add(product)
    await db.flush()
    series_feature = Feature(
        slug="priority-series-feature",
        name="Series feature",
        category_id=category.id,
        scope_type="universal",
    )
    brand_feature = Feature(
        slug="priority-brand-feature",
        name="Brand feature",
        category_id=category.id,
        scope_type="brand",
        brand_id=brand.id,
    )
    db.add_all([series_feature, brand_feature])
    await db.flush()
    db.add_all(
        [
            FeatureSeriesLink(series_id=series.id, feature_id=series_feature.id),
            FeatureBrandLink(brand_id=brand.id, feature_id=brand_feature.id),
            FeatureProductLink(
                product_id=product.id,
                feature_id=series_feature.id,
                source="derived",
                is_enabled=False,
            ),
            FeatureProductLink(
                product_id=product.id,
                feature_id=brand_feature.id,
                source="derived",
                is_enabled=False,
            ),
        ]
    )
    await db.commit()

    resolved = await FeatureResolverService.resolve_for_products(db, [product])
    workspace = resolved[int(product.id)]
    assert [(item.slug, item.source) for item in workspace["effective"]] == [
        ("priority-brand-feature", "brand"),
        ("priority-series-feature", "series"),
    ]
    assert workspace["disabled_feature_ids"] == []


@pytest.mark.asyncio
async def test_universal_with_active_replacements_cannot_become_brand(async_client, db):
    category = FeatureCategory(slug="replacement-scope-guard", name="Replacement guard")
    brand = Brand(title="Replacement Guard Brand", slug="replacement-guard-brand")
    db.add_all([category, brand])
    await db.flush()
    universal = Feature(
        slug="replacement-guard-universal",
        name="Universal target",
        category_id=category.id,
        scope_type="universal",
    )
    db.add(universal)
    await db.flush()
    branded = Feature(
        slug="replacement-guard-branded",
        name="Branded replacement",
        category_id=category.id,
        scope_type="brand",
        brand_id=brand.id,
        replaces_feature_id=universal.id,
    )
    db.add(branded)
    await db.commit()
    headers = await _auth_headers(async_client)

    response = await async_client.patch(
        f"/api/manager/features/{universal.id}",
        headers=headers,
        json={"scope_type": "brand", "brand_id": brand.id},
    )
    assert response.status_code == 400, response.text
    await db.refresh(universal)
    assert universal.scope_type == "universal"
    assert universal.brand_id is None


@pytest.mark.asyncio
async def test_series_migration_preview_apply_replay_and_public_projection(async_client, db):
    category = FeatureCategory(slug="migration-category", name="Migration")
    brand = Brand(title="Migration Brand", slug="migration-brand")
    db.add_all([category, brand])
    await db.flush()
    series = ProductSeries(brand_id=brand.id, title="Migration Series", slug="migration-series")
    db.add(series)
    await db.flush()
    published = [
        Product(
            title=f"Migration Product {index}",
            slug=f"migration-product-{index}",
            price=1000,
            brand_id=brand.id,
            series_id=series.id,
            is_published=True,
        )
        for index in range(2)
    ]
    draft = Product(
        title="Migration Draft",
        slug="migration-draft",
        price=1000,
        brand_id=brand.id,
        series_id=series.id,
        is_published=False,
    )
    db.add_all([*published, draft])
    await db.flush()
    common = Feature(
        slug="migration-common",
        name="Migration Common",
        category_id=category.id,
        scope_type="universal",
    )
    partial = Feature(
        slug="migration-partial",
        name="Migration Partial",
        category_id=category.id,
        scope_type="universal",
    )
    overridden = Feature(
        slug="migration-override",
        name="Migration Override",
        category_id=category.id,
        scope_type="universal",
    )
    db.add_all([common, partial, overridden])
    await db.flush()
    db.add_all(
        [
            *[
                FeatureProductLink(
                    product_id=product.id,
                    feature_id=common.id,
                    source="manual",
                    is_enabled=True,
                    sort_order=20,
                )
                for product in [*published, draft]
            ],
            FeatureProductLink(product_id=published[0].id, feature_id=partial.id),
            FeatureProductLink(product_id=published[0].id, feature_id=overridden.id),
            FeatureProductLink(
                product_id=published[1].id,
                feature_id=overridden.id,
                override_title="Individual",
            ),
        ]
    )
    await db.commit()
    series_id = int(series.id)
    headers = await _auth_headers(async_client)

    preview = await async_client.get(
        "/api/manager/features/series-migration/preview",
        headers=headers,
        params={"series_ids": series_id},
    )
    assert preview.status_code == 200, preview.text
    assert [item["feature_id"] for item in preview.json()["candidates"]] == [common.id]
    candidate = preview.json()["candidates"][0]
    assert candidate["published_products_count"] == 2
    assert candidate["matching_assignments_count"] == 2

    payload = {
        "candidates": [
            {
                "series_id": series.id,
                "feature_id": common.id,
                "candidate_token": candidate["candidate_token"],
            }
        ]
    }
    applied = await async_client.post(
        "/api/manager/features/series-migration/apply",
        headers=headers,
        json=payload,
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied_count"] == 1
    assert applied.json()["deleted_product_assignments"] == 2
    links = list(
        (
            await db.execute(
                select(FeatureProductLink).where(FeatureProductLink.feature_id == common.id)
            )
        ).scalars().all()
    )
    assert [link.product_id for link in links] == [draft.id]
    series_link = (
        await db.execute(
            select(FeatureSeriesLink).where(
                FeatureSeriesLink.series_id == series.id,
                FeatureSeriesLink.feature_id == common.id,
            )
        )
    ).scalar_one()
    assert series_link.sort_order == 20

    replay = await async_client.post(
        "/api/manager/features/series-migration/apply",
        headers=headers,
        json=payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["already_applied_count"] == 1

    public = await async_client.get(f"/api/v1/products/{published[0].slug}")
    assert public.status_code == 200, public.text
    item = next(item for item in public.json()["features"] if item["id"] == common.id)
    assert item["source"] == "series"


@pytest.mark.asyncio
async def test_series_migration_stale_batch_rolls_back_every_candidate(async_client, db):
    category = FeatureCategory(slug="migration-rollback", name="Rollback")
    brand = Brand(title="Rollback Brand", slug="rollback-brand")
    db.add_all([category, brand])
    await db.flush()
    series = ProductSeries(brand_id=brand.id, title="Rollback Series", slug="rollback-series")
    db.add(series)
    await db.flush()
    products = [
        Product(
            title=f"Rollback Product {index}",
            slug=f"rollback-product-{index}",
            price=1000,
            brand_id=brand.id,
            series_id=series.id,
        )
        for index in range(2)
    ]
    features = [
        Feature(
            slug=f"rollback-feature-{index}",
            name=f"Rollback Feature {index}",
            category_id=category.id,
            scope_type="universal",
        )
        for index in range(2)
    ]
    db.add_all([*products, *features])
    await db.flush()
    db.add_all(
        [
            FeatureProductLink(product_id=product.id, feature_id=feature.id, sort_order=10)
            for product in products
            for feature in features
        ]
    )
    await db.commit()
    series_id = int(series.id)
    product_ids = [int(product.id) for product in products]
    headers = await _auth_headers(async_client)
    preview = await async_client.get(
        "/api/manager/features/series-migration/preview",
        headers=headers,
        params={"series_ids": series_id},
    )
    candidates = preview.json()["candidates"]
    assert len(candidates) == 2

    stale_link = (
        await db.execute(
            select(FeatureProductLink).where(
                FeatureProductLink.product_id == products[0].id,
                FeatureProductLink.feature_id == features[1].id,
            )
        )
    ).scalar_one()
    stale_link.sort_order = 99
    db.add(stale_link)
    await db.commit()
    apply = await async_client.post(
        "/api/manager/features/series-migration/apply",
        headers=headers,
        json={
            "candidates": [
                {
                    "series_id": item["series_id"],
                    "feature_id": item["feature_id"],
                    "candidate_token": item["candidate_token"],
                }
                for item in candidates
            ]
        },
    )
    assert apply.status_code == 409
    assert (
        await db.execute(
            select(FeatureSeriesLink).where(FeatureSeriesLink.series_id == series_id)
        )
    ).scalars().all() == []
    remaining = (
        await db.execute(
            select(FeatureProductLink).where(
                FeatureProductLink.product_id.in_(product_ids)
            )
        )
    ).scalars().all()
    assert len(remaining) == 4


@pytest.mark.asyncio
async def test_legacy_contract_report_is_read_only_and_deterministic(db):
    category = FeatureCategory(slug="legacy-report", name="Legacy report")
    brand = Brand(title="Legacy Report Brand", slug="legacy-report-brand")
    db.add_all([category, brand])
    await db.flush()
    series = ProductSeries(
        brand_id=brand.id,
        title="Legacy Report Series",
        slug="legacy-report-series",
        features=["Legacy text"],
        feature_blocks=[{"title": "Legacy block"}],
    )
    db.add(series)
    await db.flush()
    feature = Feature(
        slug="legacy-report-derived",
        name="Legacy derived",
        category_id=category.id,
        scope_type="derived",
    )
    db.add(feature)
    await db.flush()
    product = Product(
        title="Legacy Report Product",
        slug="legacy-report-product",
        price=1000,
        brand_id=brand.id,
        series_id=series.id,
    )
    db.add(product)
    await db.flush()
    db.add_all(
        [
            FeatureBrandLink(brand_id=brand.id, feature_id=feature.id),
            FeatureProductLink(
                product_id=product.id,
                feature_id=feature.id,
                source="derived",
                override_title="Legacy override",
            ),
        ]
    )
    await db.commit()

    first = await FeatureContractLegacyReportService.build(db, sample_limit=5)
    second = await FeatureContractLegacyReportService.build(db, sample_limit=5)
    assert first == second
    assert first["legacy_feature_scopes"]["derived"]["sample_ids"] == [feature.id]
    assert first["feature_brand_links"]["count"] == 1
    assert first["stored_derived_product_links"]["count"] == 1
    assert first["product_feature_overrides"]["count"] == 1
    assert first["product_series_legacy_content"]["features"]["sample_series_ids"] == [series.id]
