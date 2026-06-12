from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional, Sequence

from slugify import slugify
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Brand, Product, ProductSeries, ProductTagLink, Tag, TagGroup
from services.tag_logic import (
    extract_brand_name,
    extract_brand_slug,
    is_invalid_brand_name,
    is_invalid_brand_slug,
)


SERIES_SPEC_KEYS = (
    "series",
    "Серия",
    "серия",
    "Серия модели",
    "серия модели",
    "Серия кондиционера",
    "серия кондиционера",
    "Линейка",
    "линейка",
    "Линейка модели",
    "линейка модели",
    "Модельная серия",
    "модельная серия",
    "Модельный ряд",
    "model_series",
)

SERIES_VALUE_STOP_PATTERN = re.compile(
    r"(?i)(?:"
    r"\b(?:inverter|invertor|инвертор\w*|r32|r410a|wi[\s-]?fi|wifi|технология)\b"
    r"|[-−]\s*\d+\s*°?\s*c\b"
    r")"
)

TITLE_SERIES_STOP_WORDS = {
    "кондиционер",
    "сплит",
    "сплит-система",
    "система",
    "настенный",
    "настенная",
    "инверторный",
    "инверторная",
}


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


def _clean_series_value(value: str) -> str:
    text = _primary_token(value)
    if not text:
        return ""

    marker = SERIES_VALUE_STOP_PATTERN.search(text)
    if marker:
        if marker.start() == 0:
            return re.sub(r"\s+", " ", text).strip(" -–—.,;:")
        text = text[: marker.start()].strip()

    return re.sub(r"\s+", " ", text).strip(" -–—.,;:")


def _looks_like_model_code(value: str) -> bool:
    token = _to_text(value).strip("()[]{}.,;:!?'\"`")
    if not token:
        return True
    if "/" in token or "+" in token or "_" in token:
        return True
    if re.fullmatch(r"\d+(?:[.,]\d+)+", token):
        return False
    if re.fullmatch(r"\d+", token):
        return True
    if any(char.isdigit() for char in token):
        if re.search(r"[A-ZА-Я]{2,}", token) or "-" in token or len(token) > 5:
            return True
        return False
    if token.isupper() and len(token) > 4:
        return True
    return False


def _extract_series_from_title(title: str, brand_name: Optional[str]) -> Optional[str]:
    title_text = re.sub(r"\s+", " ", _to_text(title))
    brand_text = re.sub(r"\s+", " ", _to_text(brand_name))
    if not title_text or not brand_text:
        return None

    if not title_text.casefold().startswith(f"{brand_text.casefold()} "):
        return None

    tail = title_text[len(brand_text) :].strip()
    if not tail:
        return None

    parts: list[str] = []
    for raw_token in tail.split():
        token = raw_token.strip("()[]{}.,;:!?'\"`")
        if not token:
            break
        normalized = token.casefold()
        if normalized in TITLE_SERIES_STOP_WORDS:
            break
        if _looks_like_model_code(token):
            break
        parts.append(token)
        if len(parts) >= 3:
            break

    if not parts:
        return None
    return " ".join(parts)


def _safe_group_slug(tag: Tag, group_slug_by_id: Dict[int, str]) -> Optional[str]:
    group_id = getattr(tag, "group_id", None)
    if group_id is not None and group_id in group_slug_by_id:
        return group_slug_by_id[group_id]

    # Access loaded relationship from instance dict only.
    loaded_group = getattr(tag, "__dict__", {}).get("group")
    if loaded_group is None and not hasattr(tag, "__dict__"):
        # Lightweight objects from tests (e.g. SimpleNamespace) may not use SQLAlchemy state.
        loaded_group = getattr(tag, "group", None)
    return getattr(loaded_group, "slug", None)


def _brand_tag_from_tags(
    tags: Sequence[Tag],
    group_slug_by_id: Dict[int, str],
) -> Optional[Tag]:
    for tag in tags:
        if not tag:
            continue
        if _safe_group_slug(tag, group_slug_by_id) != "brand":
            continue
        if not _to_text(getattr(tag, "title", "")):
            continue
        if is_invalid_brand_name(tag.title) or is_invalid_brand_slug(tag.slug):
            continue
        return tag
    return None


def _brand_title_from_tags(
    tags: Sequence[Tag],
    group_slug_by_id: Dict[int, str],
) -> Optional[str]:
    tag = _brand_tag_from_tags(tags, group_slug_by_id)
    return _to_text(tag.title) if tag else None


def extract_series_name(
    specs: Optional[Dict[str, Any]] = None,
    tags: Optional[Sequence[Tag]] = None,
    *,
    group_slug_by_id: Optional[Dict[int, str]] = None,
    title: str = "",
    brand_name: Optional[str] = None,
) -> Optional[str]:
    specs = specs or {}
    raw = _first_non_empty(specs, SERIES_SPEC_KEYS)
    if raw:
        series = _clean_series_value(raw)
        if series:
            return series

    slug_map = group_slug_by_id or {}
    for tag in tags or []:
        if _safe_group_slug(tag, slug_map) == "series" and _to_text(getattr(tag, "title", "")):
            return _to_text(tag.title)

    title_series = _extract_series_from_title(title, brand_name)
    if title_series:
        return title_series
    return None


async def _load_product_tags(session: AsyncSession, product_id: int) -> list[Tag]:
    stmt = (
        select(Tag)
        .join(ProductTagLink, ProductTagLink.tag_id == Tag.id)
        .where(ProductTagLink.product_id == product_id)
        .options(selectinload(Tag.group))
    )
    return list((await session.execute(stmt)).scalars().all())


async def _build_group_slug_map(session: AsyncSession, tags: Sequence[Tag]) -> Dict[int, str]:
    result: Dict[int, str] = {}
    missing_ids: set[int] = set()
    for tag in tags:
        if tag.group_id is None:
            continue
        loaded_group = getattr(tag, "__dict__", {}).get("group")
        if loaded_group and getattr(loaded_group, "slug", None):
            result[tag.group_id] = loaded_group.slug
        else:
            missing_ids.add(tag.group_id)

    if missing_ids:
        stmt = select(TagGroup.id, TagGroup.slug).where(TagGroup.id.in_(missing_ids))
        rows = (await session.execute(stmt)).all()
        for group_id, slug in rows:
            result[group_id] = slug
    return result


async def _ensure_brand_group(session: AsyncSession) -> TagGroup:
    group = (
        await session.execute(select(TagGroup).where(TagGroup.slug == "brand"))
    ).scalar_one_or_none()
    if group:
        return group

    group = TagGroup(
        slug="brand",
        title="Бренд",
        is_public=True,
        allow_multiple=False,
        sort_order=10,
    )
    session.add(group)
    await session.flush()
    return group


async def _ensure_brand_tag(
    session: AsyncSession,
    *,
    brand: Brand,
    brand_group: TagGroup,
) -> Tag:
    brand_slug = _to_text(brand.slug).lower()
    if not brand_slug:
        brand_slug = slugify(_to_text(brand.title), lowercase=True)

    existing = (await session.execute(select(Tag).where(Tag.slug == brand_slug))).scalar_one_or_none()
    if existing:
        changed = False
        if existing.group_id != brand_group.id:
            existing.group_id = brand_group.id
            changed = True
        if not existing.is_public:
            existing.is_public = True
            changed = True
        if not existing.is_filter:
            existing.is_filter = True
            changed = True
        if not _to_text(existing.title):
            existing.title = _to_text(brand.title) or brand_slug.upper()
            changed = True
        if changed:
            session.add(existing)
            await session.flush()
        return existing

    tag = Tag(
        group_id=brand_group.id,
        title=_to_text(brand.title) or brand_slug.upper(),
        slug=brand_slug,
        is_public=True,
        is_filter=True,
    )
    session.add(tag)
    await session.flush()
    return tag


async def _sync_product_brand_tag_link(
    session: AsyncSession,
    *,
    product_id: int,
    brand_group_id: int,
    brand_tag_id: int,
) -> bool:
    changed = False
    existing_brand_tag_ids = (
        await session.execute(
            select(ProductTagLink.tag_id)
            .join(Tag, ProductTagLink.tag_id == Tag.id)
            .where(ProductTagLink.product_id == product_id)
            .where(Tag.group_id == brand_group_id)
        )
    ).scalars().all()

    to_remove = [tag_id for tag_id in existing_brand_tag_ids if tag_id != brand_tag_id]
    if to_remove:
        await session.execute(
            delete(ProductTagLink)
            .where(ProductTagLink.product_id == product_id)
            .where(ProductTagLink.tag_id.in_(to_remove))
        )
        changed = True

    has_link = (
        await session.execute(
            select(ProductTagLink.product_id)
            .where(ProductTagLink.product_id == product_id)
            .where(ProductTagLink.tag_id == brand_tag_id)
        )
    ).first() is not None
    if not has_link:
        session.add(ProductTagLink(product_id=product_id, tag_id=brand_tag_id))
        changed = True

    return changed


async def _clear_product_brand_tag_links(
    session: AsyncSession,
    *,
    product_id: int,
    brand_group_id: int,
) -> bool:
    brand_tag_ids = (
        await session.execute(select(Tag.id).where(Tag.group_id == brand_group_id))
    ).scalars().all()
    if not brand_tag_ids:
        return False

    existing = (
        await session.execute(
            select(ProductTagLink.tag_id)
            .where(ProductTagLink.product_id == product_id)
            .where(ProductTagLink.tag_id.in_(brand_tag_ids))
        )
    ).scalars().all()
    if not existing:
        return False

    await session.execute(
        delete(ProductTagLink)
        .where(ProductTagLink.product_id == product_id)
        .where(ProductTagLink.tag_id.in_(brand_tag_ids))
    )
    return True


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
    explicit_brand_id: Optional[int] = None,
    explicit_brand_override: bool = False,
) -> bool:
    data_specs = specs if specs is not None else (product.specs or {})
    product_title = title if title is not None else (product.title or "")

    if tags is not None:
        tag_list = list(tags)
    elif product.id:
        tag_list = await _load_product_tags(session, product.id)
    else:
        tag_list = list(getattr(product, "tags", []) or [])

    group_slug_by_id = await _build_group_slug_map(session, tag_list)
    selected_brand_tag = _brand_tag_from_tags(tag_list, group_slug_by_id)

    brand_name: Optional[str] = None
    brand_slug: Optional[str] = None
    changed = False
    skip_auto_brand_detection = False

    if explicit_brand_override:
        if explicit_brand_id is not None:
            explicit_brand = await session.get(Brand, explicit_brand_id)
            if explicit_brand:
                brand_name = _to_text(explicit_brand.title)
                brand_slug = _to_text(explicit_brand.slug)
            else:
                skip_auto_brand_detection = False
        else:
            if product.brand_id is not None:
                product.brand_id = None
                changed = True
            brand_group = await _ensure_brand_group(session)
            if product.id and await _clear_product_brand_tag_links(
                session,
                product_id=product.id,
                brand_group_id=brand_group.id,
            ):
                changed = True
            skip_auto_brand_detection = True

    if not skip_auto_brand_detection and brand_name is None and selected_brand_tag is not None:
        brand_name = _to_text(selected_brand_tag.title)
        brand_slug = selected_brand_tag.slug
    elif not skip_auto_brand_detection and brand_name is None:
        brand_name = extract_brand_name(specs=data_specs, title=product_title)
        if not brand_name:
            brand_name = _brand_title_from_tags(tag_list, group_slug_by_id)
        brand_slug = extract_brand_slug(specs=data_specs, title=product_title)

    if brand_name and is_invalid_brand_name(brand_name):
        brand_name = None
    if brand_slug and is_invalid_brand_slug(brand_slug):
        brand_slug = None

    if brand_name:
        if not brand_slug:
            generated = slugify(brand_name, lowercase=True)
            brand_slug = generated or None
        if brand_slug:
            brand = await ensure_brand(session, title=brand_name, slug=brand_slug)
            if product.brand_id != brand.id:
                product.brand_id = brand.id
                changed = True

            brand_group = await _ensure_brand_group(session)
            brand_tag = await _ensure_brand_tag(session, brand=brand, brand_group=brand_group)
            if product.id and await _sync_product_brand_tag_link(
                session,
                product_id=product.id,
                brand_group_id=brand_group.id,
                brand_tag_id=brand_tag.id,
            ):
                changed = True

    series_name = extract_series_name(
        specs=data_specs,
        tags=tag_list,
        group_slug_by_id=group_slug_by_id,
        title=product_title,
        brand_name=brand_name,
    )
    if series_name:
        series = await ensure_series(session, title=series_name, brand_id=product.brand_id)
        if product.series_id != series.id:
            product.series_id = series.id
            changed = True

    if changed:
        session.add(product)
    return changed
