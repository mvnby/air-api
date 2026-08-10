from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Feature, FeatureSeriesLink, ProductSeries
from services.feature_scope_policy import FeatureScopePolicy
from services.manager_brand_mutation_state import normalize_brand_feature_ids


class ManagerBrandSeriesFeatureOperations:
    @classmethod
    def _serialize_series_feature_link(
        cls,
        link: FeatureSeriesLink,
        feature: Feature,
    ) -> Dict[str, Any]:
        return {
            "id": feature.id,
            "title": link.override_title or feature.name,
            "slug": feature.slug,
            "text": (
                link.override_description
                if link.override_description is not None
                else feature.full_description
            ),
            "image_url": link.override_image_url or feature.image_url,
            "icon": link.override_icon or feature.icon,
            "footnote": link.override_footnote or feature.footnote,
            "source_url": feature.source_url,
            "aliases": cls._normalize_string_list(feature.aliases),
            "is_published": feature.is_active,
            "sort_order": int(
                link.sort_order if link.sort_order is not None else feature.sort_order or 0
            ),
            "is_featured": bool(link.is_featured),
        }

    @classmethod
    async def _load_series_brand_features(
        cls,
        session: AsyncSession,
        series_ids: List[int],
    ) -> Dict[int, List[Dict[str, Any]]]:
        normalized_ids = [int(value) for value in dict.fromkeys(series_ids) if value]
        if not normalized_ids:
            return {}

        rows = (
            await session.execute(
                select(FeatureSeriesLink, Feature, ProductSeries.brand_id)
                .join(Feature, Feature.id == FeatureSeriesLink.feature_id)
                .join(ProductSeries, ProductSeries.id == FeatureSeriesLink.series_id)
                .where(
                    FeatureSeriesLink.series_id.in_(normalized_ids),
                    FeatureSeriesLink.is_enabled.is_(True),
                )
                .order_by(
                    FeatureSeriesLink.series_id.asc(),
                    FeatureSeriesLink.is_featured.desc(),
                    FeatureSeriesLink.sort_order.asc(),
                    Feature.sort_order.asc(),
                    Feature.name.asc(),
                )
            )
        ).all()
        out: Dict[int, List[Dict[str, Any]]] = {
            series_id: [] for series_id in normalized_ids
        }
        for link, feature, brand_id in rows:
            if not FeatureScopePolicy.allows_target(
                feature,
                target_type="series",
                brand_id=brand_id,
            ):
                continue
            out.setdefault(int(link.series_id), []).append(
                cls._serialize_series_feature_link(link, feature)
            )
        return out

    @classmethod
    async def _sync_series_feature_assignments(
        cls,
        session: AsyncSession,
        *,
        series: ProductSeries,
        brand_id: int,
        assignments: Any,
    ) -> bool:
        normalized: list[tuple[int, bool]] = []
        seen: set[int] = set()
        for raw in assignments or []:
            data = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
            feature_id = int(data.get("feature_id") or 0)
            if feature_id <= 0 or feature_id in seen:
                raise HTTPException(
                    status_code=400,
                    detail="Фича серии указана повторно или некорректно",
                )
            seen.add(feature_id)
            normalized.append((feature_id, bool(data.get("is_featured", False))))
        if sum(1 for _, is_featured in normalized if is_featured) > 3:
            raise HTTPException(
                status_code=400,
                detail="У серии может быть не более трёх главных фич",
            )

        existing_links = list(
            (
                await session.execute(
                    select(FeatureSeriesLink).where(
                        FeatureSeriesLink.series_id == series.id
                    )
                )
            ).scalars().all()
        )
        await cls._validate_series_feature_ids(
            session,
            brand_id=brand_id,
            feature_ids=[feature_id for feature_id, _ in normalized],
            preserved_legacy_feature_ids={
                int(link.feature_id) for link in existing_links if link.is_enabled
            },
        )
        existing = {int(link.feature_id): link for link in existing_links}
        requested = {feature_id: is_featured for feature_id, is_featured in normalized}
        changed = set(existing) != set(requested)
        for link in existing_links:
            if int(link.feature_id) not in requested:
                await session.delete(link)

        next_sort_order = max(
            (int(link.sort_order or 0) for link in existing_links),
            default=0,
        )
        for feature_id, is_featured in normalized:
            link = existing.get(feature_id)
            if link is None:
                next_sort_order += 10
                link = FeatureSeriesLink(
                    series_id=int(series.id),
                    feature_id=feature_id,
                    sort_order=next_sort_order,
                )
            if (
                bool(link.is_featured) != is_featured
                or not link.is_enabled
                or link.source != "manual"
            ):
                changed = True
            link.is_featured = is_featured
            link.is_enabled = True
            link.source = "manual"
            session.add(link)
        return changed

    @classmethod
    async def _validate_series_feature_ids(
        cls,
        session: AsyncSession,
        *,
        brand_id: int,
        feature_ids: List[int],
        preserved_legacy_feature_ids: set[int] | None = None,
    ) -> None:
        if not feature_ids:
            return
        preserved_legacy_ids = preserved_legacy_feature_ids or set()
        candidates = list(
            (
                await session.execute(
                    select(Feature).where(
                        Feature.id.in_(feature_ids),
                        Feature.is_active.is_(True),
                        Feature.archived_at.is_(None),
                    )
                )
            ).scalars().all()
        )
        found_ids = {
            int(feature.id)
            for feature in candidates
            if (
                feature.scope_type in {"universal", "brand"}
                or (
                    int(feature.id) in preserved_legacy_ids
                    and feature.scope_type in {"series", "derived"}
                )
            )
            and FeatureScopePolicy.allows_target(
                feature,
                target_type="series",
                brand_id=brand_id,
            )
        }
        missing_ids = [
            feature_id for feature_id in feature_ids if feature_id not in found_ids
        ]
        if missing_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Фичи недоступны этой серии: {', '.join(map(str, missing_ids))}",
            )

    @classmethod
    async def _sync_series_brand_features(
        cls,
        session: AsyncSession,
        *,
        series: ProductSeries,
        brand_id: int,
        feature_ids: Any,
    ) -> bool:
        if not series.id:
            return False

        normalized_ids = normalize_brand_feature_ids(feature_ids)
        existing_links = (
            await session.execute(
                select(FeatureSeriesLink).where(FeatureSeriesLink.series_id == series.id)
            )
        ).scalars().all()
        existing_by_feature_id = {
            int(link.feature_id): link for link in existing_links
        }
        if set(existing_by_feature_id) == set(normalized_ids):
            return False

        await cls._validate_series_feature_ids(
            session,
            brand_id=brand_id,
            feature_ids=list(normalized_ids),
            preserved_legacy_feature_ids={
                int(link.feature_id) for link in existing_links if link.is_enabled
            },
        )

        keep_ids = set(normalized_ids)
        for link in existing_links:
            if int(link.feature_id) not in keep_ids:
                await session.delete(link)

        next_sort_order = max(
            (int(link.sort_order or 0) for link in existing_links),
            default=0,
        )
        for feature_id in normalized_ids:
            if feature_id not in existing_by_feature_id:
                next_sort_order += 10
                session.add(
                    FeatureSeriesLink(
                        series_id=int(series.id),
                        feature_id=feature_id,
                        sort_order=next_sort_order,
                    )
                )
        return True
