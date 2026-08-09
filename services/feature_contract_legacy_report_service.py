"""Read-only inventory for legacy Feature-contract data."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Feature, FeatureBrandLink, FeatureProductLink, ProductSeries


class FeatureContractLegacyReportService:
    @classmethod
    async def build(cls, session: AsyncSession, *, sample_limit: int = 25) -> dict[str, Any]:
        limit = max(1, min(int(sample_limit), 100))
        scopes: dict[str, dict[str, Any]] = {}
        for scope_type in ("series", "product", "derived"):
            scopes[scope_type] = await cls._count_and_sample(
                session,
                Feature.id,
                Feature.scope_type == scope_type,
                limit=limit,
            )

        brand_links = await cls._count_and_sample(
            session,
            FeatureBrandLink.id,
            limit=limit,
        )
        stored_derived = await cls._count_and_sample(
            session,
            FeatureProductLink.id,
            FeatureProductLink.source == "derived",
            limit=limit,
        )
        overrides = await cls._count_and_sample(
            session,
            FeatureProductLink.id,
            or_(
                FeatureProductLink.override_title.is_not(None),
                FeatureProductLink.override_description.is_not(None),
                FeatureProductLink.override_media_id.is_not(None),
                FeatureProductLink.override_image_url.is_not(None),
                FeatureProductLink.override_icon.is_not(None),
                FeatureProductLink.override_footnote.is_not(None),
            ),
            limit=limit,
        )
        legacy_series_rows = list(
            (
                await session.execute(
                    select(ProductSeries.id, ProductSeries.features, ProductSeries.feature_blocks)
                    .order_by(ProductSeries.id.asc())
                )
            ).all()
        )
        features_ids = [int(row.id) for row in legacy_series_rows if row.features]
        feature_blocks_ids = [int(row.id) for row in legacy_series_rows if row.feature_blocks]
        return {
            "legacy_feature_scopes": scopes,
            "feature_brand_links": brand_links,
            "stored_derived_product_links": stored_derived,
            "product_feature_overrides": overrides,
            "product_series_legacy_content": {
                "features": {
                    "count": len(features_ids),
                    "sample_series_ids": features_ids[:limit],
                },
                "feature_blocks": {
                    "count": len(feature_blocks_ids),
                    "sample_series_ids": feature_blocks_ids[:limit],
                },
            },
        }

    @staticmethod
    async def _count_and_sample(
        session: AsyncSession,
        id_column: Any,
        *criteria: Any,
        limit: int,
    ) -> dict[str, Any]:
        count_stmt = select(func.count(id_column))
        sample_stmt = select(id_column).order_by(id_column.asc()).limit(limit)
        if criteria:
            count_stmt = count_stmt.where(*criteria)
            sample_stmt = sample_stmt.where(*criteria)
        count = int((await session.execute(count_stmt)).scalar_one() or 0)
        sample_ids = list((await session.execute(sample_stmt)).scalars().all())
        return {"count": count, "sample_ids": sample_ids}
