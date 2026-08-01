"""Public-only taxonomy predicates for storefront catalog queries."""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import exists, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Brand, Product, ProductTagLink, Tag, TagGroup
from models.product_constants import BTU_MAPPING


PUBLIC_FILTER_GROUP_SLUGS = {
    "brand",
    "series",
    "expert-badge",
    "type",
    "category",
}


def _normalized_slugs(values: Iterable[str] | None) -> list[str]:
    return list(
        dict.fromkeys(
            str(value).strip().lower()
            for value in (values or [])
            if value and str(value).strip()
        )
    )


class PublicTaxonomyDAO:
    """Build queries that can only observe public tags and tag groups."""

    @staticmethod
    def public_tag_conditions():
        return (
            Tag.is_public.is_(True),
            TagGroup.is_public.is_(True),
        )

    @staticmethod
    async def resolve_filter_ids(
        session: AsyncSession,
        *,
        tag_slugs: Iterable[str] | None,
        brand_slugs: Iterable[str] | None,
    ) -> tuple[dict[int, list[int]] | None, list[str]]:
        requested_tag_slugs = _normalized_slugs(tag_slugs)
        resolved_brand_slugs = _normalized_slugs(brand_slugs)
        if not requested_tag_slugs:
            return None, resolved_brand_slugs

        tag_rows = (
            await session.execute(
                select(Tag.id, Tag.group_id, Tag.slug, TagGroup.slug)
                .join(TagGroup, Tag.group_id == TagGroup.id)
                .where(
                    Tag.slug.in_(requested_tag_slugs),
                    TagGroup.slug.in_(sorted(PUBLIC_FILTER_GROUP_SLUGS)),
                    *PublicTaxonomyDAO.public_tag_conditions(),
                )
            )
        ).all()

        public_brand_tag_slugs = {
            str(tag_slug)
            for _, _, tag_slug, group_slug in tag_rows
            if group_slug == "brand" and tag_slug
        }
        legacy_brand_slugs: set[str] = set()
        if public_brand_tag_slugs:
            legacy_brand_slugs = {
                str(slug)
                for slug in (
                    await session.execute(
                        select(Brand.slug).where(
                            Brand.slug.in_(public_brand_tag_slugs),
                            Brand.is_published.is_(True),
                        )
                    )
                ).scalars().all()
                if slug
            }
            resolved_brand_slugs.extend(sorted(legacy_brand_slugs))

        grouped: dict[int, list[int]] = {}
        for tag_id, group_id, _, group_slug in tag_rows:
            if group_id is None or tag_id is None or group_slug == "brand":
                continue
            grouped.setdefault(int(group_id), []).append(int(tag_id))

        return grouped or None, list(dict.fromkeys(resolved_brand_slugs))

    @staticmethod
    def apply_published_brand_filter(statement, brand_slugs: Iterable[str] | None):
        normalized = _normalized_slugs(brand_slugs)
        if not normalized:
            return statement
        published_brand_ids = select(Brand.id).where(
            Brand.slug.in_(normalized),
            Brand.is_published.is_(True),
        )
        return statement.where(Product.brand_id.in_(published_brand_ids))

    @staticmethod
    def apply_faceted_filters(
        statement,
        faceted_tag_ids: dict[int, list[int]] | None,
    ):
        for tag_ids in (faceted_tag_ids or {}).values():
            normalized_ids = sorted({int(tag_id) for tag_id in tag_ids})
            if not normalized_ids:
                continue
            matching_products = (
                select(ProductTagLink.product_id)
                .join(Tag, ProductTagLink.tag_id == Tag.id)
                .join(TagGroup, Tag.group_id == TagGroup.id)
                .where(
                    Tag.id.in_(normalized_ids),
                    *PublicTaxonomyDAO.public_tag_conditions(),
                )
            )
            statement = statement.where(Product.id.in_(matching_products))
        return statement

    @staticmethod
    def apply_search_filter(
        session: AsyncSession,
        statement,
        query: str | None,
    ):
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return statement

        from crud.product import ProductDAO

        tokens = normalized_query.split()
        text_tokens = [token for token in tokens if not token.isdigit()]
        number_tokens = [token for token in tokens if token.isdigit()]

        for word in text_tokens:
            public_tag_title_match = exists(
                select(ProductTagLink.product_id)
                .join(Tag, ProductTagLink.tag_id == Tag.id)
                .join(TagGroup, Tag.group_id == TagGroup.id)
                .where(
                    ProductTagLink.product_id == Product.id,
                    Tag.title.ilike(f"%{word}%"),
                    *PublicTaxonomyDAO.public_tag_conditions(),
                )
            )
            statement = statement.where(
                or_(
                    Product.title.ilike(f"%{word}%"),
                    public_tag_title_match,
                )
            )

        for number in number_tokens:
            if number in BTU_MAPPING:
                ranges = BTU_MAPPING[number]
                number_filter = or_(
                    ProductDAO.area_expr(session).between(
                        ranges["area"][0],
                        ranges["area"][1],
                    ),
                    Product.power_cooling.between(
                        ranges["power"][0],
                        ranges["power"][1],
                    ),
                    Product.title.ilike(f"%{number}%"),
                )
            else:
                number_filter = Product.title.ilike(f"%{number}%")
            statement = statement.where(number_filter)

        return statement
