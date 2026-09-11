from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import (
    Brand,
    Product,
    ProductSeries,
    Supplier,
    WarrantyPolicy,
    WarrantyPolicySeriesLink,
)
from services.catalog_revision_service import CatalogRevisionService
from services.product_response_mapper import map_product_to_response
from services.public_catalog_visibility_service import PublicCatalogVisibilityService
from services.warranty_policy_resolver import WarrantyPolicyResolver
from services.warranty_service import WarrantyService


@pytest.fixture
async def warranty_projection_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'public-warranty.db'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_public_warranty_projection_is_batched_and_uses_general_precedence(
    warranty_projection_session: AsyncSession,
):
    session = warranty_projection_session
    now = datetime(2026, 9, 11, 12, 0, 0)
    supplier = Supplier(name="Private supplier", code="private-public-warranty")
    brand = Brand(title="Public warranty brand", slug="public-warranty-brand")
    session.add_all([supplier, brand])
    await session.flush()
    first_series = ProductSeries(
        brand_id=int(brand.id),
        title="First public warranty series",
        slug="first-public-warranty-series",
    )
    second_series = ProductSeries(
        brand_id=int(brand.id),
        title="Second public warranty series",
        slug="second-public-warranty-series",
    )
    session.add_all([first_series, second_series])
    await session.flush()
    product = Product(
        title="Specific public warranty",
        slug="specific-public-warranty",
        price=1000,
        brand_id=brand.id,
        series_id=first_series.id,
    )
    series_product = Product(
        title="Series public warranty",
        slug="series-public-warranty",
        price=1000,
        brand_id=brand.id,
        series_id=second_series.id,
    )
    brand_product = Product(
        title="Brand public warranty",
        slug="brand-public-warranty",
        price=1000,
        brand_id=brand.id,
    )
    no_policy_product = Product(
        title="No public warranty",
        slug="no-public-warranty",
        price=1000,
        specs={"warranty_months": "5"},
    )
    hidden_product = Product(
        title="Tenant-hidden warranty product",
        slug="tenant-hidden-warranty-product",
        price=1000,
        brand_id=brand.id,
    )
    session.add_all(
        [product, series_product, brand_product, no_policy_product, hidden_product]
    )
    await session.flush()
    series_policy = WarrantyPolicy(
        name="Multi-series general",
        brand_id=brand.id,
        series_id=first_series.id,
        duration_months=48,
    )
    session.add(series_policy)
    await session.flush()
    session.add_all(
        [
            WarrantyPolicy(
                name="Brand general",
                brand_id=brand.id,
                duration_months=36,
            ),
            WarrantyPolicy(
                name="Supplier private",
                supplier_id=supplier.id,
                product_id=product.id,
                duration_months=120,
            ),
            WarrantyPolicy(
                name="Work coverage",
                coverage_type="mvn_work",
                product_id=product.id,
                duration_months=110,
            ),
            WarrantyPolicy(
                name="Expired product general",
                product_id=product.id,
                duration_months=72,
                effective_until=now - timedelta(seconds=1),
            ),
            WarrantyPolicy(
                name="Future product general",
                product_id=product.id,
                duration_months=60,
                effective_from=now + timedelta(seconds=1),
            ),
            WarrantyPolicy(
                name="Current product general",
                product_id=product.id,
                duration_months=54,
                maintenance_required=True,
                maintenance_interval_months=12,
                allowed_maintenance_provider="mvn",
                grace_period_days=30,
                start_event="installation",
                terms="Annual maintenance is required.",
                effective_from=now,
                effective_until=now,
            ),
            WarrantyPolicy(
                name="Hidden product policy",
                product_id=hidden_product.id,
                duration_months=84,
            ),
            WarrantyPolicySeriesLink(
                policy_id=int(series_policy.id),
                series_id=int(first_series.id),
                sort_order=0,
            ),
            WarrantyPolicySeriesLink(
                policy_id=int(series_policy.id),
                series_id=int(second_series.id),
                sort_order=1,
            ),
        ]
    )
    await session.commit()

    statement_count = 0

    def count_warranty_selects(_conn, _cursor, statement, _parameters, _context, _many):
        nonlocal statement_count
        normalized = statement.casefold()
        if normalized.lstrip().startswith("select") and "warranty_policy" in normalized:
            statement_count += 1

    sync_engine = session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", count_warranty_selects)
    try:
        projected = await WarrantyPolicyResolver.resolve_public(
            session,
            [product, series_product, brand_product, no_policy_product],
            at=now,
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", count_warranty_selects)

    assert statement_count == 2
    assert projected[int(product.id)].model_dump() == {
        "duration_months": 54,
        "maintenance_required": True,
        "maintenance_interval_months": 12,
        "start_event": "installation",
        "allowed_maintenance_provider": "mvn",
        "grace_period_days": 30,
        "terms": "Annual maintenance is required.",
    }
    assert projected[int(series_product.id)].duration_months == 48
    assert projected[int(brand_product.id)].duration_months == 36
    assert projected[int(no_policy_product.id)] is None
    assert int(hidden_product.id) not in projected


@pytest.mark.asyncio
async def test_public_product_mapper_exposes_only_reviewed_warranty_fields(
    warranty_projection_session: AsyncSession,
):
    session = warranty_projection_session
    brand = Brand(title="Mapper warranty brand", slug="mapper-warranty-brand")
    session.add(brand)
    await session.flush()
    product = Product(
        title="Mapper warranty product",
        slug="mapper-warranty-product",
        price=1000,
        brand_id=brand.id,
    )
    sibling = Product(
        title="Mapper warranty sibling",
        slug="mapper-warranty-sibling",
        price=1100,
        brand_id=brand.id,
    )
    for item in (product, sibling):
        item.brand = brand
        item.tags = []
        item.gallery_images = []
        item.attachments = []
    session.add_all([product, sibling])
    await session.flush()
    session.add(
        WarrantyPolicy(
            name="Public mapper terms",
            brand_id=brand.id,
            duration_months=48,
            terms="Public conditions",
        )
    )
    await session.commit()

    warranties = await WarrantyPolicyResolver.resolve_public(
        session,
        [product, sibling],
    )
    response = map_product_to_response(
        PublicCatalogVisibilityService.project_product(product),
        series_siblings=[
            PublicCatalogVisibilityService.project_product(sibling)
        ],
        warranties=warranties,
    ).model_dump()

    expected = {
        "duration_months": 48,
        "maintenance_required": False,
        "maintenance_interval_months": None,
        "start_event": "commissioning",
        "allowed_maintenance_provider": "any",
        "grace_period_days": 0,
        "terms": "Public conditions",
    }
    assert response["warranty"] == expected
    assert response["series_siblings"][0]["warranty"] == expected
    assert set(response["warranty"]) == set(expected)


@pytest.mark.asyncio
async def test_warranty_policy_writes_invalidate_public_catalog(
    warranty_projection_session: AsyncSession,
):
    session = warranty_projection_session
    product = Product(
        title="Revision warranty product",
        slug="revision-warranty-product",
        price=1000,
    )
    session.add(product)
    await session.commit()
    before = await CatalogRevisionService.get_current(session)

    created = await WarrantyService.create_policy(
        session,
        payload={
            "name": "Revision warranty",
            "product_id": product.id,
            "duration_months": 36,
        },
    )
    after_create = await CatalogRevisionService.get_current(session)
    updated = await WarrantyService.update_policy(
        session,
        policy_id=created["id"],
        payload={"duration_months": 48},
    )
    after_update = await CatalogRevisionService.get_current(session)

    assert updated and updated["duration_months"] == 48
    assert after_create["revision"] == before["revision"] + 1
    assert after_update["revision"] == after_create["revision"] + 1
