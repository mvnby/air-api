"""Confirmed migration of identical published-product Feature links to a series."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureProductLink,
    FeatureSeriesLink,
    Product,
    ProductSeries,
)
from schemas_features import (
    ManagerFeatureSeriesMigrationAppliedItem,
    ManagerFeatureSeriesMigrationApplyItem,
    ManagerFeatureSeriesMigrationApplyResponse,
    ManagerFeatureSeriesMigrationCandidate,
    ManagerFeatureSeriesMigrationPreviewResponse,
)
from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService


_OVERRIDE_FIELDS = (
    "override_title",
    "override_description",
    "override_media_id",
    "override_image_url",
    "override_icon",
    "override_footnote",
)


class FeatureSeriesMigrationService:
    @classmethod
    async def preview(
        cls,
        session: AsyncSession,
        *,
        series_ids: Iterable[int] | None = None,
    ) -> ManagerFeatureSeriesMigrationPreviewResponse:
        requested_series_ids = sorted({int(value) for value in series_ids or [] if int(value) > 0})
        stmt = (
            select(ProductSeries, Brand)
            .join(Brand, Brand.id == ProductSeries.brand_id)
            .order_by(ProductSeries.id.asc())
        )
        if requested_series_ids:
            stmt = stmt.where(ProductSeries.id.in_(requested_series_ids))
        series_rows = list((await session.execute(stmt)).all())
        if not series_rows:
            return ManagerFeatureSeriesMigrationPreviewResponse()
        selected_series_ids = [int(series.id) for series, _ in series_rows]
        products = list(
            (
                await session.execute(
                    select(Product)
                    .where(
                        Product.series_id.in_(selected_series_ids),
                        Product.is_published.is_(True),
                    )
                    .order_by(Product.series_id.asc(), Product.id.asc())
                )
            ).scalars().all()
        )
        products_by_series: dict[int, list[Product]] = defaultdict(list)
        product_series_by_id: dict[int, int] = {}
        for product in products:
            products_by_series[int(product.series_id)].append(product)
            product_series_by_id[int(product.id)] = int(product.series_id)

        link_rows: list[tuple[FeatureProductLink, Feature]] = []
        if product_series_by_id:
            link_rows = list(
                (
                    await session.execute(
                        select(FeatureProductLink, Feature)
                        .join(Feature, Feature.id == FeatureProductLink.feature_id)
                        .where(FeatureProductLink.product_id.in_(list(product_series_by_id)))
                        .order_by(FeatureProductLink.product_id, FeatureProductLink.feature_id)
                    )
                ).all()
            )
        links_by_series: dict[int, list[tuple[FeatureProductLink, Feature]]] = defaultdict(list)
        for link, feature in link_rows:
            links_by_series[product_series_by_id[int(link.product_id)]].append((link, feature))
        existing_series_pairs = set(
            (
                await session.execute(
                    select(FeatureSeriesLink.series_id, FeatureSeriesLink.feature_id).where(
                        FeatureSeriesLink.series_id.in_(selected_series_ids)
                    )
                )
            ).all()
        )
        brand_ids = {int(series.brand_id) for series, _ in series_rows if series.brand_id is not None}
        existing_brand_pairs = set(
            (
                await session.execute(
                    select(FeatureBrandLink.brand_id, FeatureBrandLink.feature_id).where(
                        FeatureBrandLink.brand_id.in_(brand_ids)
                    )
                )
            ).all()
        )
        candidates: list[ManagerFeatureSeriesMigrationCandidate] = []
        for series, brand in series_rows:
            candidates.extend(
                cls._series_candidates(
                    series=series,
                    brand=brand,
                    products=products_by_series.get(int(series.id), []),
                    rows=links_by_series.get(int(series.id), []),
                    existing_series_feature_ids={
                        int(feature_id)
                        for series_id, feature_id in existing_series_pairs
                        if int(series_id) == int(series.id)
                    },
                    existing_brand_feature_ids={
                        int(feature_id)
                        for brand_id, feature_id in existing_brand_pairs
                        if int(brand_id) == int(series.brand_id)
                    },
                )
            )
        candidates.sort(key=lambda item: (item.series_id, item.feature_id))
        return ManagerFeatureSeriesMigrationPreviewResponse(
            candidates=candidates,
            total=len(candidates),
        )

    @classmethod
    async def apply(
        cls,
        session: AsyncSession,
        items: list[ManagerFeatureSeriesMigrationApplyItem],
    ) -> ManagerFeatureSeriesMigrationApplyResponse:
        keys = [(item.series_id, item.feature_id) for item in items]
        if len(keys) != len(set(keys)):
            raise HTTPException(status_code=400, detail="Кандидат миграции указан дважды")

        results: list[ManagerFeatureSeriesMigrationAppliedItem] = []
        changed_product_ids: set[int] = set()
        try:
            await cls._prelock_batch(session, items)
            for item in sorted(items, key=lambda value: (value.series_id, value.feature_id)):
                result, product_ids = await cls._apply_one_prelocked(session, item)
                results.append(result)
                changed_product_ids.update(product_ids)
            await CatalogInvalidationCommitService.commit_registered_global_mutation(
                session,
                producer="feature_series_migration.apply",
                changed=bool(changed_product_ids),
                product_ids=sorted(changed_product_ids),
            )
        except Exception:
            await session.rollback()
            raise

        return ManagerFeatureSeriesMigrationApplyResponse(
            items=results,
            applied_count=sum(item.status == "applied" for item in results),
            already_applied_count=sum(item.status == "already_applied" for item in results),
            deleted_product_assignments=sum(item.deleted_product_assignments for item in results),
        )

    @staticmethod
    async def _prelock_batch(
        session: AsyncSession,
        items: list[ManagerFeatureSeriesMigrationApplyItem],
    ) -> None:
        """Acquire every mutable row class once in a global deterministic order."""

        if not items:
            return
        series_ids = sorted({int(item.series_id) for item in items})
        feature_ids = sorted({int(item.feature_id) for item in items})
        series_rows = list(
            (
                await session.execute(
                    select(ProductSeries)
                    .where(ProductSeries.id.in_(series_ids))
                    .order_by(ProductSeries.id.asc())
                    .with_for_update()
                )
            ).scalars().all()
        )
        brand_ids = sorted(
            {int(series.brand_id) for series in series_rows if series.brand_id is not None}
        )
        if brand_ids:
            await session.execute(
                select(Brand.id)
                .where(Brand.id.in_(brand_ids))
                .order_by(Brand.id.asc())
                .with_for_update()
            )
        await session.execute(
            select(Feature.id)
            .where(Feature.id.in_(feature_ids))
            .order_by(Feature.id.asc())
            .with_for_update()
        )
        product_ids = list(
            (
                await session.execute(
                    select(Product.id)
                    .where(
                        Product.series_id.in_(series_ids),
                        Product.is_published.is_(True),
                    )
                    .order_by(Product.series_id.asc(), Product.id.asc())
                    .with_for_update()
                )
            ).scalars().all()
        )
        if product_ids:
            await session.execute(
                select(FeatureProductLink.id)
                .where(
                    FeatureProductLink.product_id.in_(product_ids),
                    FeatureProductLink.feature_id.in_(feature_ids),
                )
                .order_by(
                    FeatureProductLink.product_id.asc(),
                    FeatureProductLink.feature_id.asc(),
                )
                .with_for_update()
            )
        await session.execute(
            select(FeatureSeriesLink.id)
            .where(
                FeatureSeriesLink.series_id.in_(series_ids),
                FeatureSeriesLink.feature_id.in_(feature_ids),
            )
            .order_by(
                FeatureSeriesLink.series_id.asc(),
                FeatureSeriesLink.feature_id.asc(),
            )
            .with_for_update()
        )
        if brand_ids:
            await session.execute(
                select(FeatureBrandLink.id)
                .where(
                    FeatureBrandLink.brand_id.in_(brand_ids),
                    FeatureBrandLink.feature_id.in_(feature_ids),
                )
                .order_by(
                    FeatureBrandLink.brand_id.asc(),
                    FeatureBrandLink.feature_id.asc(),
                )
                .with_for_update()
            )

    @classmethod
    def _series_candidates(
        cls,
        *,
        series: ProductSeries,
        brand: Brand,
        products: list[Product],
        rows: list[tuple[FeatureProductLink, Feature]],
        existing_series_feature_ids: set[int],
        existing_brand_feature_ids: set[int],
    ) -> list[ManagerFeatureSeriesMigrationCandidate]:
        if not products or any(product.brand_id != series.brand_id for product in products):
            return []
        product_ids = [int(product.id) for product in products]
        valid_by_feature: dict[int, list[FeatureProductLink]] = defaultdict(list)
        feature_by_id: dict[int, Feature] = {}
        for link, feature in rows:
            if not cls._eligible_link(link) or not cls._eligible_feature(feature, int(series.brand_id)):
                continue
            valid_by_feature[int(link.feature_id)].append(link)
            feature_by_id[int(feature.id)] = feature

        result: list[ManagerFeatureSeriesMigrationCandidate] = []
        expected_products = set(product_ids)
        for feature_id, links in sorted(valid_by_feature.items()):
            if (
                feature_id in existing_series_feature_ids
                or feature_id in existing_brand_feature_ids
            ):
                continue
            if {int(link.product_id) for link in links} != expected_products:
                continue
            sort_orders = {int(link.sort_order) for link in links}
            if len(sort_orders) != 1:
                continue
            feature = feature_by_id[feature_id]
            sort_order = sort_orders.pop()
            result.append(
                ManagerFeatureSeriesMigrationCandidate(
                    candidate_token=cls._token(
                        series_id=int(series.id),
                        brand_id=int(series.brand_id),
                        feature_id=feature_id,
                        product_ids=product_ids,
                        sort_order=sort_order,
                    ),
                    series_id=int(series.id),
                    series_title=series.title,
                    brand_id=int(series.brand_id),
                    brand_title=brand.title,
                    feature_id=feature_id,
                    feature_name=feature.name,
                    feature_slug=feature.slug,
                    published_products_count=len(product_ids),
                    matching_assignments_count=len(links),
                    sort_order=sort_order,
                )
            )
        return result

    @classmethod
    async def _apply_one_prelocked(
        cls,
        session: AsyncSession,
        item: ManagerFeatureSeriesMigrationApplyItem,
    ) -> tuple[ManagerFeatureSeriesMigrationAppliedItem, list[int]]:
        series = (
            await session.execute(
                select(ProductSeries)
                .where(ProductSeries.id == item.series_id)
            )
        ).scalar_one_or_none()
        feature = (
            await session.execute(
                select(Feature).where(Feature.id == item.feature_id)
            )
        ).scalar_one_or_none()
        if series is None or feature is None or series.brand_id is None:
            cls._stale()
        assert series is not None and feature is not None and series.brand_id is not None
        if not cls._eligible_feature(feature, int(series.brand_id)):
            cls._stale()

        products = list(
            (
                await session.execute(
                    select(Product)
                    .where(Product.series_id == series.id, Product.is_published.is_(True))
                    .order_by(Product.id.asc())
                )
            ).scalars().all()
        )
        if not products or any(product.brand_id != series.brand_id for product in products):
            cls._stale()
        product_ids = [int(product.id) for product in products]
        product_links = list(
            (
                await session.execute(
                    select(FeatureProductLink)
                    .where(
                        FeatureProductLink.product_id.in_(product_ids),
                        FeatureProductLink.feature_id == feature.id,
                    )
                    .order_by(FeatureProductLink.product_id.asc())
                )
            ).scalars().all()
        )
        series_link = (
            await session.execute(
                select(FeatureSeriesLink)
                .where(
                    FeatureSeriesLink.series_id == series.id,
                    FeatureSeriesLink.feature_id == feature.id,
                )
            )
        ).scalar_one_or_none()
        brand_link = (
            await session.execute(
                select(FeatureBrandLink.id).where(
                    FeatureBrandLink.brand_id == series.brand_id,
                    FeatureBrandLink.feature_id == feature.id,
                )
            )
        ).scalar_one_or_none()

        if series_link is not None and not product_links and brand_link is None:
            replay_token = cls._token(
                series_id=int(series.id),
                brand_id=int(series.brand_id),
                feature_id=int(feature.id),
                product_ids=product_ids,
                sort_order=int(series_link.sort_order),
            )
            if (
                replay_token == item.candidate_token
                and series_link.source == "manual"
                and series_link.is_enabled
                and not cls._has_override(series_link)
            ):
                return (
                    ManagerFeatureSeriesMigrationAppliedItem(
                        series_id=int(series.id),
                        feature_id=int(feature.id),
                        status="already_applied",
                    ),
                    [],
                )
            cls._stale()

        if series_link is not None or brand_link is not None:
            cls._stale()
        if len(product_links) != len(product_ids) or any(
            not cls._eligible_link(link) for link in product_links
        ):
            cls._stale()
        sort_orders = {int(link.sort_order) for link in product_links}
        if len(sort_orders) != 1:
            cls._stale()
        sort_order = sort_orders.pop()
        expected_token = cls._token(
            series_id=int(series.id),
            brand_id=int(series.brand_id),
            feature_id=int(feature.id),
            product_ids=product_ids,
            sort_order=sort_order,
        )
        if expected_token != item.candidate_token:
            cls._stale()

        session.add(
            FeatureSeriesLink(
                series_id=int(series.id),
                feature_id=int(feature.id),
                source="manual",
                is_enabled=True,
                is_featured=False,
                sort_order=sort_order,
            )
        )
        for link in product_links:
            await session.delete(link)
        await session.flush()
        return (
            ManagerFeatureSeriesMigrationAppliedItem(
                series_id=int(series.id),
                feature_id=int(feature.id),
                status="applied",
                deleted_product_assignments=len(product_links),
            ),
            product_ids,
        )

    @staticmethod
    def _eligible_feature(feature: Feature, brand_id: int) -> bool:
        return bool(
            feature.is_active
            and feature.archived_at is None
            and (
                feature.scope_type == "universal"
                or (feature.scope_type == "brand" and feature.brand_id == brand_id)
            )
        )

    @classmethod
    def _eligible_link(cls, link: FeatureProductLink) -> bool:
        return bool(
            link.source == "manual"
            and link.is_enabled
            and not cls._has_override(link)
        )

    @staticmethod
    def _has_override(link: object) -> bool:
        return any(getattr(link, field, None) is not None for field in _OVERRIDE_FIELDS)

    @staticmethod
    def _token(
        *,
        series_id: int,
        brand_id: int,
        feature_id: int,
        product_ids: Iterable[int],
        sort_order: int,
    ) -> str:
        payload = json.dumps(
            {
                "v": 1,
                "series_id": series_id,
                "brand_id": brand_id,
                "feature_id": feature_id,
                "published_product_ids": sorted(int(value) for value in product_ids),
                "sort_order": sort_order,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _stale() -> None:
        raise HTTPException(
            status_code=409,
            detail="Кандидат изменился; обновите preview и подтвердите заново",
        )
