"""
Repository Layer: Favorite Data Access Object (DAO).
Pure database operations.
"""
from typing import Optional, List
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Favorite, Product, Tag


class FavoriteDAO:
    """Data Access Object for Favorite entity."""

    @staticmethod
    async def toggle(session: AsyncSession, user_id: int, product_id: int) -> bool:
        """Toggle favorite status. Returns True if added, False if removed."""
        stmt = select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.product_id == product_id
        )
        result = await session.execute(stmt)
        item = result.scalar_one_or_none()
        
        if item:
            await session.delete(item)
            await session.commit()
            return False
        else:
            fav = Favorite(user_id=user_id, product_id=product_id)
            session.add(fav)
            await session.commit()
            return True

    @staticmethod
    async def is_favorite(session: AsyncSession, user_id: int, product_id: int) -> bool:
        """Check if product is in user's favorites."""
        stmt = select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.product_id == product_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_user_favorites(session: AsyncSession, user_id: int) -> List[Product]:
        """Get all favorite products for a user."""
        stmt = select(Favorite).where(
            Favorite.user_id == user_id
        ).options(
            selectinload(Favorite.product).selectinload(Product.tags)
        )
        result = await session.execute(stmt)
        favs = result.scalars().all()
        return [f.product for f in favs if f.product]
