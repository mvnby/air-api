"""
Service Layer: Favorite Business Logic.
"""
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from crud.favorite import FavoriteDAO
from models import Product
from services.product_dict_mapper import map_product_to_dict


class FavoriteService:
    """Favorite business logic service."""

    @staticmethod
    async def toggle(session: AsyncSession, user_id: int, product_id: int) -> bool:
        """Toggle favorite. Returns True if added, False if removed."""
        return await FavoriteDAO.toggle(session, user_id, product_id)

    @staticmethod
    async def is_favorite(session: AsyncSession, user_id: int, product_id: int) -> bool:
        """Check if product is favorite."""
        return await FavoriteDAO.is_favorite(session, user_id, product_id)

    @staticmethod
    async def get_favorites(session: AsyncSession, user_id: int) -> List[Dict[str, Any]]:
        """Get user's favorite products formatted for bot."""
        products = await FavoriteDAO.get_user_favorites(session, user_id)
        return [FavoriteService._to_dict(p) for p in products]

    @staticmethod
    def _to_dict(product: Product) -> Dict[str, Any]:
        """Convert Product to dict with bot-compatible format."""
        return map_product_to_dict(product)
