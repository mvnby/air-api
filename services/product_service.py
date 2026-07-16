"""Compatibility facade for product service operations.

Read/filter methods are inherited from ProductReadService.
Write/mutation methods are inherited from ProductWriteService.
Manager-facing methods are inherited from ProductManagerService.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from crud.product import ProductDAO
from services.catalog_revision_service import CatalogRevisionService
from services.product_manager_service import ProductManagerService
from services.product_read_service import ProductReadService
from services.product_write_service import ProductWriteService

class ProductService(ProductReadService, ProductWriteService, ProductManagerService):
    """Backward-compatible facade that combines product service specializations."""

    @staticmethod
    async def update_price(
        session: AsyncSession,
        product_id: int,
        new_price: int,
    ) -> bool:
        updated = await ProductDAO.update_price(session, product_id, new_price, commit=False)
        if updated:
            await CatalogRevisionService.bump_commit_and_purge(
                session,
                scope="product_price",
                product_ids=[product_id],
            )
        return updated

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

        search_result = await ProductManagerService.smart_search(
            session=session,
            q=normalized_query,
            limit=limit,
        )
        products = search_result.get("items", []) if isinstance(search_result, dict) else list(search_result or [])
        return products
