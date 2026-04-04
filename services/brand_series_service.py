from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional, Sequence

from slugify import slugify
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Brand, Product, ProductSeries, Tag
from services.tag_logic import extract_brand_name, extract_brand_slug


SERIES_SPEC_KEYS = (
    "series",
    "Серия",
    "серия",
    "Линейка",
    "линейка",
    "Модельный ряд",
    "model_series",
)


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_non_empty(specs: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = specs.get(key)
        if value is not None and _to_text(value):
            return _to_text(value)

    lowered = {
        str(key).strip().lower(): value
        for key, value in specs.items()
        if isinstance(key, str)
    }
    for key in keys:
        value = lowered.get(str(key).strip().lower())
        if value is not None and _to_text(value):
            return _to_text(value)
    return None


def _primary_token(value: str) -> str:
    return re.split(r"[,/|;]", _to_text(value), maxsplit=1)[0].strip()


def _brand_title_from_tags(tags: Sequence[Tag]) -> Optional[str]:
    for tag in tags:
        if not tag:
            continue
        group_slug = getattr(getattr(tag, "group", None), "slug", None)
        if group_slug == "brand" and _to_text(getattr(tag, "title", "")):
            return _to_text(tag.title)
    return None


def extract_series_name(specs: Optional[Dict[str, Any]] = None, tags: Optional[Sequence[Tag]] = None) -> Optional[str]:
    specs = specs or {}
    raw = _first_non_empty(specs, SERIES_SPEC_KEYS)
    if raw:
        series = _primary_token(raw)
        if series:
            return series

    for tag in tags or []:
        group_slug = getattr(getattr(tag, "group", None), "slug", None)
        if group_slug == "series" and _to_text(getattr(tag, "title", "")):
            return _to_text(tag.title)
    return None


async def ensure_brand(
    session: AsyncSession,
    *,
    title: str,
    slug: Optional[str] = None,
) -> Brand:
    normalized_title = _to_text(title)
    if not normalized_title:
        raise ValueError("Brand title is required")

    brand_slug = slug or slugify(normalized_title, lowercase=True)
    if not brand_slug:
        brand_slug = slugify(normalized_title.replace(" ", "-"), lowercase=True)

    existing = (await session.execute(select(Brand).where(Brand.slug == brand_slug))).scalar_one_or_none()
    if existing:
        if not existing.title and normalized_title:
            existing.title = normalized_title
            session.add(existing)
            await session.flush()
        return existing

    brand = Brand(title=normalized_title, slug=brand_slug, is_published=True)
    session.add(brand)
    await session.flush()
    return brand


async def ensure_series(
    session: AsyncSession,
    *,
    title: str,
    brand_id: Optional[int],
) -> ProductSeries:
    normalized_title = _to_text(title)
    if not normalized_title:
        raise ValueError("Series title is required")

    series_slug = slugify(normalized_title, lowercase=True)
    if not series_slug:
        series_slug = slugify(normalized_title.replace(" ", "-"), lowercase=True)

    if brand_id is not None:
        existing = (
            await session.execute(
                select(ProductSeries).where(
                    ProductSeries.brand_id == brand_id,
                    ProductSeries.slug == series_slug,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        orphan = (
            await session.execute(
                select(ProductSeries).where(
                    ProductSeries.brand_id.is_(None),
                    ProductSeries.slug == series_slug,
                )
            )
        ).scalar_one_or_none()
        if orphan:
            orphan.brand_id = brand_id
            session.add(orphan)
            await session.flush()
            return orphan
    else:
        existing = (
            await session.execute(
                select(ProductSeries).where(
                    ProductSeries.brand_id.is_(None),
                    ProductSeries.slug == series_slug,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing

    series = ProductSeries(
        title=normalized_title,
        slug=series_slug,
        brand_id=brand_id,
        is_published=True,
    )
    session.add(series)
    await session.flush()
    return series


async def sync_product_brand_series(
    session: AsyncSession,
    *,
    product: Product,
    specs: Optional[Dict[str, Any]] = None,
    title: Optional[str] = None,
    tags: Optional[Sequence[Tag]] = None,
) -> bool:
    data_specs = specs if specs is not None else (product.specs or {})
    product_title = title if title is not None else (product.title or "")
    tag_list = list(tags or (product.tags or []))

    brand_name = extract_brand_name(specs=data_specs, title=product_title)
    if not brand_name:
        brand_name = _brand_title_from_tags(tag_list)

    changed = False
    if brand_name:
        brand_slug = extract_brand_slug(specs=data_specs, title=product_title)
        brand = await ensure_brand(session, title=brand_name, slug=brand_slug)
        if product.brand_id != brand.id:
            product.brand_id = brand.id
            changed = True

    series_name = extract_series_name(specs=data_specs, tags=tag_list)
    if series_name:
        series = await ensure_series(session, title=series_name, brand_id=product.brand_id)
        if product.series_id != series.id:
            product.series_id = series.id
            changed = True

    if changed:
        session.add(product)
    return changed
