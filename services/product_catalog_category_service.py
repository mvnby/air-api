"""Canonical catalog-category selection and tag synchronization."""

from typing import Any, Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from crud.product_catalog_category import (
    ensure_catalog_category_tag,
    get_category_group_tag_ids,
)
from models.product import Product, Tag
from services.tag_logic import CATEGORY_TAG_TITLES, detect_category_slug


CATALOG_CATEGORY_SLUGS = frozenset(CATEGORY_TAG_TITLES)


def catalog_category_from_tags(tags: Iterable[Tag]) -> Optional[str]:
    """Return the single canonical category currently exposed by product tags."""
    slugs = {
        tag.slug
        for tag in tags
        if tag.slug in CATALOG_CATEGORY_SLUGS
    }
    return next(iter(slugs)) if len(slugs) == 1 else None


def resolve_catalog_category(
    product: Product,
    *,
    specs: Optional[dict[str, Any]] = None,
    title: Optional[str] = None,
    metrics: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Prefer the durable manager choice; otherwise apply canonical inference."""
    if product.catalog_category_override in CATALOG_CATEGORY_SLUGS:
        return product.catalog_category_override
    return detect_category_slug(
        metrics=metrics,
        specs=specs if specs is not None else product.specs,
        title=title if title is not None else product.title or "",
    )


async def sync_product_catalog_category(
    session: AsyncSession,
    *,
    product: Product,
    specs: Optional[dict[str, Any]] = None,
    title: Optional[str] = None,
    metrics: Optional[dict[str, Any]] = None,
) -> bool:
    """Keep exactly one category tag while preserving every other tag group."""
    slug = resolve_catalog_category(
        product,
        specs=specs,
        title=title,
        metrics=metrics,
    )
    desired_tag = await ensure_catalog_category_tag(session, slug) if slug else None
    previous_ids = {tag.id for tag in product.tags if tag.id is not None}
    category_tag_ids = await get_category_group_tag_ids(session, previous_ids)
    kept = [
        tag
        for tag in product.tags
        if tag.id not in category_tag_ids and tag.slug not in CATALOG_CATEGORY_SLUGS
    ]
    if desired_tag is not None:
        kept.append(desired_tag)
    product.tags = kept
    current_ids = {tag.id for tag in product.tags if tag.id is not None}
    return previous_ids != current_ids
