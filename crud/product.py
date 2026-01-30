"""
Repository Layer: Product Data Access Object (DAO).
Pure database operations. No business logic.
All methods accept AsyncSession as first argument for DI/transaction control.
"""
from typing import Optional, List
from sqlmodel import select, func, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Product, Tag, ProductTagLink


class ProductDAO:
    """
    Data Access Object for Product entity.
    Methods are static and receive session as argument.
    """

    @staticmethod
    async def get_by_id(session: AsyncSession, product_id: int) -> Optional[Product]:
        """Fetch a single product by ID with tags loaded."""
        stmt = select(Product).where(Product.id == product_id).options(
            selectinload(Product.tags).selectinload(Tag.group)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(session: AsyncSession, slug: str) -> Optional[Product]:
        """Fetch a single product by slug with tags loaded."""
        stmt = select(Product).where(Product.slug == slug).options(
            selectinload(Product.tags).selectinload(Tag.group)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_published(session: AsyncSession) -> List[Product]:
        """Fetch all published products with tags loaded."""
        stmt = select(Product).where(Product.is_published == True).options(
            selectinload(Product.tags).selectinload(Tag.group)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_ids(session: AsyncSession, product_ids: List[int]) -> List[Product]:
        """Fetch multiple products by ID."""
        if not product_ids:
            return []
        stmt = select(Product).where(Product.id.in_(product_ids))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _apply_common_filters(
        stmt,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        is_inverter: Optional[bool] = None,
        tag_slugs: Optional[List[str]] = None,
        is_published: bool = True
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
            
        if tag_slugs:
            for slug in tag_slugs:
                # Join to Tag to filter by slug
                subq = select(ProductTagLink.product_id).join(Tag, ProductTagLink.tag_id == Tag.id).where(Tag.slug == slug)
                stmt = stmt.where(Product.id.in_(subq))
        
        return stmt

    @staticmethod
    def _apply_faceted_filters(
        stmt,
        faceted_tag_ids: Optional[dict[int, list[int]]] = None
    ):
        """
        Apply faceted filtering:
        - Tags within the same group are combined with OR.
        - Groups are combined with AND.
        """
        if faceted_tag_ids:
            for group_id, tag_ids in faceted_tag_ids.items():
                if not tag_ids:
                    continue
                # Subquery for products having ANY of the tags in this group
                subq = (
                    select(ProductTagLink.product_id)
                    .where(ProductTagLink.tag_id.in_(tag_ids))
                )
                stmt = stmt.where(Product.id.in_(subq))
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
        tag_slugs: Optional[List[str]] = None,
        is_published: bool = True,
        sort: str = "newest",
        page: int = 1,
        limit: int = 20,
        faceted_tag_ids: Optional[dict[int, list[int]]] = None
    ) -> List[Product]:
        """
        Flexible product filtering with pagination and sorting.
        """
        stmt = select(Product).options(
            selectinload(Product.tags).selectinload(Tag.group)
        )
        
        stmt = ProductDAO._apply_common_filters(
            stmt, area_min, area_max, min_price, max_price, is_inverter, tag_slugs, is_published
        )
        
        stmt = ProductDAO._apply_faceted_filters(stmt, faceted_tag_ids)
        
        # Sorting
        if sort == "price_asc":
            stmt = stmt.order_by(Product.price.asc())
        elif sort == "price_desc":
             stmt = stmt.order_by(Product.price.desc())
        elif sort == "area_asc":
            stmt = stmt.order_by(Product.area.asc())
        elif sort == "area_desc":
             stmt = stmt.order_by(Product.area.desc())
        else: # newest
            stmt = stmt.order_by(Product.created_at.desc())

        # Pagination
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
        tag_slugs: Optional[List[str]] = None,
        is_published: bool = True,
        faceted_tag_ids: Optional[dict[int, list[int]]] = None
    ) -> int:
        """Count total results for pagination metadata."""
        stmt = select(func.count(Product.id))
        stmt = ProductDAO._apply_common_filters(
            stmt, area_min, area_max, min_price, max_price, is_inverter, tag_slugs, is_published
        )
        stmt = ProductDAO._apply_faceted_filters(stmt, faceted_tag_ids)
        result = await session.execute(stmt)
        return result.scalar_one() or 0

    @staticmethod
    async def update_price(session: AsyncSession, product_id: int, new_price: int) -> bool:
        """Update product price. Returns True if successful."""
        product = await session.get(Product, product_id)
        if product:
            product.price = new_price
            session.add(product)
            await session.commit()
            return True
        return False

    @staticmethod
    async def delete(session: AsyncSession, product_id: int) -> bool:
        """Delete product. Returns True if successful."""
        product = await session.get(Product, product_id)
        if product:
            await session.delete(product)
            await session.commit()
            return True
        return False
    
    @staticmethod
    async def get_for_generation(session: AsyncSession, product_id: int) -> Optional[Product]:
        """
        Загружает товар со ВСЕЙ иерархией: Теги + Их Группы.
        Нужно для понимания контекста (какой тег к чему относится).
        """
        statement = (
            select(Product)
            .where(Product.id == product_id)
            .options(
                # Жадная загрузка: Product -> Tags -> Group
                selectinload(Product.tags).selectinload(Tag.group)
            )
        )
        result = await session.execute(statement)
        return result.scalar_one_or_none()
