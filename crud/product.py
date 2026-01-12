"""
Repository Layer: Product Data Access Object (DAO).
Pure database operations. No business logic.
All methods accept AsyncSession as first argument for DI/transaction control.
"""
from typing import Optional, List
from sqlmodel import select
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
    async def get_all_published(session: AsyncSession) -> List[Product]:
        """Fetch all published products with tags loaded."""
        stmt = select(Product).where(Product.is_published == True).options(
            selectinload(Product.tags).selectinload(Tag.group)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_filtered(
        session: AsyncSession,
        *,
        area_min: Optional[int] = None,
        area_max: Optional[int] = None,
        is_inverter: Optional[bool] = None,
        tag_ids: Optional[List[int]] = None,
        is_published: bool = True,
        order_by_area: bool = False,
        order_by_price: bool = False,
        limit: Optional[int] = None
    ) -> List[Product]:
        """
        Flexible product filtering with support for M2M tag filtering.
        
        Args:
            session: Database session.
            area_min: Minimum area coverage.
            area_max: Maximum area coverage.
            is_inverter: Filter by inverter type (legacy field).
            tag_ids: List of tag IDs - product must have ALL of these tags.
            is_published: Filter by published status.
            order_by_area: Sort by area ascending.
            order_by_price: Sort by price ascending.
            limit: Maximum number of results.
        
        Returns:
            List of Product objects with tags loaded.
        """
        stmt = select(Product).options(
            selectinload(Product.tags).selectinload(Tag.group)
        )
        
        # Apply filters
        if is_published is not None:
            stmt = stmt.where(Product.is_published == is_published)
        
        if area_min is not None:
            stmt = stmt.where(Product.area >= area_min)
        
        if area_max is not None:
            stmt = stmt.where(Product.area <= area_max)
        
        if is_inverter is not None:
            stmt = stmt.where(Product.is_inverter == is_inverter)
        
        # M2M Tag Filtering: Product must have ALL specified tags
        if tag_ids:
            for tag_id in tag_ids:
                subq = select(ProductTagLink.product_id).where(ProductTagLink.tag_id == tag_id)
                stmt = stmt.where(Product.id.in_(subq))
        
        # Ordering
        if order_by_area:
            stmt = stmt.order_by(Product.area.asc())
        if order_by_price:
            stmt = stmt.order_by(Product.price.asc())
        
        # Limit
        if limit:
            stmt = stmt.limit(limit)
        
        result = await session.execute(stmt)
        return list(result.scalars().all())

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
