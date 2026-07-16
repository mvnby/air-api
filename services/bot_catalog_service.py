"""Staff-authorized catalog reads exposed to the Telegram bot API."""

from sqlalchemy.ext.asyncio import AsyncSession

from services.bot_access_service import BotAccessService
from services.product_service import ProductService


class BotCatalogAccessDeniedError(PermissionError):
    """The Telegram identity cannot use staff catalog scenarios."""


class BotCatalogService:
    @staticmethod
    async def _require_staff(session: AsyncSession, telegram_id: int) -> None:
        context = await BotAccessService.get_context(session, telegram_id)
        if not context.is_staff:
            raise BotCatalogAccessDeniedError("Staff catalog access is required")

    @classmethod
    async def search_for_staff(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        query: str,
        limit: int,
    ) -> list[dict]:
        await cls._require_staff(session, telegram_id)
        return await ProductService.search_products(session, query=query, limit=limit)

    @classmethod
    async def get_product_for_staff(
        cls,
        session: AsyncSession,
        *,
        telegram_id: int,
        product_id: int,
    ) -> dict | None:
        await cls._require_staff(session, telegram_id)
        return await ProductService.get_by_id(session, product_id)
