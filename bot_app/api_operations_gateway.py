"""Typed catalog and repair operations mixed into the bot HTTP gateway."""

from api_contracts.bot import (
    BotCuratedProductsResponse,
    BotProductMutationResponse,
    BotProductSelectionResponse,
    BotRepairApplyResponse,
    BotRepairDraftResponse,
)


class BotApiOperationsMixin:
    async def build_product_selection(
        self, *, telegram_id: int, query: str
    ) -> BotProductSelectionResponse:
        payload = await self._post(
            "catalog/selection", json={"telegram_id": telegram_id, "query": query}
        )
        return self._validate_contract(BotProductSelectionResponse, payload, "product selection")

    async def get_curated_products(
        self,
        *,
        telegram_id: int,
        area: int,
        is_inverter: bool,
        tag_slugs: list[str],
        limit: int = 5,
    ) -> BotCuratedProductsResponse:
        payload = await self._post(
            "catalog/curated",
            json={
                "telegram_id": telegram_id,
                "area": area,
                "is_inverter": is_inverter,
                "tag_slugs": tag_slugs,
                "limit": limit,
            },
        )
        return self._validate_contract(BotCuratedProductsResponse, payload, "curated products")

    async def update_product_price(
        self, *, telegram_id: int, product_id: int, price: int
    ) -> BotProductMutationResponse:
        payload = await self._post(
            f"catalog/products/{product_id}/price",
            json={"telegram_id": telegram_id, "price": price},
        )
        return self._validate_contract(BotProductMutationResponse, payload, "product update")

    async def delete_product(
        self, *, telegram_id: int, product_id: int
    ) -> BotProductMutationResponse:
        payload = await self._post(
            f"catalog/products/{product_id}/delete",
            json={"telegram_id": telegram_id},
        )
        return self._validate_contract(BotProductMutationResponse, payload, "product deletion")

    async def build_repair_comment_draft(
        self, *, telegram_id: int, order_id: int, comment: str
    ) -> BotRepairDraftResponse:
        payload = await self._post(
            "repair-context/comment-draft",
            json={"telegram_id": telegram_id, "order_id": order_id, "comment": comment},
        )
        return self._validate_contract(BotRepairDraftResponse, payload, "repair draft")

    async def build_repair_preset_draft(
        self, *, telegram_id: int, order_id: int, fault_type: str
    ) -> BotRepairDraftResponse:
        payload = await self._post(
            "repair-context/preset-draft",
            json={"telegram_id": telegram_id, "order_id": order_id, "fault_type": fault_type},
        )
        return self._validate_contract(BotRepairDraftResponse, payload, "repair preset draft")

    async def apply_repair_context(
        self,
        *,
        telegram_id: int,
        order_id: int,
        repair_meta_draft: dict,
        raw_comment: str,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> BotRepairApplyResponse:
        payload = await self._post(
            "repair-context/apply",
            json={
                "telegram_id": telegram_id,
                "order_id": order_id,
                "repair_meta_draft": repair_meta_draft,
                "raw_comment": raw_comment,
                "telegram_chat_id": telegram_chat_id,
                "telegram_message_id": telegram_message_id,
            },
        )
        return self._validate_contract(BotRepairApplyResponse, payload, "repair apply result")
