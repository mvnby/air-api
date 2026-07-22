from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    Feature,
    FeatureBrandLink,
    FeatureProductLink,
    FeatureSeriesLink,
    MediaAsset,
    Product,
)
from schemas_features import FeatureCategoryResponse, FeatureLinkPayload, PublicFeatureResponse
from services.feature_rule_engine import describe_rules, matches_all_rules
from services.feature_scope_policy import FeatureScopePolicy


class FeatureResolverService:
    @staticmethod
    async def resolve_for_products(
        session: AsyncSession,
        products: Iterable[Product],
        *,
        include_suggestions: bool = False,
    ) -> dict[int, dict[str, Any]]:
        product_list = [product for product in products if product.id is not None]
        if not product_list:
            return {}

        product_ids = [int(product.id) for product in product_list]
        brand_ids = {int(product.brand_id) for product in product_list if product.brand_id is not None}
        series_ids = {int(product.series_id) for product in product_list if product.series_id is not None}

        product_links = await FeatureResolverService._load_links(
            session, FeatureProductLink, FeatureProductLink.product_id, product_ids
        )
        brand_links = await FeatureResolverService._load_links(
            session, FeatureBrandLink, FeatureBrandLink.brand_id, brand_ids
        )
        series_links = await FeatureResolverService._load_links(
            session, FeatureSeriesLink, FeatureSeriesLink.series_id, series_ids
        )
        feature_stmt = (
            select(Feature)
            .where(Feature.is_active.is_(True), Feature.archived_at.is_(None))
            .options(selectinload(Feature.category), selectinload(Feature.rules))
        )
        if not include_suggestions:
            linked_feature_ids = {
                int(link.feature_id)
                for link in (*product_links, *brand_links, *series_links)
            }
            feature_stmt = feature_stmt.where(Feature.id.in_(linked_feature_ids or {-1}))
        feature_rows = list((await session.execute(feature_stmt)).scalars().all())
        features = {int(feature.id): feature for feature in feature_rows if feature.id is not None}
        media = await FeatureResolverService._load_media(
            session,
            feature_rows,
            [*product_links, *brand_links, *series_links],
        )

        product_link_map = FeatureResolverService._by_target(product_links, "product_id")
        brand_link_map = FeatureResolverService._by_target(brand_links, "brand_id")
        series_link_map = FeatureResolverService._by_target(series_links, "series_id")
        resolved_by_product: dict[int, dict[str, Any]] = {}

        for product in product_list:
            pid = int(product.id)
            specs = dict(product.specs or {})
            specs.setdefault("is_inverter", product.is_inverter)
            specs.setdefault("power_cooling", product.power_cooling)
            effective: list[PublicFeatureResponse] = []
            suggestions: list[PublicFeatureResponse] = []
            inherited: list[PublicFeatureResponse] = []
            manual: list[PublicFeatureResponse] = []
            disabled_ids: list[int] = []
            applicable_feature_ids: set[int] = set()

            for feature_id, feature in features.items():
                p_link = product_link_map.get(pid, {}).get(feature_id)
                s_link = series_link_map.get(int(product.series_id or 0), {}).get(feature_id)
                b_link = brand_link_map.get(int(product.brand_id or 0), {}).get(feature_id)
                matched = matches_all_rules(specs, list(feature.rules or []))
                if not FeatureScopePolicy.allows_product(
                    feature,
                    product,
                    has_series_link=s_link is not None,
                    has_product_link=p_link is not None,
                ):
                    continue
                applicable_feature_ids.add(feature_id)
                chosen = None
                source = None

                if p_link is not None and p_link.source != "derived":
                    if not p_link.is_enabled:
                        disabled_ids.append(feature_id)
                        continue
                    chosen = p_link
                    source = (
                        "product_override" if FeatureResolverService._has_override(p_link) else "product_manual"
                    )
                elif s_link is not None:
                    if not s_link.is_enabled:
                        disabled_ids.append(feature_id)
                        continue
                    chosen, source = s_link, "series"
                elif b_link is not None:
                    if not b_link.is_enabled:
                        disabled_ids.append(feature_id)
                        continue
                    chosen, source = b_link, "brand"
                elif p_link is not None and p_link.source == "derived" and matched:
                    if not p_link.is_enabled:
                        disabled_ids.append(feature_id)
                        continue
                    chosen, source = p_link, "derived"

                if chosen is not None and source is not None:
                    item = FeatureResolverService._serialize_resolved(
                        feature,
                        chosen,
                        source=source,
                        media=media,
                        applied_rule=describe_rules(list(feature.rules or [])) if source == "derived" else None,
                    )
                    effective.append(item)
                    if source in {"series", "brand"}:
                        inherited.append(item)
                    elif source in {"product_manual", "product_override"}:
                        manual.append(item)
                    continue

                if (
                    include_suggestions
                    and matched
                    and feature.rules
                    and FeatureScopePolicy.allows_product(
                        feature,
                        product,
                        has_series_link=s_link is not None,
                        has_product_link=p_link is not None,
                        mode="suggestion",
                    )
                ):
                    suggestions.append(
                        FeatureResolverService._serialize_resolved(
                            feature,
                            None,
                            source="derived",
                            media=media,
                            applied_rule=describe_rules(list(feature.rules or [])),
                        )
                    )

            sort_key = FeatureResolverService._sort_key
            payload = {
                "effective": sorted(effective, key=sort_key),
                "automatic_suggestions": sorted(suggestions, key=sort_key),
                "inherited": sorted(inherited, key=sort_key),
                "manual": sorted(manual, key=sort_key),
                "manual_assignments": FeatureResolverService._manual_assignments(
                    link
                    for feature_id, link in product_link_map.get(pid, {}).items()
                    if feature_id in applicable_feature_ids
                ),
                "disabled_feature_ids": sorted(set(disabled_ids)),
            }
            resolved_by_product[pid] = payload
            product.__dict__["_resolved_features"] = payload["effective"]
            product.__dict__["_feature_workspace"] = payload
            series = product.__dict__.get("series")
            if series is not None:
                series_items: list[PublicFeatureResponse] = []
                for feature_id, feature in features.items():
                    s_link = series_link_map.get(int(product.series_id or 0), {}).get(feature_id)
                    b_link = brand_link_map.get(int(product.brand_id or 0), {}).get(feature_id)
                    if not FeatureScopePolicy.allows_product(
                        feature,
                        product,
                        has_series_link=s_link is not None,
                        has_product_link=False,
                    ):
                        continue
                    chosen, source = (s_link, "series") if s_link is not None else (b_link, "brand")
                    if chosen is None or not chosen.is_enabled:
                        continue
                    series_items.append(
                        FeatureResolverService._serialize_resolved(
                            feature,
                            chosen,
                            source=source,
                            media=media,
                            applied_rule=None,
                        )
                    )
                series.__dict__["_resolved_features"] = sorted(series_items, key=sort_key)

        return resolved_by_product

    @staticmethod
    async def _load_links(session, model, target_column, target_ids):
        if not target_ids:
            return []
        return list((await session.execute(select(model).where(target_column.in_(target_ids)))).scalars().all())

    @staticmethod
    def _by_target(links, target_name: str):
        payload = defaultdict(dict)
        for link in links:
            payload[int(getattr(link, target_name))][int(link.feature_id)] = link
        return payload

    @staticmethod
    async def _load_media(session: AsyncSession, features: list[Feature], links: list[Any]):
        ids = {
            int(value)
            for feature in features
            for value in (feature.icon_media_id, feature.image_media_id)
            if value is not None
        }
        ids.update(int(link.override_media_id) for link in links if link.override_media_id is not None)
        if not ids:
            return {}
        rows = list((await session.execute(select(MediaAsset).where(MediaAsset.id.in_(ids)))).scalars().all())
        return {int(item.id): item.url for item in rows if item.id is not None}

    @staticmethod
    def _has_override(link: Any) -> bool:
        return any(
            getattr(link, name, None) is not None
            for name in (
                "override_title",
                "override_description",
                "override_media_id",
                "override_image_url",
                "override_icon",
                "override_footnote",
            )
        )

    @staticmethod
    def _manual_assignments(links: Iterable[Any]) -> list[FeatureLinkPayload]:
        payload = []
        for link in links:
            if link.source != "manual":
                continue
            payload.append(
                FeatureLinkPayload(
                    feature_id=int(link.feature_id),
                    source="manual",
                    is_enabled=link.is_enabled,
                    sort_order=link.sort_order,
                    override_title=link.override_title,
                    override_description=link.override_description,
                    override_media_id=link.override_media_id,
                    override_image_url=link.override_image_url,
                    override_icon=link.override_icon,
                    override_footnote=link.override_footnote,
                )
            )
        return sorted(payload, key=lambda item: (item.sort_order, item.feature_id))

    @staticmethod
    def _serialize_resolved(
        feature: Feature,
        link: Any | None,
        *,
        source: str,
        media: dict[int, str],
        applied_rule: str | None,
    ) -> PublicFeatureResponse:
        category = feature.category
        override_media_id = getattr(link, "override_media_id", None) if link else None
        image_url = (
            media.get(int(override_media_id)) if override_media_id is not None else None
        ) or (getattr(link, "override_image_url", None) if link else None) or (
            media.get(int(feature.image_media_id)) if feature.image_media_id is not None else None
        ) or feature.image_url
        icon_url = media.get(int(feature.icon_media_id)) if feature.icon_media_id is not None else None
        return PublicFeatureResponse(
            id=int(feature.id),
            slug=feature.slug,
            name=(getattr(link, "override_title", None) if link else None) or feature.name,
            short_description=feature.short_description,
            full_description=(
                getattr(link, "override_description", None) if link and link.override_description is not None
                else feature.full_description
            ),
            category=FeatureCategoryResponse(
                id=int(category.id),
                slug=category.slug,
                name=category.name,
                sort_order=category.sort_order,
                is_active=category.is_active,
            ),
            scope_type=feature.scope_type,
            source=source,
            is_overridden=FeatureResolverService._has_override(link) if link else False,
            sort_order=int(link.sort_order if link is not None else feature.sort_order),
            feature_sort_order=feature.sort_order,
            icon=(getattr(link, "override_icon", None) if link else None) or feature.icon,
            icon_url=icon_url,
            image_url=image_url,
            video_url=feature.video_url,
            footnote=(getattr(link, "override_footnote", None) if link else None) or feature.footnote,
            applied_rule=applied_rule,
        )

    @staticmethod
    def _sort_key(item: PublicFeatureResponse):
        return (
            item.sort_order,
            item.category.sort_order,
            item.feature_sort_order,
            item.name.casefold(),
            item.id,
        )
