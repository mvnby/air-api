"""Public catalog projection selected by a trusted storefront scope."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api_contracts.public_catalog import PublicProductSearchItemResponse
from crud.product import ProductDAO
from crud.public_catalog import PublicCatalogDAO
from models import Brand
from models.tenancy import TenantScope
from schemas import (
    ProductSeriesNavigationItemResponse,
    ProductSeriesNavigationResponse,
    ProductSiblingResponse,
)
from services.catalog import CatalogService
from services.feature_resolver_service import FeatureResolverService
from services.product_area import area_from_specs
from services.product_filter_service import ProductFilterService
from services.product_read_service import ProductReadService
from services.product_response_mapper import map_product_to_response
from services.product_series_service import ProductSeriesService
from services.product_series_payloads import build_product_series_response
from services.product_serialization import sanitize_specs
from services.public_catalog_visibility_service import (
    PublicCatalogVisibilityService,
    PublicProductProjection,
)
from services.tag_logic import is_invalid_brand_name, is_invalid_brand_slug


@dataclass(frozen=True)
class PublicProductPage:
    product: PublicProductProjection
    siblings: list[PublicProductProjection]


class PublicCatalogService:
    @staticmethod
    async def _resolve_filter_ids(
        session: AsyncSession,
        tag_slugs: Optional[list[str]],
        brand_slugs: Optional[list[str]],
    ) -> tuple[dict[int, list[int]] | None, list[str]]:
        faceted_tag_ids = None
        resolved_brand_slugs = list(brand_slugs or [])
        if tag_slugs:
            brand_rows = (
                await session.execute(select(Brand.slug).where(Brand.slug.in_(tag_slugs)))
            ).scalars().all()
            legacy_brand_slugs = [slug for slug in brand_rows if slug]
            resolved_brand_slugs.extend(legacy_brand_slugs)
            brand_slug_set = set(legacy_brand_slugs)
            facet_slugs = [slug for slug in tag_slugs if slug not in brand_slug_set]
            faceted_tag_ids = await ProductReadService.resolve_slugs_to_grouped_ids(
                session,
                facet_slugs,
            )
        return faceted_tag_ids, list(dict.fromkeys(resolved_brand_slugs))

    @staticmethod
    async def get_catalog_page(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        page: int = 1,
        limit: int = 20,
        sort: str = "recommended",
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        has_fresh_air: Optional[bool] = None,
        color: Optional[str] = None,
        indoor_types: Optional[list[str]] = None,
        tag_slugs: Optional[list[str]] = None,
        brand_slugs: Optional[list[str]] = None,
        is_inverter: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> dict[str, Any]:
        if await PublicCatalogVisibilityService.is_canonical_scope(
            session,
            tenant_scope,
        ):
            payload = await ProductReadService.get_catalog_page(
                session,
                page=page,
                limit=limit,
                sort=sort,
                min_price=min_price,
                max_price=max_price,
                area_min=area_min,
                area_max=area_max,
                heating_min=heating_min,
                has_wifi=has_wifi,
                has_fresh_air=has_fresh_air,
                color=color,
                indoor_types=indoor_types,
                tag_slugs=tag_slugs,
                brand_slugs=brand_slugs,
                is_inverter=is_inverter,
                search=search,
            )
            return {
                "items": [
                    PublicCatalogVisibilityService.project_product(product)
                    for product in payload["items"]
                ],
                "meta": payload["meta"],
            }

        faceted_tag_ids, resolved_brand_slugs = await PublicCatalogService._resolve_filter_ids(
            session,
            tag_slugs,
            brand_slugs,
        )
        query = {
            "tenant_scope": tenant_scope,
            "area_min": area_min,
            "area_max": area_max,
            "min_price": min_price,
            "max_price": max_price,
            "heating_min": heating_min,
            "has_wifi": has_wifi,
            "has_fresh_air": has_fresh_air,
            "color": color,
            "indoor_types": indoor_types,
            "is_inverter": is_inverter,
            "brand_slugs": resolved_brand_slugs,
            "faceted_tag_ids": faceted_tag_ids,
            "search_query": search,
        }
        rows = await PublicCatalogDAO.get_filtered(
            session,
            **query,
            sort=sort,
            page=page,
            limit=limit,
            load_image_variants=True,
        )
        total = await PublicCatalogDAO.count_filtered(session, **query)
        return {
            "items": [
                PublicCatalogVisibilityService.project_row(row) for row in rows
            ],
            "meta": {
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit if limit > 0 else 0,
            },
        }

    @staticmethod
    async def get_product_page(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        identifier: str,
        sibling_limit: int = 8,
    ) -> PublicProductPage | None:
        if await PublicCatalogVisibilityService.is_canonical_scope(
            session,
            tenant_scope,
        ):
            product = await ProductReadService.get_public_product_by_identifier(
                session,
                identifier,
            )
            if product is None:
                return None
            siblings = await ProductSeriesService.get_series_siblings(
                session,
                product,
                limit=sibling_limit,
            )
            return PublicProductPage(
                product=PublicCatalogVisibilityService.project_product(product),
                siblings=[
                    PublicCatalogVisibilityService.project_product(sibling)
                    for sibling in siblings
                ],
            )

        row = await PublicCatalogDAO.get_by_identifier(
            session,
            tenant_scope=tenant_scope,
            identifier=identifier,
        )
        if row is None:
            return None
        projection = PublicCatalogVisibilityService.project_row(row)
        visible_rows = await PublicCatalogDAO.get_series_siblings(
            session,
            tenant_scope=tenant_scope,
            product=projection.product,
        )
        ordered = PublicCatalogService._sort_series_projections(
            projection,
            [
                PublicCatalogVisibilityService.project_row(candidate)
                for candidate in visible_rows
            ],
        )[:sibling_limit]
        return PublicProductPage(product=projection, siblings=ordered)

    @staticmethod
    async def get_vitebsk_featured_products(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        limit: int = 6,
    ) -> list[PublicProductProjection]:
        if await PublicCatalogVisibilityService.is_canonical_scope(
            session,
            tenant_scope,
        ):
            products = await CatalogService.get_vitebsk_featured_products(
                session,
                limit=limit,
            )
            return [
                PublicCatalogVisibilityService.project_product(item)
                for item in products
            ]
        rows = await PublicCatalogDAO.get_vitebsk_featured(
            session,
            tenant_scope=tenant_scope,
            limit=limit,
        )
        return [PublicCatalogVisibilityService.project_row(row) for row in rows]

    @staticmethod
    async def get_products_by_series_id(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        series_id: int,
        load_image_variants: bool = True,
    ) -> list[PublicProductProjection]:
        if await PublicCatalogVisibilityService.is_canonical_scope(
            session,
            tenant_scope,
        ):
            products = await ProductDAO.get_published_by_series_id(
                session,
                series_id,
                load_image_variants=load_image_variants,
            )
            return [
                PublicCatalogVisibilityService.project_product(item)
                for item in products
            ]
        rows = await PublicCatalogDAO.get_by_series_id(
            session,
            tenant_scope=tenant_scope,
            series_id=series_id,
            load_image_variants=load_image_variants,
        )
        return [PublicCatalogVisibilityService.project_row(row) for row in rows]

    @staticmethod
    async def search(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        query: str | None,
        is_inverter: bool | None,
        limit: int = 10,
    ) -> list[PublicProductSearchItemResponse]:
        if await PublicCatalogVisibilityService.is_canonical_scope(
            session,
            tenant_scope,
        ):
            products = await ProductDAO.get_filtered(
                session,
                is_inverter=is_inverter,
                search_query=(query or "").strip() or None,
                is_published=True,
                limit=max(limit, 1),
                page=1,
                sort="recommended",
                load_image_variants=True,
            )
            projections = [
                PublicCatalogVisibilityService.project_product(product)
                for product in products
            ]
        else:
            rows = await PublicCatalogDAO.get_filtered(
                session,
                tenant_scope=tenant_scope,
                is_inverter=is_inverter,
                search_query=(query or "").strip() or None,
                limit=max(limit, 1),
                page=1,
                sort="recommended",
                load_image_variants=True,
            )
            projections = [
                PublicCatalogVisibilityService.project_row(row) for row in rows
            ]

        supply_metrics = await ProductReadService.get_supply_metrics_map(
            session,
            [projection.product for projection in projections],
        )
        return [
            PublicCatalogService._to_public_search_item(
                projection,
                supply_metrics.get(int(projection.product.id or 0), {}),
            )
            for projection in projections[:limit]
        ]

    @staticmethod
    def _to_public_search_item(
        projection: PublicProductProjection,
        supply_metrics: dict[str, Any],
    ) -> PublicProductSearchItemResponse:
        mapped = map_product_to_response(
            projection.product,
            supply_metrics=supply_metrics,
            pricing=projection.pricing,
        )
        return PublicProductSearchItemResponse(
            id=mapped.id,
            title=mapped.title,
            slug=mapped.slug,
            price=mapped.price,
            old_price=mapped.old_price,
            product_kind=mapped.product_kind,
            is_inverter=mapped.is_inverter,
            power_cooling=mapped.power_cooling,
            main_image=mapped.main_image,
            card_image=mapped.card_image,
            full_image=mapped.full_image,
            specs=mapped.specs,
            vitebsk_qty=mapped.vitebsk_qty,
            minsk_qty=mapped.minsk_qty,
            availability_status=mapped.availability_status,
            public_stock_state=mapped.public_stock_state,
            delivery_min_days=mapped.delivery_min_days,
            delivery_max_days=mapped.delivery_max_days,
        )

    @staticmethod
    async def get_filters_config(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        if await PublicCatalogVisibilityService.is_canonical_scope(
            session,
            tenant_scope,
        ):
            return await ProductFilterService.get_filters_config(session)

        price_min, price_max, area_min, area_max, brands = (
            await PublicCatalogDAO.get_filter_stats(
                session,
                tenant_scope=tenant_scope,
            )
        )
        expert_tags = await PublicCatalogDAO.list_expert_tags(
            session,
            tenant_scope=tenant_scope,
        )
        brands = [
            brand
            for brand in brands
            if not is_invalid_brand_name(brand.title)
            and not is_invalid_brand_slug(brand.slug)
        ]
        return {
            "price": {"min": price_min, "max": price_max},
            "area": {"min": area_min, "max": area_max},
            "brands": [
                {
                    "id": brand.id,
                    "title": brand.title,
                    "slug": brand.slug,
                    "logo_url": brand.logo_url,
                    "sort_order": brand.sort_order,
                }
                for brand in brands
            ],
            "expert_tags": [
                {"id": tag.id, "title": tag.title, "slug": tag.slug}
                for tag in expert_tags
            ],
        }

    @staticmethod
    async def get_public_spec_keys(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        if await PublicCatalogVisibilityService.is_canonical_scope(
            session,
            tenant_scope,
        ):
            return await ProductReadService.get_public_spec_keys(session)
        all_specs = await PublicCatalogDAO.get_public_specs(
            session,
            tenant_scope=tenant_scope,
        )
        stats: dict[str, int] = {}
        for spec_dict in all_specs:
            if not spec_dict:
                continue
            for key in spec_dict:
                if str(key).startswith("__"):
                    continue
                stats[key] = stats.get(key, 0) + 1
        return {"keys": sorted(stats), "total_products_using": stats}

    @staticmethod
    def _sort_series_projections(
        reference: PublicProductProjection,
        candidates: list[PublicProductProjection],
    ) -> list[PublicProductProjection]:
        reference_product = reference.product

        def numeric(value) -> float:
            if value is None:
                return float("inf")
            try:
                number = float(value)
            except (TypeError, ValueError):
                return float("inf")
            return number if number > 0 else float("inf")

        def score(item: PublicProductProjection):
            product = item.product
            same_brand = 1
            if reference_product.brand_id and product.brand_id:
                same_brand = 0 if reference_product.brand_id == product.brand_id else 1
            else:
                reference_brand_ids = {
                    tag.id
                    for tag in (reference_product.tags or [])
                    if tag.group and tag.group.slug == "brand"
                }
                product_brand_ids = {
                    tag.id
                    for tag in (product.tags or [])
                    if tag.group and tag.group.slug == "brand"
                }
                same_brand = (
                    0
                    if reference_brand_ids
                    and product_brand_ids.intersection(reference_brand_ids)
                    else 1
                )
            return (
                same_brand,
                numeric(area_from_specs(product.specs)),
                numeric(product.power_cooling),
                numeric(item.price),
                (product.title or "").casefold(),
                product.id or 0,
            )

        return sorted(candidates, key=score)

    @staticmethod
    async def get_series_navigation(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        limit_per_product: int = 8,
    ) -> ProductSeriesNavigationResponse:
        if await PublicCatalogVisibilityService.is_canonical_scope(
            session,
            tenant_scope,
        ):
            return await ProductSeriesService.get_series_navigation(
                session,
                limit_per_product=limit_per_product,
            )

        rows = await PublicCatalogDAO.get_all(
            session,
            tenant_scope=tenant_scope,
        )
        projections = [
            PublicCatalogVisibilityService.project_row(row) for row in rows
        ]
        products = [projection.product for projection in projections]
        await FeatureResolverService.resolve_for_products(session, products)

        product_group_keys: dict[int, list[str]] = {}
        groups: dict[str, list[PublicProductProjection]] = {}
        for projection in projections:
            product = projection.product
            if not product.id:
                continue
            keys = ProductSeriesService._series_group_keys(product)
            product_group_keys[int(product.id)] = keys
            for key in keys:
                groups.setdefault(key, []).append(projection)

        payload: dict[str, ProductSeriesNavigationItemResponse] = {}
        for projection in projections:
            product = projection.product
            if not product.id or not product.slug:
                continue
            group_keys = product_group_keys.get(int(product.id), [])
            if not group_keys:
                continue
            siblings_by_id: dict[int, PublicProductProjection] = {}
            for key in group_keys:
                for candidate in groups.get(key, []):
                    candidate_id = int(candidate.product.id or 0)
                    if candidate_id and candidate_id != product.id:
                        siblings_by_id[candidate_id] = candidate
            siblings = PublicCatalogService._sort_series_projections(
                projection,
                list(siblings_by_id.values()),
            )[:limit_per_product]
            payload[product.slug] = ProductSeriesNavigationItemResponse(
                series=build_product_series_response(
                    product.series if product.series_id else None
                ),
                series_siblings=[
                    ProductSiblingResponse(
                        id=item.product.id,
                        title=item.product.title,
                        slug=item.product.slug,
                        price=item.price,
                        old_price=item.old_price,
                        specs=sanitize_specs(item.product.specs),
                        is_inverter=item.product.is_inverter,
                        main_image=item.product.main_image,
                    )
                    for item in siblings
                ],
            )
        return ProductSeriesNavigationResponse(products=payload)
