import asyncio
import sys
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

sys.path.append('.')
from core.config import settings
from models import Product, Tag, TagGroup
from services.spec_normalizer import normalize_specs
from services.tag_logic import (
    CATEGORY_TAG_TITLES,
    detect_category_slug,
    extract_brand_name,
    extract_brand_slug,
)

# --- НАСТРОЙКИ ---
KEEP_UNITS = True  # True = Оставляем "кВт", "мм". False = Чистим до числа.
# Сейчас ставим True, чтобы на сайте было красиво сразу!


async def _ensure_group(
    session: AsyncSession,
    group_cache: Dict[str, TagGroup],
    *,
    slug: str,
    title: str,
    allow_multiple: bool,
    sort_order: int,
) -> TagGroup:
    cached = group_cache.get(slug)
    if cached:
        return cached

    group = (await session.execute(select(TagGroup).where(TagGroup.slug == slug))).scalar_one_or_none()
    if not group:
        group = TagGroup(
            slug=slug,
            title=title,
            is_public=True,
            allow_multiple=allow_multiple,
            sort_order=sort_order,
        )
        session.add(group)
        await session.flush()
    group_cache[slug] = group
    return group


async def _ensure_tag(
    session: AsyncSession,
    tag_cache: Dict[str, Tag],
    *,
    group: TagGroup,
    slug: str,
    title: str,
    sort_order: int = 0,
) -> Tag:
    cached = tag_cache.get(slug)
    if cached:
        return cached

    tag = (await session.execute(select(Tag).where(Tag.slug == slug))).scalar_one_or_none()
    if not tag:
        tag = Tag(
            slug=slug,
            title=title,
            group_id=group.id,
            is_public=True,
            is_filter=True,
            sort_order=sort_order,
        )
        session.add(tag)
        await session.flush()
    else:
        changed = False
        if tag.group_id != group.id:
            tag.group_id = group.id
            changed = True
        if not tag.is_filter:
            tag.is_filter = True
            changed = True
        if not tag.is_public:
            tag.is_public = True
            changed = True
        if title and not tag.title:
            tag.title = title
            changed = True
        if changed:
            session.add(tag)
            await session.flush()

    tag_cache[slug] = tag
    return tag


def _replace_group_tag(product: Product, group_slug: str, desired_tag: Optional[Tag]) -> bool:
    before = {tag.id for tag in (product.tags or []) if tag.id is not None}

    kept_tags = [
        tag
        for tag in (product.tags or [])
        if not (tag.group and tag.group.slug == group_slug)
    ]
    if desired_tag and all(tag.id != desired_tag.id for tag in kept_tags):
        kept_tags.append(desired_tag)
    product.tags = kept_tags

    after = {tag.id for tag in (product.tags or []) if tag.id is not None}
    return before != after


async def run_normalize():
    db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print(f"🧹 Старт нормализации v3 (Keep Units: {KEEP_UNITS})...")
    
    async with async_session() as session:
        group_cache: Dict[str, TagGroup] = {}
        tag_cache: Dict[str, Tag] = {}

        brand_group = await _ensure_group(
            session,
            group_cache,
            slug="brand",
            title="Бренд",
            allow_multiple=False,
            sort_order=10,
        )
        category_group = await _ensure_group(
            session,
            group_cache,
            slug="category",
            title="Категория",
            allow_multiple=False,
            sort_order=20,
        )

        for idx, (slug, title) in enumerate(CATEGORY_TAG_TITLES.items()):
            await _ensure_tag(
                session,
                tag_cache,
                group=category_group,
                slug=slug,
                title=title,
                sort_order=idx * 10,
            )

        result = await session.execute(
            select(Product).options(selectinload(Product.tags).selectinload(Tag.group))
        )
        products = result.scalars().all()
        
        updated_specs = 0
        updated_tag_sets = 0
        
        for p in products:
            old_specs = p.specs.copy() if isinstance(p.specs, dict) else {}
            wifi_tag_slugs = [
                tag.slug
                for tag in (p.tags or [])
                if tag.slug in {"wifi-builtin", "wifi-ready"}
            ]
            auto_tag_slugs: list[str] = []
            
            new_specs = normalize_specs(
                old_specs,
                keep_units=KEEP_UNITS,
                wifi_tag_slugs=wifi_tag_slugs,
                strict_wifi_from_tags=True,
                title=p.title or "",
                auto_tag_slugs=auto_tag_slugs,
            )
            
            row_changed = False
            if new_specs != old_specs:
                p.specs = new_specs
                flag_modified(p, "specs")
                updated_specs += 1
                row_changed = True

            metrics = {
                "is_inverter": p.is_inverter,
                "power_cooling": p.power_cooling,
            }

            brand_slug = auto_tag_slugs[0] if auto_tag_slugs else extract_brand_slug(new_specs, title=p.title or "")
            brand_title = extract_brand_name(new_specs, title=p.title or "")
            desired_brand_tag = None
            if brand_slug and brand_title:
                desired_brand_tag = await _ensure_tag(
                    session,
                    tag_cache,
                    group=brand_group,
                    slug=brand_slug,
                    title=brand_title,
                )

            category_slug = detect_category_slug(metrics=metrics, specs=new_specs, title=p.title or "")
            desired_category_tag = None
            if category_slug:
                desired_category_tag = await _ensure_tag(
                    session,
                    tag_cache,
                    group=category_group,
                    slug=category_slug,
                    title=CATEGORY_TAG_TITLES.get(category_slug, category_slug),
                )

            category_changed = _replace_group_tag(p, "category", desired_category_tag)
            brand_changed = _replace_group_tag(p, "brand", desired_brand_tag)
            if category_changed or brand_changed:
                updated_tag_sets += 1
                row_changed = True

            if row_changed:
                session.add(p)
        
        await session.commit()
        print(f"🏁 Готово! Обновлено specs: {updated_specs}; обновлено наборов тегов: {updated_tag_sets}")

if __name__ == "__main__":
    asyncio.run(run_normalize())
