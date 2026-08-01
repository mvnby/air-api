from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from crud.catalog_revision import CatalogRevisionDAO
from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureCategory,
    IntegrationOutboxEvent,
    Storefront,
    Tenant,
)
from services.catalog_invalidation_contracts import (
    CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
)
from services.feature_assignment_service import FeatureAssignmentService


@pytest.mark.asyncio
async def test_repeated_feature_link_delete_keeps_revision_and_outbox_stable(
    tmp_path: Path,
):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'feature-delete.db'}",
        echo=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        tenant = Tenant(
            id=1,
            slug="system",
            display_name="System",
            status="active",
            is_system=True,
        )
        session.add(tenant)
        await session.flush()
        session.add(
            Storefront(
                id=1,
                tenant_id=1,
                slug="main",
                display_name="Main",
                status="active",
                is_default=True,
            )
        )
        category = FeatureCategory(slug="comfort", name="Comfort")
        brand = Brand(slug="test-brand", title="Test Brand")
        session.add_all([category, brand])
        await session.flush()
        feature = Feature(
            slug="quiet",
            name="Quiet",
            category_id=category.id,
            scope_type="brand",
            brand_id=brand.id,
        )
        session.add(feature)
        await session.flush()
        session.add(FeatureBrandLink(brand_id=brand.id, feature_id=feature.id))
        await session.commit()

        for _ in range(2):
            await FeatureAssignmentService.delete_target_link(
                session,
                feature_id=feature.id,
                target_type="brand",
                target_id=brand.id,
            )

        revision = await CatalogRevisionDAO.get_current(session)
        events = (
            await session.execute(
                select(IntegrationOutboxEvent).where(
                    IntegrationOutboxEvent.event_type
                    == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
                )
            )
        ).scalars().all()
        links = (await session.execute(select(FeatureBrandLink))).scalars().all()

        assert revision.revision == 1
        assert len(events) == 1
        assert events[0].payload["reason"] == "feature_brand_link_delete"
        assert links == []

    await engine.dispose()
