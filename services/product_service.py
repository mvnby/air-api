"""Compatibility facade for product service operations.

Read/filter methods are inherited from ProductReadService.
Write/mutation methods are inherited from ProductWriteService.
Manager-facing methods are inherited from ProductManagerService.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from services.product_manager_service import ProductManagerService
from services.product_read_service import ProductReadService
from services.product_write_service import ProductWriteService


class ProductService(ProductReadService, ProductWriteService, ProductManagerService):
    """Backward-compatible facade that combines product service specializations."""

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
        return await ProductManagerService.smart_search(
            session=session,
            q=normalized_query,
            limit=limit,
        )
