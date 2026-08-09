import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureCategory,
    FeatureProductLink,
    FeatureSeriesLink,
    Product,
    ProductSeries,
)
from schemas_features import FeatureTargetLinkPayload, FeatureUpdatePayload
from services.feature_assignment_service import FeatureAssignmentService
from services.feature_library_service import FeatureLibraryService
from services.feature_series_migration_service import FeatureSeriesMigrationService
from services.manager_brand_service import ManagerBrandService


@pytest.mark.asyncio
async def test_postgres_concurrent_featured_assignments_keep_max_three(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        category = FeatureCategory(slug="featured-race", name="Featured race")
        brand = Brand(title="Featured Race Brand", slug="featured-race-brand")
        setup.add_all([category, brand])
        await setup.flush()
        series = ProductSeries(brand_id=brand.id, title="Featured Race", slug="featured-race")
        setup.add(series)
        await setup.flush()
        features = [
            Feature(
                slug=f"featured-race-{index}",
                name=f"Featured race {index}",
                category_id=category.id,
                scope_type="universal",
            )
            for index in range(4)
        ]
        setup.add_all(features)
        await setup.flush()
        setup.add_all(
            [
                FeatureSeriesLink(
                    series_id=series.id,
                    feature_id=feature.id,
                    is_featured=True,
                )
                for feature in features[:2]
            ]
        )
        await setup.commit()
        series_id = int(series.id)
        candidate_ids = [int(feature.id) for feature in features[2:]]

    async def assign(feature_id: int) -> str:
        async with factory() as session:
            try:
                await FeatureAssignmentService.upsert_target_link(
                    session,
                    feature_id=feature_id,
                    target_type="series",
                    target_id=series_id,
                    payload=FeatureTargetLinkPayload(is_featured=True),
                )
            except HTTPException as exc:
                await session.rollback()
                return str(exc.status_code)
            return "ok"

    outcomes = await asyncio.wait_for(
        asyncio.gather(*(assign(feature_id) for feature_id in candidate_ids)),
        timeout=10,
    )
    assert sorted(outcomes) == ["400", "ok"]
    async with factory() as session:
        featured_ids = list(
            (
                await session.execute(
                    select(FeatureSeriesLink.feature_id).where(
                        FeatureSeriesLink.series_id == series_id,
                        FeatureSeriesLink.is_enabled.is_(True),
                        FeatureSeriesLink.is_featured.is_(True),
                    )
                )
            ).scalars().all()
        )
    assert len(featured_ids) == 3


@pytest.mark.asyncio
async def test_postgres_concurrent_series_replacements_remain_coherent(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        category = FeatureCategory(slug="series-replace-race", name="Series replace race")
        brand = Brand(title="Series Replace Race", slug="series-replace-race")
        setup.add_all([category, brand])
        await setup.flush()
        series = ProductSeries(
            brand_id=brand.id,
            title="Series Replace Race",
            slug="series-replace-race",
        )
        features = [
            Feature(
                slug=f"series-replace-race-{index}",
                name=f"Series replace race {index}",
                category_id=category.id,
                scope_type="universal",
            )
            for index in range(4)
        ]
        setup.add_all([series, *features])
        await setup.flush()
        setup.add_all(
            [
                FeatureSeriesLink(
                    series_id=series.id,
                    feature_id=feature.id,
                    is_featured=True,
                )
                for feature in features[:2]
            ]
        )
        await setup.commit()
        brand_id = int(brand.id)
        series_id = int(series.id)
        feature_ids = [int(feature.id) for feature in features]

    assignments_a = [
        {"feature_id": feature_id, "is_featured": True}
        for feature_id in [feature_ids[0], feature_ids[1], feature_ids[2]]
    ]
    assignments_b = [
        {"feature_id": feature_id, "is_featured": True}
        for feature_id in [feature_ids[0], feature_ids[1], feature_ids[3]]
    ]
    barrier = asyncio.Barrier(2)

    async def replace(assignments):
        async with factory() as session:
            await barrier.wait()
            return await ManagerBrandService.update_brand_series(
                session,
                brand_id,
                series_id,
                {"feature_assignments": assignments},
            )

    responses = await asyncio.wait_for(
        asyncio.gather(replace(assignments_a), replace(assignments_b)),
        timeout=10,
    )
    expected_sets = {
        frozenset(item["feature_id"] for item in assignments_a),
        frozenset(item["feature_id"] for item in assignments_b),
    }
    assert {
        frozenset(item["feature_id"] for item in response["feature_assignments"])
        for response in responses
    } == expected_sets

    async with factory() as verification:
        links = list(
            (
                await verification.execute(
                    select(FeatureSeriesLink).where(
                        FeatureSeriesLink.series_id == series_id,
                        FeatureSeriesLink.is_enabled.is_(True),
                    )
                )
            ).scalars().all()
        )
    assert len(links) == 3
    assert sum(bool(link.is_featured) for link in links) == 3
    assert frozenset(int(link.feature_id) for link in links) in expected_sets


@pytest.mark.asyncio
async def test_postgres_cross_replacements_use_ordered_feature_locks(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        category = FeatureCategory(slug="replacement-lock-order", name="Replacement lock order")
        brand = Brand(title="Replacement Lock Brand", slug="replacement-lock-brand")
        setup.add_all([category, brand])
        await setup.flush()
        features = [
            Feature(
                slug=f"replacement-lock-{index}",
                name=f"Replacement lock {index}",
                category_id=category.id,
                scope_type="universal",
            )
            for index in range(2)
        ]
        setup.add_all(features)
        await setup.commit()
        brand_id = int(brand.id)
        feature_ids = [int(feature.id) for feature in features]

    barrier = asyncio.Barrier(2)

    async def replace(feature_id: int, replacement_id: int) -> str:
        async with factory() as session:
            await barrier.wait()
            try:
                await FeatureLibraryService.update_feature(
                    session,
                    feature_id,
                    FeatureUpdatePayload(
                        scope_type="brand",
                        brand_id=brand_id,
                        replaces_feature_id=replacement_id,
                    ),
                )
            except HTTPException as exc:
                await session.rollback()
                return f"http-{exc.status_code}"
            return "ok"

    outcomes = await asyncio.wait_for(
        asyncio.gather(
            replace(feature_ids[0], feature_ids[1]),
            replace(feature_ids[1], feature_ids[0]),
        ),
        timeout=10,
    )
    assert sorted(outcomes) == ["http-400", "ok"]

    async with factory() as verification:
        rows = list(
            (
                await verification.execute(
                    select(Feature)
                    .where(Feature.id.in_(feature_ids))
                    .order_by(Feature.id.asc())
                )
            ).scalars().all()
        )
    branded = [feature for feature in rows if feature.scope_type == "brand"]
    universal = [feature for feature in rows if feature.scope_type == "universal"]
    assert len(branded) == 1
    assert len(universal) == 1
    assert branded[0].replaces_feature_id == universal[0].id


@pytest.mark.asyncio
async def test_postgres_crossed_migration_batches_use_global_lock_order(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        category = FeatureCategory(slug="migration-lock-order", name="Migration lock order")
        brand = Brand(title="Migration Lock Brand", slug="migration-lock-brand")
        setup.add_all([category, brand])
        await setup.flush()
        features = [
            Feature(
                slug=f"migration-lock-feature-{index}",
                name=f"Migration lock feature {index}",
                category_id=category.id,
                scope_type="universal",
            )
            for index in range(2)
        ]
        setup.add_all(features)
        await setup.flush()
        series_rows = []
        products = []
        for index in range(4):
            series = ProductSeries(
                brand_id=brand.id,
                title=f"Migration Lock Series {index}",
                slug=f"migration-lock-series-{index}",
            )
            setup.add(series)
            await setup.flush()
            product = Product(
                title=f"Migration Lock Product {index}",
                slug=f"migration-lock-product-{index}",
                price=1000,
                brand_id=brand.id,
                series_id=series.id,
            )
            setup.add(product)
            await setup.flush()
            series_rows.append(series)
            products.append(product)

        pairs = [
            (series_rows[0], products[0], features[1]),
            (series_rows[1], products[1], features[0]),
            (series_rows[2], products[2], features[0]),
            (series_rows[3], products[3], features[1]),
        ]
        setup.add_all(
            [
                FeatureProductLink(
                    product_id=product.id,
                    feature_id=feature.id,
                    source="manual",
                    is_enabled=True,
                    sort_order=10,
                )
                for _, product, feature in pairs
            ]
        )
        await setup.commit()
        series_ids = [int(series.id) for series in series_rows]
        feature_ids = [int(feature.id) for feature in features]

    async with factory() as preview_session:
        preview = await FeatureSeriesMigrationService.preview(
            preview_session,
            series_ids=series_ids,
        )
    assert preview.total == 4
    by_pair = {(item.series_id, item.feature_id): item for item in preview.candidates}
    batch_a = [
        by_pair[(series_ids[0], feature_ids[1])],
        by_pair[(series_ids[1], feature_ids[0])],
    ]
    batch_b = [
        by_pair[(series_ids[2], feature_ids[0])],
        by_pair[(series_ids[3], feature_ids[1])],
    ]

    async def apply_batch(candidates):
        async with factory() as session:
            return await FeatureSeriesMigrationService.apply(session, list(reversed(candidates)))

    first, second = await asyncio.wait_for(
        asyncio.gather(apply_batch(batch_a), apply_batch(batch_b)),
        timeout=10,
    )
    assert first.applied_count == 2
    assert second.applied_count == 2
    async with factory() as session:
        series_links = list((await session.execute(select(FeatureSeriesLink))).scalars().all())
        product_links = list((await session.execute(select(FeatureProductLink))).scalars().all())
    assert len(series_links) == 4
    assert product_links == []


@pytest.mark.asyncio
async def test_postgres_brand_assignment_and_migration_share_brand_fence(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup:
        category = FeatureCategory(slug="migration-brand-fence", name="Brand fence")
        brand = Brand(title="Migration Brand Fence", slug="migration-brand-fence")
        setup.add_all([category, brand])
        await setup.flush()
        series = ProductSeries(
            brand_id=brand.id,
            title="Migration Brand Fence Series",
            slug="migration-brand-fence-series",
        )
        setup.add(series)
        await setup.flush()
        product = Product(
            title="Migration Brand Fence Product",
            slug="migration-brand-fence-product",
            price=1000,
            brand_id=brand.id,
            series_id=series.id,
        )
        feature = Feature(
            slug="migration-brand-fence-feature",
            name="Migration brand fence feature",
            category_id=category.id,
            scope_type="universal",
        )
        setup.add_all([product, feature])
        await setup.flush()
        setup.add(
            FeatureProductLink(
                product_id=product.id,
                feature_id=feature.id,
                source="manual",
                is_enabled=True,
            )
        )
        await setup.commit()
        brand_id = int(brand.id)
        series_id = int(series.id)
        feature_id = int(feature.id)

    async with factory() as preview_session:
        preview = await FeatureSeriesMigrationService.preview(
            preview_session,
            series_ids=[series_id],
        )
    candidate = preview.candidates[0]
    barrier = asyncio.Barrier(2)

    async def migrate():
        async with factory() as session:
            await barrier.wait()
            try:
                return await FeatureSeriesMigrationService.apply(session, [candidate])
            except HTTPException as exc:
                return exc.status_code

    async def assign_brand():
        async with factory() as session:
            await barrier.wait()
            await FeatureAssignmentService.upsert_target_link(
                session,
                feature_id=feature_id,
                target_type="brand",
                target_id=brand_id,
                payload=FeatureTargetLinkPayload(),
            )

    migration_result, _ = await asyncio.wait_for(
        asyncio.gather(migrate(), assign_brand()),
        timeout=10,
    )
    async with factory() as verification:
        brand_link = (
            await verification.execute(
                select(FeatureBrandLink).where(
                    FeatureBrandLink.brand_id == brand_id,
                    FeatureBrandLink.feature_id == feature_id,
                )
            )
        ).scalar_one()
        series_link = (
            await verification.execute(
                select(FeatureSeriesLink).where(
                    FeatureSeriesLink.series_id == series_id,
                    FeatureSeriesLink.feature_id == feature_id,
                )
            )
        ).scalar_one_or_none()
        product_links = list(
            (
                await verification.execute(
                    select(FeatureProductLink).where(
                        FeatureProductLink.feature_id == feature_id
                    )
                )
            ).scalars().all()
        )
    assert brand_link is not None
    if migration_result == 409:
        assert series_link is None
        assert len(product_links) == 1
    else:
        assert migration_result.applied_count == 1
        assert series_link is not None
        assert product_links == []
