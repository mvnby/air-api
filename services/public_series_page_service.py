"""Public read model for one published brand series page."""

from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from crud.public_catalog import PublicCatalogDAO
from models import Brand, FeatureSeriesLink, Product, ProductSeries
from models.tenancy import TenantScope
from schemas import (
    ProductBrandResponse,
    PublicRelatedSeriesResponse,
    PublicSeriesPageResponse,
)
from services.feature_resolver_service import FeatureResolverService
from services.product_read_service import ProductReadService
from services.product_response_mapper import map_product_to_response
from services.product_series_payloads import build_product_series_response
from services.public_catalog_service import PublicCatalogService
from services.public_catalog_disclosure import (
    CANONICAL_PUBLIC_DISCLOSURE,
    TENANT_NEUTRAL_PUBLIC_DISCLOSURE,
)
from services.public_catalog_visibility_service import PublicCatalogVisibilityService


class PublicSeriesPageService:
    RELATED_LIMIT = 4

    @staticmethod
    async def get_by_slugs(
        session: AsyncSession,
        *,
        brand_slug: str,
        series_slug: str,
        tenant_scope: TenantScope,
    ) -> PublicSeriesPageResponse | None:
        row = (
            await session.execute(
                select(ProductSeries, Brand)
                .join(Brand, Brand.id == ProductSeries.brand_id)
                .where(
                    Brand.slug == brand_slug,
                    Brand.is_published.is_(True),
                    ProductSeries.slug == series_slug,
                    ProductSeries.is_published.is_(True),
                )
                .options(
                    selectinload(ProductSeries.feature_links).selectinload(
                        FeatureSeriesLink.feature
                    )
                )
            )
        ).one_or_none()
        if row is None:
            return None

        series, brand = row
        projections = await PublicCatalogService.get_products_by_series_id(
            session,
            tenant_scope=tenant_scope,
            series_id=int(series.id),
            load_image_variants=True,
        )
        is_canonical = await PublicCatalogVisibilityService.is_canonical_scope(
            session,
            tenant_scope,
        )
        if not projections and not is_canonical:
            return None
        products = [projection.product for projection in projections]
        supply_metrics = await ProductReadService.get_supply_metrics_map(session, products)
        await FeatureResolverService.resolve_for_products(session, products)

        disclosure_policy = (
            CANONICAL_PUBLIC_DISCLOSURE
            if is_canonical
            else TENANT_NEUTRAL_PUBLIC_DISCLOSURE
        )
        series_payload = build_product_series_response(
            series,
            disclosure_policy=disclosure_policy,
        )
        if series_payload is None:
            return None

        return PublicSeriesPageResponse(
            brand=ProductBrandResponse(
                id=int(brand.id),
                title=brand.title,
                slug=brand.slug,
                logo_url=brand.logo_url,
            ),
            series=series_payload,
            products=[
                map_product_to_response(
                    projection,
                    supply_metrics=supply_metrics.get(int(projection.product.id)),
                )
                for projection in projections
            ],
            related_series=await PublicSeriesPageService._get_related_series(
                session,
                brand_id=int(brand.id),
                current_series_id=int(series.id),
                tenant_scope=tenant_scope,
            ),
        )

    @staticmethod
    async def _get_related_series(
        session: AsyncSession,
        *,
        brand_id: int,
        current_series_id: int,
        tenant_scope: TenantScope,
    ) -> list[PublicRelatedSeriesResponse]:
        if not await PublicCatalogVisibilityService.is_canonical_scope(
            session,
            tenant_scope,
        ):
            rows = await PublicCatalogDAO.list_related_series(
                session,
                tenant_scope=tenant_scope,
                brand_id=brand_id,
                current_series_id=current_series_id,
                limit=PublicSeriesPageService.RELATED_LIMIT,
            )
            return [
                PublicRelatedSeriesResponse(
                    title=related.title,
                    slug=related.slug,
                    short_description=related.short_description,
                    hero_image=related.hero_image,
                    products_count=products_count,
                )
                for related, products_count in rows
            ]
        rows = list(
            (
                await session.execute(
                    select(
                        ProductSeries,
                        func.count(Product.id).label("products_count"),
                    )
                    .outerjoin(
                        Product,
                        and_(
                            Product.series_id == ProductSeries.id,
                            Product.is_published.is_(True),
                        ),
                    )
                    .where(
                        ProductSeries.brand_id == brand_id,
                        ProductSeries.id != current_series_id,
                        ProductSeries.is_published.is_(True),
                    )
                    .group_by(ProductSeries.id)
                    .order_by(
                        ProductSeries.sort_order.asc(),
                        ProductSeries.title.asc(),
                        ProductSeries.id.asc(),
                    )
                    .limit(PublicSeriesPageService.RELATED_LIMIT)
                )
            ).all()
        )
        return [
            PublicRelatedSeriesResponse(
                title=related.title,
                slug=related.slug,
                short_description=related.short_description,
                hero_image=related.hero_image,
                products_count=int(products_count or 0),
            )
            for related, products_count in rows
        ]
