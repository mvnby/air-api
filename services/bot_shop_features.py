"""Evaluate catalog features on eligible models, before any page boundaries."""

from collections import Counter
from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from sqlmodel import select

from api_contracts.bot_shop import BotShopFacetsResponse, BotShopFilters
from models import Feature, FeatureCategory, Product, ProductSeries
from models.product_constants import BTU_MAPPING
from models.tenancy import TenantScope
from services.catalog_decision_projection import (
    SUPPORTED_COOLING_BTU_CLASSES, CatalogDecisionFilters, CatalogDecisionQueryService,
)
from services.feature_resolver_service import FeatureIdResolutionCache, FeatureResolverService


async def _candidates(
    session: AsyncSession, scope: TenantScope, filters: CatalogDecisionFilters, *,
    sort: str = "title", direction: str = "asc",
):
    base = await CatalogDecisionQueryService.filtered_products_query(
        session, tenant_scope=scope, filters=filters, include_supplier_details=False,
    )
    columns = base.selected_columns
    statement = (
        base.with_only_columns(Product, columns.brand_title, columns.series_title,
                               ProductSeries.brand_id.label("series_brand_id"), columns.cooling_power_kw, columns.area_m2)
        .options(load_only(Product.id, Product.brand_id, Product.series_id, Product.specs,
                           Product.is_inverter, Product.power_cooling))
        .order_by(*CatalogDecisionQueryService.product_order(base, filters, sort, direction))
    )
    # Source JSON can contain large import records. Keep only a bounded batch alive
    # while applying the canonical rule, inheritance and override resolver.
    stream = await session.stream(statement.execution_options(yield_per=128))
    cache = FeatureIdResolutionCache()
    try:
        async for batch in stream.partitions(128):
            resolved = await FeatureResolverService.resolve_for_products(
                session, [row[0] for row in batch], id_cache=cache,
            )
            for row in batch:
                yield row, resolved[row[0].id]["effective_ids"]
    finally:
        await stream.close()


async def feature_page(
    session: AsyncSession, scope: TenantScope, filters: CatalogDecisionFilters, *,
    feature_ids: list[int], sort: str, direction: str, page: int, limit: int,
) -> tuple[list[int], int]:
    wanted = set(feature_ids)
    start = (page - 1) * limit
    selected = []
    total = 0
    async for row, effective in _candidates(session, scope, filters, sort=sort, direction=direction):
        if wanted.issubset(effective):
            if start <= total < start + limit:
                selected.append(row[0].id)
            total += 1
    return selected, total


def _btu_classes(nominal: float | None, area: float | None) -> set[int]:
    value = nominal if nominal is not None else area
    if value is None:
        return set()
    key = "power" if nominal is not None else "area"
    return {
        btu for btu in SUPPORTED_COOLING_BTU_CLASSES
        if BTU_MAPPING[str(btu)][key][0] <= value <= BTU_MAPPING[str(btu)][key][1]
    }


async def facets(
    session: AsyncSession, scope: TenantScope, filters: CatalogDecisionFilters, selected: BotShopFilters,
) -> BotShopFacetsResponse:
    requested_brands, requested_series = set(filters.brand_ids), set(filters.series_ids)
    requested_btu, requested_features = set(filters.cooling_btu_classes), set(selected.feature_ids)
    base_filters = replace(filters, brand_ids=(), series_ids=(), cooling_btu_classes=())
    brand_counts, series_counts, btu_counts, feature_counts = Counter(), Counter(), Counter(), Counter()
    total = 0
    async for row, effective in _candidates(session, scope, base_filters):
        product = row[0]
        classes = _btu_classes(row.cooling_power_kw, row.area_m2)
        matches_brand = not requested_brands or product.brand_id in requested_brands
        matches_series = not requested_series or product.series_id in requested_series
        matches_btu = not requested_btu or not requested_btu.isdisjoint(classes)
        if not requested_features.issubset(effective):
            continue
        # Brand, series and BTU accept alternatives within their own facet.
        # Feature IDs are cumulative: an added feature narrows the current set.
        if matches_series and matches_btu and row.brand_title and product.brand_id is not None:
            brand_counts[(product.brand_id, row.brand_title)] += 1
        if matches_brand and matches_btu and row.series_title and product.series_id is not None:
            series_counts[(product.series_id, row.series_title, row.series_brand_id)] += 1
        if matches_brand and matches_series:
            btu_counts.update(classes)
            if matches_btu:
                total += 1
                feature_counts.update(effective)

    features = []
    if feature_counts:
        feature_rows = (await session.execute(
            select(Feature.id, Feature.slug, Feature.name, FeatureCategory.name.label("category"))
            .join(FeatureCategory, Feature.category_id == FeatureCategory.id)
            .where(Feature.id.in_(feature_counts), Feature.is_active.is_(True), Feature.archived_at.is_(None))
            .order_by(FeatureCategory.sort_order, Feature.sort_order, Feature.name, Feature.id)
        )).all()
        features = [
            {"id": f.id, "slug": f.slug, "title": f.name, "category": f.category, "count": feature_counts[f.id]}
            for f in feature_rows
        ]
    return BotShopFacetsResponse(
        total=total,
        brands=[{"id": key[0], "title": key[1], "count": count} for key, count in sorted(
            brand_counts.items(), key=lambda item: (item[0][1].casefold(), item[0][0]),
        )],
        series=[{"id": key[0], "title": key[1], "brand_id": key[2], "count": count} for key, count in sorted(
            series_counts.items(), key=lambda item: (item[0][1].casefold(), item[0][0]),
        )],
        cooling_btu_classes=[{"value": value, "count": count} for value, count in sorted(btu_counts.items())],
        features=features,
    )
