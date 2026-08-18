"""Strict storefront-scoped reads for the shared product catalog."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import exists, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from crud.product import ProductDAO
from crud.public_taxonomy import PublicTaxonomyDAO
from models import (
    Brand,
    FeatureSeriesLink,
    Product,
    ProductImage,
    ProductSeries,
    ProductTagLink,
    Tag,
    TagGroup,
    TenantOffer,
    TenantCatalogGrant,
)
from models.supplier import ProductLocalStock
from models.tenancy import TenantScope
from services.public_taxonomy_service import PublicTaxonomyService


PublicCatalogRow = tuple[Product, int, int | None]


class PublicCatalogDAO:
    """Read active offers without falling back to shared Product prices."""

    @staticmethod
    def visible_offer_conditions(tenant_scope: TenantScope):
        return (
            TenantOffer.tenant_id == tenant_scope.tenant_id,
            TenantOffer.storefront_id == tenant_scope.storefront_id,
            TenantOffer.status == "active",
            TenantOffer.is_published.is_(True),
            or_(
                TenantOffer.catalog_grant_id.is_(None),
                exists(
                    select(TenantCatalogGrant.id).where(
                        TenantCatalogGrant.id == TenantOffer.catalog_grant_id,
                        TenantCatalogGrant.tenant_id == tenant_scope.tenant_id,
                        TenantCatalogGrant.storefront_id
                        == tenant_scope.storefront_id,
                        TenantCatalogGrant.status == "active",
                    )
                ),
            ),
        )

    @staticmethod
    def _product_options(*, load_image_variants: bool = False):
        gallery_option = selectinload(Product.gallery_images)
        if load_image_variants:
            gallery_option = gallery_option.selectinload(ProductImage.variants)
        return (
            selectinload(Product.brand),
            selectinload(Product.series)
            .selectinload(ProductSeries.feature_links)
            .selectinload(FeatureSeriesLink.feature),
            selectinload(Product.tags).selectinload(Tag.group),
            gallery_option,
            selectinload(Product.attachments),
        )

    @staticmethod
    def _select_products(
        tenant_scope: TenantScope,
        *,
        load_image_variants: bool = False,
    ):
        return (
            select(Product, TenantOffer.price, TenantOffer.old_price)
            .join(TenantOffer, TenantOffer.product_id == Product.id)
            .where(
                Product.is_published.is_(True),
                *PublicCatalogDAO.visible_offer_conditions(tenant_scope),
            )
            .options(
                *PublicCatalogDAO._product_options(
                    load_image_variants=load_image_variants
                )
            )
        )

    @staticmethod
    def _rows(result) -> list[PublicCatalogRow]:
        return [
            (product, int(price), int(old_price) if old_price is not None else None)
            for product, price, old_price in result.all()
        ]

    @staticmethod
    async def get_filtered(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        is_inverter: Optional[bool] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        has_fresh_air: Optional[bool] = None,
        color: Optional[str] = None,
        indoor_types: Optional[list[str]] = None,
        brand_slugs: Optional[list[str]] = None,
        brand_ids: Optional[list[int]] = None,
        series_ids: Optional[list[int]] = None,
        product_kinds: Optional[list[str]] = None,
        faceted_tag_ids: Optional[dict[int, list[int]]] = None,
        search_query: Optional[str] = None,
        sort: str = "recommended",
        page: int = 1,
        limit: int = 20,
        load_image_variants: bool = False,
    ) -> list[PublicCatalogRow]:
        stmt = PublicCatalogDAO._select_products(
            tenant_scope,
            load_image_variants=load_image_variants,
        )
        stmt = ProductDAO._apply_common_filters(
            session,
            stmt,
            area_min=area_min,
            area_max=area_max,
            min_price=None,
            max_price=None,
            is_inverter=is_inverter,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            color=color,
            indoor_types=indoor_types,
            brand_slugs=None,
            is_published=True,
        )
        stmt = PublicTaxonomyDAO.apply_published_brand_filter(
            stmt,
            brand_slugs,
        )
        if min_price is not None:
            stmt = stmt.where(TenantOffer.price >= min_price)
        if max_price is not None:
            stmt = stmt.where(TenantOffer.price <= max_price)
        if brand_ids:
            stmt = stmt.where(Product.brand_id.in_(brand_ids))
        if series_ids:
            stmt = stmt.where(Product.series_id.in_(series_ids))
        if product_kinds:
            stmt = stmt.where(Product.product_kind.in_(product_kinds))
        stmt = PublicTaxonomyDAO.apply_search_filter(
            session,
            stmt,
            search_query,
        )
        stmt = PublicTaxonomyDAO.apply_faceted_filters(stmt, faceted_tag_ids)

        if sort == "price_asc":
            stmt = stmt.order_by(TenantOffer.price.asc(), Product.id.asc())
        elif sort == "price_desc":
            stmt = stmt.order_by(TenantOffer.price.desc(), Product.id.desc())
        elif sort == "area_asc":
            stmt = stmt.order_by(ProductDAO.area_expr(session).asc(), Product.id.asc())
        elif sort == "area_desc":
            stmt = stmt.order_by(ProductDAO.area_expr(session).desc(), Product.id.desc())
        elif sort == "newest":
            stmt = stmt.order_by(Product.created_at.desc(), Product.id.desc())
        else:
            stmt = stmt.order_by(
                ProductDAO._catalog_recommendation_score_expr(
                    session,
                    area_max=area_max,
                ).desc(),
                ProductDAO._catalog_brand_priority_expr().asc(),
                Product.created_at.desc(),
                Product.id.desc(),
            )

        stmt = stmt.offset((page - 1) * limit).limit(limit)
        return PublicCatalogDAO._rows(await session.execute(stmt))

    @staticmethod
    async def count_filtered(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        is_inverter: Optional[bool] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        has_fresh_air: Optional[bool] = None,
        color: Optional[str] = None,
        indoor_types: Optional[list[str]] = None,
        brand_slugs: Optional[list[str]] = None,
        faceted_tag_ids: Optional[dict[int, list[int]]] = None,
        search_query: Optional[str] = None,
    ) -> int:
        stmt = (
            select(func.count(Product.id))
            .select_from(Product)
            .join(TenantOffer, TenantOffer.product_id == Product.id)
            .where(*PublicCatalogDAO.visible_offer_conditions(tenant_scope))
        )
        stmt = ProductDAO._apply_common_filters(
            session,
            stmt,
            area_min=area_min,
            area_max=area_max,
            min_price=None,
            max_price=None,
            is_inverter=is_inverter,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            color=color,
            indoor_types=indoor_types,
            brand_slugs=None,
            is_published=True,
        )
        stmt = PublicTaxonomyDAO.apply_published_brand_filter(
            stmt,
            brand_slugs,
        )
        if min_price is not None:
            stmt = stmt.where(TenantOffer.price >= min_price)
        if max_price is not None:
            stmt = stmt.where(TenantOffer.price <= max_price)
        stmt = PublicTaxonomyDAO.apply_search_filter(
            session,
            stmt,
            search_query,
        )
        stmt = PublicTaxonomyDAO.apply_faceted_filters(stmt, faceted_tag_ids)
        return int((await session.execute(stmt)).scalar_one() or 0)

    @staticmethod
    async def get_by_identifier(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        identifier: str,
    ) -> PublicCatalogRow | None:
        async def fetch(condition) -> PublicCatalogRow | None:
            result = await session.execute(
                PublicCatalogDAO._select_products(
                    tenant_scope,
                    load_image_variants=True,
                ).where(condition)
            )
            row = result.one_or_none()
            if row is None:
                return None
            product, price, old_price = row
            return (
                product,
                int(price),
                int(old_price) if old_price is not None else None,
            )

        if identifier.isdigit():
            by_id = await fetch(Product.id == int(identifier))
            if by_id is not None:
                return by_id
        return await fetch(Product.slug == identifier)

    @staticmethod
    async def get_by_ids(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        product_ids: list[int],
        load_image_variants: bool = False,
    ) -> list[PublicCatalogRow]:
        if not product_ids:
            return []
        stmt = PublicCatalogDAO._select_products(
            tenant_scope,
            load_image_variants=load_image_variants,
        ).where(Product.id.in_(product_ids))
        return PublicCatalogDAO._rows(await session.execute(stmt))

    @staticmethod
    async def get_series_siblings(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        product: Product,
        load_image_variants: bool = False,
    ) -> list[PublicCatalogRow]:
        """Select sibling candidates inside the storefront offer boundary."""
        stmt = PublicCatalogDAO._select_products(
            tenant_scope,
            load_image_variants=load_image_variants,
        ).where(Product.id != product.id)

        series = PublicTaxonomyService.public_series(product)
        if series is not None and series.id is not None:
            stmt = stmt.where(Product.series_id == series.id)
        else:
            series_tag_ids = [
                int(tag.id)
                for tag in (product.tags or [])
                if tag.id is not None
                and tag.is_public is True
                and tag.group is not None
                and tag.group.is_public is True
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
            stmt = stmt.join(
                series_product_ids,
                Product.id == series_product_ids.c.product_id,
            )

        return PublicCatalogDAO._rows(await session.execute(stmt))

    @staticmethod
    async def get_all(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        load_image_variants: bool = False,
    ) -> list[PublicCatalogRow]:
        stmt = PublicCatalogDAO._select_products(
            tenant_scope,
            load_image_variants=load_image_variants,
        ).order_by(Product.id.asc())
        return PublicCatalogDAO._rows(await session.execute(stmt))

    @staticmethod
    async def get_by_series_id(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        series_id: int,
        load_image_variants: bool = False,
    ) -> list[PublicCatalogRow]:
        stmt = (
            PublicCatalogDAO._select_products(
                tenant_scope,
                load_image_variants=load_image_variants,
            )
            .where(Product.series_id == series_id)
            .order_by(Product.title.asc(), Product.id.asc())
        )
        return PublicCatalogDAO._rows(await session.execute(stmt))

    @staticmethod
    async def get_vitebsk_featured(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        limit: int,
    ) -> list[PublicCatalogRow]:
        stmt = (
            PublicCatalogDAO._select_products(
                tenant_scope,
                load_image_variants=True,
            )
            .join(ProductLocalStock, Product.id == ProductLocalStock.product_id)
            .where(
                ProductLocalStock.warehouse_code == "vitebsk",
                ProductLocalStock.qty > 0,
            )
            .order_by(Product.created_at.desc(), Product.id.desc())
            .limit(limit)
        )
        return PublicCatalogDAO._rows(await session.execute(stmt))

    @staticmethod
    async def get_filter_stats(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> tuple[int | None, int | None, float | None, float | None, list[Brand]]:
        offer_conditions = PublicCatalogDAO.visible_offer_conditions(tenant_scope)
        price_area = (
            await session.execute(
                select(
                    func.min(TenantOffer.price),
                    func.max(TenantOffer.price),
                    func.min(ProductDAO.area_expr(session)),
                    func.max(ProductDAO.area_expr(session)),
                )
                .select_from(Product)
                .join(TenantOffer, TenantOffer.product_id == Product.id)
                .where(Product.is_published.is_(True), *offer_conditions)
            )
        ).one()
        brands = list(
            (
                await session.execute(
                    select(Brand)
                    .join(Product, Product.brand_id == Brand.id)
                    .join(TenantOffer, TenantOffer.product_id == Product.id)
                    .where(
                        Brand.is_published.is_(True),
                        Product.is_published.is_(True),
                        *offer_conditions,
                    )
                    .group_by(Brand.id)
                    .order_by(Brand.sort_order, Brand.title)
                )
            ).scalars().all()
        )
        return (*price_area, brands)

    @staticmethod
    async def get_public_specs(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> list[dict | None]:
        result = await session.execute(
            select(Product.specs)
            .join(TenantOffer, TenantOffer.product_id == Product.id)
            .where(
                Product.is_published.is_(True),
                *PublicCatalogDAO.visible_offer_conditions(tenant_scope),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_brand_counts(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        brand_slug: str | None = None,
    ) -> list[tuple[Brand, int]]:
        stmt = (
            select(Brand, func.count(Product.id).label("products_count"))
            .join(Product, Product.brand_id == Brand.id)
            .join(TenantOffer, TenantOffer.product_id == Product.id)
            .where(
                Brand.is_published.is_(True),
                Product.is_published.is_(True),
                *PublicCatalogDAO.visible_offer_conditions(tenant_scope),
            )
            .group_by(Brand.id)
            .having(func.count(Product.id) > 0)
        )
        if brand_slug is not None:
            stmt = stmt.where(Brand.slug == brand_slug)
        else:
            stmt = stmt.order_by(Brand.sort_order.asc(), Brand.title.asc())
        return [
            (brand, int(products_count))
            for brand, products_count in (await session.execute(stmt)).all()
        ]

    @staticmethod
    async def list_expert_tags(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> list[Tag]:
        result = await session.execute(
            select(Tag)
            .join(TagGroup, Tag.group_id == TagGroup.id)
            .join(ProductTagLink, ProductTagLink.tag_id == Tag.id)
            .join(Product, Product.id == ProductTagLink.product_id)
            .join(TenantOffer, TenantOffer.product_id == Product.id)
            .where(
                Tag.is_public.is_(True),
                TagGroup.is_public.is_(True),
                (TagGroup.slug == "expert-badge")
                | (TagGroup.is_expert_badge.is_(True)),
                Product.is_published.is_(True),
                *PublicCatalogDAO.visible_offer_conditions(tenant_scope),
            )
            .group_by(Tag.id)
            .order_by(Tag.sort_order, Tag.title)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_related_series(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        brand_id: int,
        current_series_id: int,
        limit: int,
    ) -> list[tuple[ProductSeries, int]]:
        stmt = (
            select(
                ProductSeries,
                func.count(Product.id).label("products_count"),
            )
            .join(Product, Product.series_id == ProductSeries.id)
            .join(TenantOffer, TenantOffer.product_id == Product.id)
            .where(
                ProductSeries.brand_id == brand_id,
                ProductSeries.id != current_series_id,
                ProductSeries.is_published.is_(True),
                Product.is_published.is_(True),
                *PublicCatalogDAO.visible_offer_conditions(tenant_scope),
            )
            .group_by(ProductSeries.id)
            .order_by(
                ProductSeries.sort_order.asc(),
                ProductSeries.title.asc(),
                ProductSeries.id.asc(),
            )
            .limit(limit)
        )
        return [
            (series, int(products_count))
            for series, products_count in (await session.execute(stmt)).all()
        ]
