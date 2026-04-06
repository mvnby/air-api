"""
Repository Layer: Product Data Access Object (DAO).
Pure database operations. No business logic.
All methods accept AsyncSession as first argument for DI/transaction control.
"""
from typing import Optional, List, Dict, Any

from sqlalchemy import Integer, Boolean, cast, func, and_, or_, exists
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Product, Tag, TagGroup, ProductTagLink
from models.product_constants import BTU_MAPPING


ALLOWED_FILTER_GROUP_SLUGS = {"brand", "series", "expert-badge", "type", "category"}


class ProductDAO:
    @staticmethod
    async def get_by_id(session: AsyncSession, product_id: int) -> Optional[Product]:
        stmt = select(Product).where(Product.id == product_id).options(
            selectinload(Product.tags).selectinload(Tag.group),
            selectinload(Product.gallery_images),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(session: AsyncSession, slug: str) -> Optional[Product]:
        stmt = select(Product).where(Product.slug == slug).options(
            selectinload(Product.tags).selectinload(Tag.group),
            selectinload(Product.gallery_images),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_published(session: AsyncSession) -> List[Product]:
        stmt = select(Product).where(Product.is_published == True).options(
            selectinload(Product.tags).selectinload(Tag.group),
            selectinload(Product.gallery_images),
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_ids(session: AsyncSession, product_ids: List[int]) -> List[Product]:
        if not product_ids:
            return []
        stmt = select(Product).where(Product.id.in_(product_ids)).options(
            selectinload(Product.gallery_images)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _json_int_expr(session: AsyncSession, key: str):
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "sqlite":
            return cast(func.json_extract(Product.specs, f"$.{key}"), Integer)
        return cast(func.jsonb_extract_path_text(cast(Product.specs, JSONB), key), Integer)

    @staticmethod
    def _json_bool_expr(session: AsyncSession, key: str):
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "sqlite":
            return cast(func.json_extract(Product.specs, f"$.{key}"), Integer)
        return cast(func.jsonb_extract_path_text(cast(Product.specs, JSONB), key), Boolean)

    @staticmethod
    def _apply_common_filters(
        session: AsyncSession,
        stmt,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        is_inverter: Optional[bool] = None,
        heating_min: Optional[int] = None,
        has_wifi: Optional[bool] = None,
        has_fresh_air: Optional[bool] = None,
        tag_slugs: Optional[List[str]] = None,
        is_published: Optional[bool] = True,
    ):
        if is_published is not None:
            stmt = stmt.where(Product.is_published == is_published)

        if area_min is not None:
            stmt = stmt.where(Product.area >= area_min)
        if area_max is not None:
            stmt = stmt.where(Product.area <= area_max)

        if min_price is not None:
            stmt = stmt.where(Product.price >= min_price)
        if max_price is not None:
            stmt = stmt.where(Product.price <= max_price)

        if is_inverter is not None:
            stmt = stmt.where(Product.is_inverter == is_inverter)

        if heating_min is not None:
            stmt = stmt.where(ProductDAO._json_int_expr(session, "__filter_min_heat") <= heating_min)

        if has_wifi is not None:
            wifi_expr = ProductDAO._json_bool_expr(session, "__filter_wifi")
            legacy_wifi_tag_subq = (
                select(ProductTagLink.product_id)
                .join(Tag, ProductTagLink.tag_id == Tag.id)
                .where(Tag.slug == "wifi-builtin")
            )
            if session.bind is not None and session.bind.dialect.name == "sqlite":
                if has_wifi:
                    stmt = stmt.where(
                        or_(
                            wifi_expr == 1,
                            Product.id.in_(legacy_wifi_tag_subq),
                        )
                    )
                else:
                    stmt = stmt.where(
                        and_(
                            wifi_expr == 0,
                            ~Product.id.in_(legacy_wifi_tag_subq),
                        )
                    )
            else:
                if has_wifi:
                    stmt = stmt.where(
                        or_(
                            wifi_expr == True,
                            Product.id.in_(legacy_wifi_tag_subq),
                        )
                    )
                else:
                    stmt = stmt.where(
                        and_(
                            wifi_expr == False,
                            ~Product.id.in_(legacy_wifi_tag_subq),
                        )
                    )

        if has_fresh_air is not None:
            fresh_air_expr = ProductDAO._json_bool_expr(session, "fresh_air")
            if has_fresh_air:
                if session.bind is not None and session.bind.dialect.name == "sqlite":
                    stmt = stmt.where(fresh_air_expr == 1)
                else:
                    stmt = stmt.where(fresh_air_expr == True)
            else:
                if session.bind is not None and session.bind.dialect.name == "sqlite":
                    stmt = stmt.where(or_(fresh_air_expr == 0, fresh_air_expr.is_(None)))
                else:
                    stmt = stmt.where(or_(fresh_air_expr == False, fresh_air_expr.is_(None)))

        if tag_slugs:
            normalized_slugs = [slug.strip().lower() for slug in tag_slugs if slug and slug.strip()]
            # AND between groups, OR within each group.
            for group_slug in sorted(ALLOWED_FILTER_GROUP_SLUGS):
                group_subq = (
                    select(ProductTagLink.product_id)
                    .join(Tag, ProductTagLink.tag_id == Tag.id)
                    .join(TagGroup, Tag.group_id == TagGroup.id)
                    .where(Tag.slug.in_(normalized_slugs))
                    .where(TagGroup.slug == group_slug)
                )
                group_slug_exists = (
                    select(Tag.id)
                    .join(TagGroup, Tag.group_id == TagGroup.id)
                    .where(Tag.slug.in_(normalized_slugs))
                    .where(TagGroup.slug == group_slug)
                )
                # Backcompat: unknown/legacy slugs should be ignored (not zero-result).
                stmt = stmt.where(or_(~exists(group_slug_exists), Product.id.in_(group_subq)))

        return stmt

    @staticmethod
    def _apply_faceted_filters(stmt, faceted_tag_ids: Optional[dict[int, list[int]]] = None):
        if faceted_tag_ids:
            for _, tag_ids in faceted_tag_ids.items():
                if not tag_ids:
                    continue
                subq = select(ProductTagLink.product_id).where(ProductTagLink.tag_id.in_(tag_ids))
                stmt = stmt.where(Product.id.in_(subq))
        return stmt

    @staticmethod
    def _apply_smart_search_filter(stmt, query: str):
        if not query:
            return stmt

        tokens = query.strip().split()
        text_tokens = [t for t in tokens if not t.isdigit()]
        number_tokens = [t for t in tokens if t.isdigit()]

        for word in text_tokens:
            word_filter = or_(
                Product.title.ilike(f"%{word}%"),
                Product.tags.any(Tag.title.ilike(f"%{word}%")),
            )
            stmt = stmt.where(word_filter)

        for num in number_tokens:
            if num in BTU_MAPPING:
                ranges = BTU_MAPPING[num]
                num_filter = or_(
                    Product.area.between(ranges["area"][0], ranges["area"][1]),
                    Product.power_cooling.between(ranges["power"][0], ranges["power"][1]),
                    Product.title.ilike(f"%{num}%"),
                )
            else:
                # Non-standard number (e.g. "2024") → plain text search
                num_filter = Product.title.ilike(f"%{num}%")
            stmt = stmt.where(num_filter)
        
        return stmt

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
        tag_slugs: Optional[List[str]] = None,
        is_published: Optional[bool] = True,
        sort: str = "newest",
        page: int = 1,
        limit: int = 20,
        faceted_tag_ids: Optional[dict[int, list[int]]] = None,
        search_query: Optional[str] = None,
    ) -> List[Product]:
        stmt = select(Product).options(
            selectinload(Product.tags).selectinload(Tag.group),
            selectinload(Product.gallery_images),
        )

        stmt = ProductDAO._apply_common_filters(
            session,
            stmt,
            area_min=area_min,
            area_max=area_max,
            min_price=min_price,
            max_price=max_price,
            is_inverter=is_inverter,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            tag_slugs=tag_slugs,
            is_published=is_published,
        )
        if search_query:
            stmt = ProductDAO._apply_smart_search_filter(stmt, search_query)
        stmt = ProductDAO._apply_faceted_filters(stmt, faceted_tag_ids)

        if sort == "price_asc":
            stmt = stmt.order_by(Product.price.asc())
        elif sort == "price_desc":
            stmt = stmt.order_by(Product.price.desc())
        elif sort == "area_asc":
            stmt = stmt.order_by(Product.area.asc())
        elif sort == "area_desc":
            stmt = stmt.order_by(Product.area.desc())
        else:
            stmt = stmt.order_by(Product.created_at.desc())

        offset = (page - 1) * limit
        stmt = stmt.offset(offset).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_filtered(
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
        tag_slugs: Optional[List[str]] = None,
        is_published: Optional[bool] = True,
        faceted_tag_ids: Optional[dict[int, list[int]]] = None,
        search_query: Optional[str] = None,
    ) -> int:
        stmt = select(func.count(Product.id))
        stmt = ProductDAO._apply_common_filters(
            session,
            stmt,
            area_min=area_min,
            area_max=area_max,
            min_price=min_price,
            max_price=max_price,
            is_inverter=is_inverter,
            heating_min=heating_min,
            has_wifi=has_wifi,
            has_fresh_air=has_fresh_air,
            tag_slugs=tag_slugs,
            is_published=is_published,
        )
        stmt = ProductDAO._apply_faceted_filters(stmt, faceted_tag_ids)
        result = await session.execute(stmt)
        return result.scalar_one() or 0

    @staticmethod
    async def update_price(session: AsyncSession, product_id: int, new_price: int) -> bool:
        product = await session.get(Product, product_id)
        if not product:
            return False
        product.price = new_price
        session.add(product)
        await session.commit()
        return True

    @staticmethod
    async def delete(session: AsyncSession, product_id: int) -> bool:
        product = await session.get(Product, product_id)
        if not product:
            return False
        await session.delete(product)
        await session.commit()
        return True

    @staticmethod
    async def update_full(
        session: AsyncSession,
        product_id: int,
        update_data: Dict[str, Any],
        tag_ids: Optional[List[int]] = None,
    ) -> Optional[Product]:
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.tags).selectinload(Tag.group))
        )
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()
        if not product:
            return None

        for key, value in update_data.items():
            setattr(product, key, value)

        if tag_ids is not None:
            tag_stmt = select(Tag).where(Tag.id.in_(tag_ids)).options(selectinload(Tag.group))
            tag_result = await session.execute(tag_stmt)
            product.tags = list(tag_result.scalars().all())

        session.add(product)
        await session.commit()
        await session.refresh(product)
        return product

    @staticmethod
    async def get_for_manager(
        session: AsyncSession,
        page: int = 1,
        limit: int = 40,
        search: Optional[str] = None,
        is_published: Optional[bool] = None,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        is_inverter: Optional[bool] = None,
        sort: str = "newest",
    ) -> tuple[List[Product], int]:
        stmt = select(Product).options(
            selectinload(Product.gallery_images),
            selectinload(Product.tags).selectinload(Tag.group),
        )
        count_stmt = select(func.count(Product.id))

        if is_published is not None:
            stmt = stmt.where(Product.is_published == is_published)
            count_stmt = count_stmt.where(Product.is_published == is_published)

        if area_min is not None:
            stmt = stmt.where(Product.area >= area_min)
            count_stmt = count_stmt.where(Product.area >= area_min)

        if area_max is not None:
            stmt = stmt.where(Product.area <= area_max)
            count_stmt = count_stmt.where(Product.area <= area_max)

        if is_inverter is not None:
            stmt = stmt.where(Product.is_inverter == is_inverter)
            count_stmt = count_stmt.where(Product.is_inverter == is_inverter)

        if search:
            stmt = stmt.where(Product.title.ilike(f"%{search}%"))
            count_stmt = count_stmt.where(Product.title.ilike(f"%{search}%"))

        if sort == "price_asc":
            stmt = stmt.order_by(Product.price.asc())
        elif sort == "price_desc":
            stmt = stmt.order_by(Product.price.desc())
        elif sort == "title":
            stmt = stmt.order_by(Product.title.asc())
        else:
            stmt = stmt.order_by(Product.id.desc())

        offset = (page - 1) * limit
        stmt = stmt.offset(offset).limit(limit)

        total = (await session.execute(count_stmt)).scalar() or 0
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_for_generation(session: AsyncSession, product_id: int) -> Optional[Product]:
        statement = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.tags).selectinload(Tag.group))
        )
        result = await session.execute(statement)
        return result.scalar_one_or_none()
