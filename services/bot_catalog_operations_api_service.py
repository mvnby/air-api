"""Authorized catalog selection and mutation operations for Telegram staff."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from services.bot_api_access import require_bot_manager, require_bot_staff
from services.bot_product_selection_service import BotProductSelectionService
from services.product_service import ProductService


class BotCatalogOperationsApiService:
    @staticmethod
    async def build_selection(
        session: AsyncSession, *, telegram_id: int, query: str
    ) -> dict[str, Any]:
        await require_bot_manager(session, telegram_id)
        return await BotProductSelectionService.build_selection(session, query)

    @staticmethod
    async def get_curated(
        session: AsyncSession,
        *,
        telegram_id: int,
        area: int,
        is_inverter: bool,
        tag_slugs: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        await require_bot_staff(session, telegram_id)
        return await ProductService.get_curated(
            session,
            area=area,
            is_inverter=is_inverter,
            tag_slugs=tag_slugs or None,
            limit=limit,
        )

    @staticmethod
    async def update_price(
        session: AsyncSession,
        *,
        telegram_id: int,
        product_id: int,
        price: int,
    ) -> bool:
        await require_bot_manager(session, telegram_id)
        return await ProductService.update_price(session, product_id, price)

    @staticmethod
    async def delete_product(
        session: AsyncSession, *, telegram_id: int, product_id: int
    ) -> bool:
        await require_bot_manager(session, telegram_id)
        return await ProductService.delete(session, product_id)
