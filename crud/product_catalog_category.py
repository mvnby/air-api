"""Persistence helpers for canonical product catalog-category tags."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.product import Tag, TagGroup
from services.tag_logic import CATEGORY_TAG_TITLES


async def get_category_group_tag_ids(
    session: AsyncSession,
    tag_ids: set[int],
) -> set[int]:
    if not tag_ids:
        return set()
    return set(
        (
            await session.execute(
                select(Tag.id)
                .join(TagGroup, Tag.group_id == TagGroup.id)
                .where(TagGroup.slug == "category")
                .where(Tag.id.in_(tag_ids))
            )
        ).scalars()
    )


async def ensure_catalog_category_tag(session: AsyncSession, slug: str) -> tuple[Tag, bool]:
    """Return the canonical category tag and whether its catalog metadata changed."""
    changed = False
    group = (
        await session.execute(select(TagGroup).where(TagGroup.slug == "category"))
    ).scalar_one_or_none()
    if group is None:
        group = TagGroup(
            slug="category",
            title="Категория",
            is_public=True,
            allow_multiple=False,
            sort_order=20,
        )
        session.add(group)
        await session.flush()
        changed = True

    tag = (await session.execute(select(Tag).where(Tag.slug == slug))).scalar_one_or_none()
    if tag is None:
        tag = Tag(
            slug=slug,
            title=CATEGORY_TAG_TITLES[slug],
            group_id=group.id,
            group=group,
            is_public=True,
            is_filter=True,
            sort_order=list(CATEGORY_TAG_TITLES).index(slug) * 10,
        )
        session.add(tag)
        await session.flush()
        changed = True
    else:
        if tag.group_id != group.id:
            tag.group_id = group.id
            changed = True
        if not tag.is_filter:
            tag.is_filter = True
            changed = True
        if not tag.is_public:
            tag.is_public = True
            changed = True
        # Consumers immediately serialize the new association. Set it here
        # rather than depending on a lazy relationship in an async session.
        tag.group = group
        if changed:
            session.add(tag)
            await session.flush()
    return tag, changed
