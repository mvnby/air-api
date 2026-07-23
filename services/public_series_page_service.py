"""Public read model for one published brand series page."""

from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from crud.product import ProductDAO
from models import Brand, FeatureSeriesLink, Product, ProductSeries
from schemas import (
    ProductBrandResponse,
    PublicRelatedSeriesResponse,
    PublicSeriesPageResponse,
)
from services.feature_resolver_service import FeatureResolverService
from services.product_read_service import ProductReadService
from services.product_response_mapper import map_product_to_response
from services.product_series_payloads import build_product_series_response


class PublicSeriesPageService:
    RELATED_LIMIT = 4

    @staticmethod
    async def get_by_slugs(
        session: AsyncSession,
        *,
        brand_slug: str,
        series_slug: str,
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
        products = await ProductDAO.get_published_by_series_id(
            session,
            int(series.id),
            load_image_variants=True,
        )
        supply_metrics = await ProductReadService.get_supply_metrics_map(session, products)
        await FeatureResolverService.resolve_for_products(session, products)

        series_payload = build_product_series_response(series)
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
                    product,
                    supply_metrics=supply_metrics.get(int(product.id)),
                )
                for product in products
            ],
            related_series=await PublicSeriesPageService._get_related_series(
                session,
                brand_id=int(brand.id),
                current_series_id=int(series.id),
            ),
        )

    @staticmethod
    async def _get_related_series(
        session: AsyncSession,
        *,
        brand_id: int,
        current_series_id: int,
    ) -> list[PublicRelatedSeriesResponse]:
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
