"""Canonical storefront reads constrained to public catalog taxonomy."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from crud.product import ProductDAO
from crud.public_taxonomy import PublicTaxonomyDAO
from models import Product, Tag


class CanonicalPublicCatalogDAO:
    @staticmethod
    def _select_products(*, load_image_variants: bool):
        return select(Product).options(
            selectinload(Product.brand),
            ProductDAO._series_option(),
            selectinload(Product.tags).selectinload(Tag.group),
            ProductDAO._gallery_images_option(
                load_image_variants=load_image_variants
            ),
            selectinload(Product.attachments),
        )

    @staticmethod
    def _apply_filters(
        session: AsyncSession,
        statement,
        *,
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
    ):
        statement = ProductDAO._apply_common_filters(
            session,
            statement,
            area_min=area_min,
            area_max=area_max,
            min_price=min_price,
            max_price=max_price,
            is_inverter=is_inverter,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            color=color,
            indoor_types=indoor_types,
            tag_slugs=None,
            brand_slugs=None,
            is_published=True,
        )
        statement = PublicTaxonomyDAO.apply_published_brand_filter(
            statement,
            brand_slugs,
        )
        statement = PublicTaxonomyDAO.apply_search_filter(
            session,
            statement,
            search_query,
        )
        return PublicTaxonomyDAO.apply_faceted_filters(
            statement,
            faceted_tag_ids,
        )

    @staticmethod
    async def get_filtered(
        session: AsyncSession,
        *,
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
        sort: str = "recommended",
        page: int = 1,
        limit: int = 20,
        load_image_variants: bool = False,
    ) -> list[Product]:
        statement = CanonicalPublicCatalogDAO._apply_filters(
            session,
            CanonicalPublicCatalogDAO._select_products(
                load_image_variants=load_image_variants
            ),
            area_min=area_min,
            area_max=area_max,
            min_price=min_price,
            max_price=max_price,
            is_inverter=is_inverter,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            color=color,
            indoor_types=indoor_types,
            brand_slugs=brand_slugs,
            faceted_tag_ids=faceted_tag_ids,
            search_query=search_query,
        )
        if sort == "price_asc":
            statement = statement.order_by(Product.price.asc(), Product.id.asc())
        elif sort == "price_desc":
            statement = statement.order_by(Product.price.desc(), Product.id.desc())
        elif sort == "area_asc":
            statement = statement.order_by(
                ProductDAO.area_expr(session).asc(),
                Product.id.asc(),
            )
        elif sort == "area_desc":
            statement = statement.order_by(
                ProductDAO.area_expr(session).desc(),
                Product.id.desc(),
            )
        elif sort == "newest":
            statement = statement.order_by(
                Product.created_at.desc(),
                Product.id.desc(),
            )
        else:
            statement = statement.order_by(
                ProductDAO._catalog_recommendation_score_expr(
                    session,
                    area_max=area_max,
                ).desc(),
                ProductDAO._catalog_brand_priority_expr().asc(),
                Product.created_at.desc(),
                Product.id.desc(),
            )
        statement = statement.offset((page - 1) * limit).limit(limit)
        result = await session.execute(statement)
        return list(result.scalars().all())

    @staticmethod
    async def count_filtered(
        session: AsyncSession,
        **filters,
    ) -> int:
        statement = CanonicalPublicCatalogDAO._apply_filters(
            session,
            select(func.count(Product.id)),
            **filters,
        )
        return int((await session.execute(statement)).scalar_one() or 0)
