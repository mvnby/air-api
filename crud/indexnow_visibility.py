"""Canonical public URL eligibility, read within the mutation transaction."""
from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import quote, unquote, urlsplit

from sqlalchemy import or_, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Brand, Product, ProductSeries
from services.indexnow_service import INDEXNOW_ORIGIN, catalog_indexnow_urls


def product_path(slug: str) -> str:
    return f"/product/{quote(slug, safe='')}/"


def brand_path(slug: str) -> str:
    return f"/brands/{quote(slug, safe='')}/"


def series_path(brand: str, series: str) -> str:
    return f"/brands/{quote(brand, safe='')}/series/{quote(series, safe='')}/"


class IndexNowVisibilityDAO:
    @staticmethod
    async def published_paths(session: AsyncSession, paths: Iterable[str]) -> tuple[str, ...]:
        candidates = catalog_indexnow_urls([INDEXNOW_ORIGIN], list(paths))
        products: set[str] = set()
        brands: set[str] = set()
        series: set[tuple[str, str]] = set()
        public: set[str] = set()
        for url in candidates:
            path = urlsplit(url).path
            parts = [unquote(part) for part in path.strip('/').split('/')]
            if parts in (["catalog"], ["brands"]):
                public.add(path)
            elif parts[0] == 'product':
                products.add(parts[1])
            elif len(parts) == 2:
                brands.add(parts[1])
            else:
                series.add((parts[1], parts[3]))
        if products:
            slugs = (await session.execute(select(Product.slug).where(
                Product.slug.in_(products), Product.is_published.is_(True),
            ))).scalars().all()
            public.update(product_path(slug) for slug in slugs)
        if brands:
            has_products = select(Product.id).where(
                Product.brand_id == Brand.id, Product.is_published.is_(True),
            ).exists()
            slugs = (await session.execute(select(Brand.slug).where(
                Brand.slug.in_(brands), Brand.is_published.is_(True), has_products,
            ))).scalars().all()
            public.update(brand_path(slug) for slug in slugs)
        if series:
            rows = (await session.execute(select(Brand.slug, ProductSeries.slug)
                .join(Brand, Brand.id == ProductSeries.brand_id).where(
                    tuple_(Brand.slug, ProductSeries.slug).in_(series),
                    Brand.is_published.is_(True), ProductSeries.is_published.is_(True),
                ))).all()
            # The canonical series endpoint also serves published empty series.
            public.update(series_path(brand, slug) for brand, slug in rows)
        return tuple(sorted(public))

    @classmethod
    async def capture_paths(
        cls, session: AsyncSession, *, product_ids: Iterable[int] = (),
        brand_ids: Iterable[int] = (), series_ids: Iterable[int] = (),
    ) -> tuple[str, ...]:
        """Snapshot before a destructive mutation; absence never proves publication."""
        product_ids, brand_ids, series_ids = set(product_ids), set(brand_ids), set(series_ids)
        related_brands = set(brand_ids)
        related_series = set(series_ids)
        paths: set[str] = set()
        if product_ids:
            rows = (await session.execute(select(Product.slug, Product.brand_id, Product.series_id)
                .where(Product.id.in_(product_ids)))).all()
            for slug, brand_id, series_id in rows:
                if slug:
                    paths.add(product_path(slug))
                if brand_id is not None:
                    related_brands.add(brand_id)
                if series_id is not None:
                    related_series.add(series_id)
        if related_brands:
            slugs = (await session.execute(select(Brand.slug).where(Brand.id.in_(related_brands)))).scalars().all()
            paths.update(brand_path(slug) for slug in slugs if slug)
        if related_series or brand_ids:
            rows = (await session.execute(select(Brand.slug, ProductSeries.slug)
                .join(Brand, Brand.id == ProductSeries.brand_id).where(or_(
                    ProductSeries.id.in_(related_series), ProductSeries.brand_id.in_(brand_ids),
                )))).all()
            paths.update(series_path(brand, slug) for brand, slug in rows if brand and slug)
        return await cls.published_paths(session, paths)
