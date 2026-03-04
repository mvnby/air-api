"""Compatibility facade for product service operations.

Read/filter methods are inherited from ProductReadService.
Write/mutation methods are inherited from ProductWriteService.
Manager-facing methods are inherited from ProductManagerService.
"""
import logging

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.product import ProductDAO
from models.product import Product
from services.product_manager_service import ProductManagerService
from services.product_read_service import ProductReadService
from services.product_write_service import ProductWriteService

logger = logging.getLogger(__name__)


class ProductService(ProductReadService, ProductWriteService, ProductManagerService):
    """Backward-compatible facade that combines product service specializations."""

    @staticmethod
    async def update_price(
        session: AsyncSession,
        product_id: int,
        new_price: int,
    ) -> bool:
        return await ProductDAO.update_price(session, product_id, new_price)

    @staticmethod
    async def delete(session: AsyncSession, product_id: int) -> bool:
        # Reuse manager-safe deletion: returns False for missing product and
        # raises ValueError when product is linked to existing orders.
        return await ProductManagerService.delete_for_manager(session, product_id)

    @staticmethod
    async def search_products(
        session: AsyncSession,
        query: str,
        limit: int = 10,
    ):
        """Unified smart product search entrypoint for external consumers."""
        normalized_query = (query or "").strip()
        if not normalized_query:
            return []

        published_total = (
            await session.execute(select(func.count(Product.id)).where(Product.is_published.is_(True)))
        ).scalar_one()
        title_like_total = (
            await session.execute(
                select(func.count(Product.id)).where(
                    Product.is_published.is_(True),
                    Product.title.ilike(f"%{normalized_query}%"),
                )
            )
        ).scalar_one()

        search_result = await ProductManagerService.smart_search(
            session=session,
            q=normalized_query,
            limit=limit,
        )
        products = search_result.get("items", []) if isinstance(search_result, dict) else list(search_result or [])
        logger.info(
            "PRODUCT_SEARCH_DEBUG query=%r published_total=%s title_like_total=%s found=%s",
            normalized_query,
            published_total,
            title_like_total,
            len(products),
        )
        return products
