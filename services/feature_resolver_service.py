from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload
from sqlmodel import select

from models import (
    Feature,
    FeatureBrandLink,
    FeatureProductLink,
    FeatureRule,
    FeatureSeriesLink,
    MediaAsset,
    Product,
)
from schemas_features import FeatureCategoryResponse, FeatureLinkPayload, PublicFeatureResponse
from services.feature_rule_engine import describe_rules, matches_all_rules
from services.feature_presentation import feature_display_mode
from services.feature_scope_policy import FeatureScopePolicy


@dataclass
class FeatureIdResolutionCache:
    """Small shared dictionary for one paged traversal of eligible products."""

    features: dict[int, Feature] | None = None
    rule_ids: set[int] = field(default_factory=set)
    brand_links: dict[int, list[FeatureBrandLink]] = field(default_factory=dict)
    series_links: dict[int, list[FeatureSeriesLink]] = field(default_factory=dict)


class FeatureResolverService:
    @staticmethod
    async def resolve_for_products(
        session: AsyncSession,
        products: Iterable[Product],
        *,
        include_suggestions: bool = False,
        id_cache: FeatureIdResolutionCache | None = None,
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
            session, FeatureBrandLink, FeatureBrandLink.brand_id, brand_ids,
            cached=id_cache.brand_links if id_cache is not None else None,
        )
        series_links = await FeatureResolverService._load_links(
            session, FeatureSeriesLink, FeatureSeriesLink.series_id, series_ids,
            cached=id_cache.series_links if id_cache is not None else None,
        )
        feature_stmt = select(Feature).where(Feature.is_active.is_(True), Feature.archived_at.is_(None))
        if id_cache is not None:
            if id_cache.features is None:
                statement = feature_stmt.options(
                    load_only(Feature.id, Feature.scope_type, Feature.brand_id, Feature.replaces_feature_id),
                    selectinload(Feature.rules),
                )
                id_cache.features = {f.id: f for f in (await session.execute(statement)).scalars()}
                id_cache.rule_ids = {fid for fid, f in id_cache.features.items() if any(r.is_active for r in f.rules)}
            features = id_cache.features
            media = {}
        else:
            links = [*product_links, *brand_links, *series_links]
            linked_feature_ids = {int(link.feature_id) for link in links}
            statement = feature_stmt.where(
                (Feature.id.in_(linked_feature_ids or {-1})) | Feature.rules.any(FeatureRule.is_active.is_(True))
            ).options(selectinload(Feature.category), selectinload(Feature.rules))
            feature_rows = list((await session.execute(statement)).scalars())
            features = {f.id: f for f in feature_rows}
            media = await FeatureResolverService._load_media(session, feature_rows, links)

        product_link_map = FeatureResolverService._by_target(product_links, "product_id")
        brand_link_map = FeatureResolverService._by_target(brand_links, "brand_id")
        series_link_map = FeatureResolverService._by_target(series_links, "series_id")
        resolved_by_product: dict[int, dict[str, Any]] = {}

        for product in product_list:
            pid = int(product.id)
            specs = dict(product.specs) if isinstance(product.specs, dict) else {}
            specs.setdefault("is_inverter", product.is_inverter)
            specs.setdefault("power_cooling", product.power_cooling)
            effective: list[PublicFeatureResponse] = []
            effective_ids: set[int] = set()
            suggestions: list[PublicFeatureResponse] = []
            inherited: list[PublicFeatureResponse] = []
            manual: list[PublicFeatureResponse] = []
            disabled_ids: list[int] = []
            applicable_feature_ids: set[int] = set()

            p_links = product_link_map.get(pid, {})
            s_links = series_link_map.get(int(product.series_id or 0), {})
            b_links = brand_link_map.get(int(product.brand_id or 0), {})
            candidates = features.keys()
            if id_cache is not None:
                candidates = features.keys() & (p_links.keys() | s_links.keys() | b_links.keys() | id_cache.rule_ids)
            for feature_id in candidates:
                feature = features[feature_id]
                p_link, s_link, b_link = p_links.get(feature_id), s_links.get(feature_id), b_links.get(feature_id)
                if not FeatureScopePolicy.allows_product(
                    feature,
                    product,
                    has_series_link=s_link is not None,
                    has_product_link=p_link is not None,
                ):
                    continue
                matched = matches_all_rules(specs, feature.rules) if feature.rules else False
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
                elif feature.scope_type == "universal" and feature.rules and matched:
                    chosen, source = None, "derived"
                elif (
                    p_link is not None
                    and p_link.source == "derived"
                    and p_link.is_enabled
                    and feature.rules
                    and matched
                ):
                    # Read compatibility for historical stored derived links.
                    chosen, source = p_link, "derived"

                if source is not None:
                    if id_cache is not None:
                        effective_ids.add(feature_id)
                        continue
                    item = FeatureResolverService._serialize_resolved(
                        feature,
                        chosen,
                        source=source,
                        media=media,
                        applied_rule=describe_rules(list(feature.rules or [])) if source == "derived" else None,
                        display_mode=FeatureResolverService._display_mode(p_link, s_link, b_link),
                    )
                    if s_link is not None and s_link.is_enabled:
                        item.is_featured = bool(s_link.is_featured)
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
                    and feature.scope_type == "derived"
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

            if id_cache is not None:
                # Facets need the identical scope, overrides and replacements without
                # serializing media or building the full editorial workspace per model.
                suppressed = FeatureResolverService._replacement_targets(effective_ids, features)
                resolved_by_product[pid] = {"effective_ids": effective_ids - suppressed}
                continue
            sort_key = FeatureResolverService._sort_key
            suppressed_ids = FeatureResolverService._replacement_targets((item.id for item in effective), features)
            if suppressed_ids:
                effective = [item for item in effective if item.id not in suppressed_ids]
                inherited = [item for item in inherited if item.id not in suppressed_ids]
                manual = [item for item in manual if item.id not in suppressed_ids]
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
                suppressed_series_ids = FeatureResolverService._replacement_targets(
                    (item.id for item in series_items),
                    features,
                )
                if suppressed_series_ids:
                    series_items = [
                        item for item in series_items if item.id not in suppressed_series_ids
                    ]
                series.__dict__["_resolved_features"] = sorted(series_items, key=sort_key)

        return resolved_by_product

    @staticmethod
    async def _load_links(session, model, target_column, target_ids, *, cached=None):
        missing = set(target_ids) - cached.keys() if cached is not None else target_ids
        rows = []
        if missing:
            rows = list((await session.execute(select(model).where(target_column.in_(missing)))).scalars())
        if cached is None:
            return rows
        cached.update({target_id: [] for target_id in missing})
        for row in rows:
            cached[getattr(row, target_column.key)].append(row)
        return [link for target_id in target_ids for link in cached[target_id]]

    @staticmethod
    def _by_target(links, target_name: str):
        payload = defaultdict(dict)
        for link in links:
            payload[int(getattr(link, target_name))][int(link.feature_id)] = link
        return payload

    @staticmethod
    def _display_mode(product_link: Any, series_link: Any, brand_link: Any) -> str:
        """Keep authored formats; unconfigured ordinary features stay compact."""
        if (
            product_link is not None and product_link.is_enabled
            and product_link.source != "derived" and product_link.display_mode
        ):
            return product_link.display_mode
        for link in (series_link, brand_link):
            if link is not None and link.is_enabled:
                return feature_display_mode(link.display_mode, is_featured=getattr(link, "is_featured", False))
        return "icon"

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
                "display_mode",
            )
        )

    @staticmethod
    def _replacement_targets(
        feature_ids: Iterable[int],
        features: dict[int, Feature],
    ) -> set[int]:
        targets: set[int] = set()
        for feature_id in feature_ids:
            feature = features.get(feature_id)
            if (
                feature is not None
                and feature.scope_type == "brand"
                and feature.replaces_feature_id is not None
            ):
                targets.add(int(feature.replaces_feature_id))
        return targets

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
                    display_mode=link.display_mode,
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
        display_mode: str | None = None,
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
            icon_caption=feature.icon_caption,
            display_mode=feature_display_mode(display_mode or getattr(link, "display_mode", None), is_featured=getattr(link, "is_featured", False)),
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
            is_featured=bool(getattr(link, "is_featured", False)) if link else False,
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
            not item.is_featured,
            item.sort_order,
            item.category.sort_order,
            item.feature_sort_order,
            item.name.casefold(),
            item.id,
        )
