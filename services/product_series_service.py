"""Series/siblings product service operations."""

from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Product, ProductSeries, FeatureSeriesLink, ProductTagLink, Tag
from schemas import (
    ProductSeriesNavigationItemResponse,
    ProductSeriesNavigationResponse,
    ProductSeriesResponse,
    ProductSiblingResponse,
)
from services.product_series_payloads import build_product_series_response
from services.product_area import area_from_specs
from services.product_serialization import sanitize_specs
from services.public_taxonomy_service import PublicTaxonomyService


class ProductSeriesService:
    @staticmethod
    def _sort_series_candidates(reference: Product, candidates: List[Product]) -> List[Product]:
        def score(item: Product) -> tuple[int, float, float, float, str, int]:
            same_brand = 1
            if reference.brand_id and item.brand_id:
                same_brand = 0 if reference.brand_id == item.brand_id else 1
            else:
                reference_brand_ids = {
                    tag.id for tag in (reference.tags or [])
                    if PublicTaxonomyService.is_public_tag(tag)
                    and tag.group.slug == "brand"
                }
                item_brand_ids = {
                    tag.id for tag in (item.tags or [])
                    if PublicTaxonomyService.is_public_tag(tag)
                    and tag.group.slug == "brand"
                }
                same_brand = 0 if (reference_brand_ids and item_brand_ids.intersection(reference_brand_ids)) else 1

            def numeric(value) -> float:
                if value is None:
                    return float("inf")
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    return float("inf")
                return number if number > 0 else float("inf")

            return (
                same_brand,
                numeric(area_from_specs(item.specs)),
                numeric(item.power_cooling),
                numeric(item.price),
                (item.title or "").casefold(),
                item.id or 0,
            )

        return sorted(candidates, key=score)

    @staticmethod
    def _sibling_payload(item: Product) -> ProductSiblingResponse:
        return ProductSiblingResponse(
            id=item.id,
            title=item.title,
            slug=item.slug,
            price=item.price,
            old_price=item.old_price,
            specs=sanitize_specs(item.specs),
            is_inverter=item.is_inverter,
            main_image=item.main_image,
        )

    @staticmethod
    def _series_payload(product: Product) -> ProductSeriesResponse | None:
        series = product.series if product.series_id else None
        return build_product_series_response(series)

    @staticmethod
    def _series_group_keys(product: Product) -> List[str]:
        if product.series_id:
            return [f"series:{product.series_id}"]

        keys = [
            f"tag:{tag.id}"
            for tag in (product.tags or [])
            if tag.id
            and PublicTaxonomyService.is_public_tag(tag)
            and tag.group.slug == "series"
        ]

        specs = product.specs if isinstance(product.specs, dict) else {}
        specs_series = specs.get("series")
        if specs_series:
            normalized_series = " ".join(str(specs_series).casefold().split())
            if normalized_series:
                keys.append(f"specs:{normalized_series}")

        return keys

    @staticmethod
    async def get_series_siblings(
        session: AsyncSession,
        product: Product,
        limit: int = 8,
    ) -> List[Product]:
        stmt = select(Product).where(Product.id != product.id).where(Product.is_published == True)

        if product.series_id:
            stmt = stmt.where(Product.series_id == product.series_id)
        else:
            series_tag_ids = [
                tag.id
                for tag in (product.tags or [])
                if PublicTaxonomyService.is_public_tag(tag)
                and tag.group.slug == "series"
            ]
            if not series_tag_ids:
                return []

            series_product_ids = (
                select(ProductTagLink.product_id)
                .where(ProductTagLink.tag_id.in_(series_tag_ids))
                .distinct()
                .subquery()
            )
            stmt = stmt.join(series_product_ids, Product.id == series_product_ids.c.product_id)

        stmt = stmt.options(selectinload(Product.tags).selectinload(Tag.group))
        candidates = list((await session.execute(stmt)).scalars().all())
        return ProductSeriesService._sort_series_candidates(product, candidates)[:limit]

    @staticmethod
    async def get_series_navigation(
        session: AsyncSession,
        limit_per_product: int = 8,
    ) -> ProductSeriesNavigationResponse:
        stmt = (
            select(Product)
            .where(Product.is_published == True)
            .options(
                selectinload(Product.series)
                .selectinload(ProductSeries.feature_links)
                .selectinload(FeatureSeriesLink.feature),
                selectinload(Product.tags).selectinload(Tag.group),
            )
        )
        products = list((await session.execute(stmt)).scalars().all())
        from services.feature_resolver_service import FeatureResolverService

        await FeatureResolverService.resolve_for_products(session, products)

        product_group_keys: Dict[int, List[str]] = {}
        groups: Dict[str, List[Product]] = {}
        for product in products:
            if not product.id:
                continue

            keys = ProductSeriesService._series_group_keys(product)
            product_group_keys[product.id] = keys
            for key in keys:
                groups.setdefault(key, []).append(product)

        products_payload: Dict[str, ProductSeriesNavigationItemResponse] = {}
        for product in products:
            if not product.slug:
                continue

            group_keys = product_group_keys.get(product.id or 0, [])
            if not group_keys:
                continue

            siblings_by_id: Dict[int, Product] = {}
            for key in group_keys:
                for candidate in groups.get(key, []):
                    if candidate.id and candidate.id != product.id:
                        siblings_by_id[candidate.id] = candidate

            siblings = ProductSeriesService._sort_series_candidates(
                product,
                list(siblings_by_id.values()),
            )[:limit_per_product]
            products_payload[product.slug] = ProductSeriesNavigationItemResponse(
                series=ProductSeriesService._series_payload(product),
                series_siblings=[
                    ProductSeriesService._sibling_payload(item)
                    for item in siblings
                ],
            )

        return ProductSeriesNavigationResponse(products=products_payload)
