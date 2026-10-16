"""Staff-authorized catalog reads exposed to the Telegram bot API."""

from sqlalchemy.ext.asyncio import AsyncSession

from services.bot_access_service import BotAccessService
from services.product_service import ProductService


class BotCatalogAccessDeniedError(PermissionError):
    """The Telegram identity cannot use staff catalog scenarios."""


class BotCatalogService:
    @staticmethod
    async def _require_staff(session: AsyncSession, telegram_id: int):
        context = await BotAccessService.get_context(session, telegram_id)
        if not context.is_staff:
            raise BotCatalogAccessDeniedError("Staff catalog access is required")
        return context

    @classmethod
    async def search_for_staff(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        query: str,
        limit: int,
    ) -> list[dict]:
        context = await cls._require_staff(session, telegram_id)
        if context.selection is not None and not context.selection.is_system:
            from services.bot_tenant_catalog_service import BotTenantCatalogService
            return await BotTenantCatalogService.products(session, context.selection.scope, query=query, limit=limit)
        return await ProductService.search_products(session, query=query, limit=limit)

    @classmethod
    async def get_product_for_staff(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        product_id: int,
    ) -> dict | None:
        context = await cls._require_staff(session, telegram_id)
        if context.selection is not None and not context.selection.is_system:
            from services.bot_tenant_catalog_service import BotTenantCatalogService
            rows = await BotTenantCatalogService.products(session, context.selection.scope, product_id=product_id, limit=1)
            return next(iter(rows), None)
        return await ProductService.get_by_id(session, product_id)
