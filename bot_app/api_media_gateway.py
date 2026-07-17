"""Typed media operations mixed into the bot HTTP gateway."""

import json

from api_contracts.bot import (
    BotNameplateApplyResponse,
    BotNameplateRecognitionResponse,
    BotOrderAttachmentResponse,
    BotOrderListResponse,
)


class BotApiMediaMixin:
    async def list_recent_orders(self, *, telegram_id: int, limit: int = 5) -> BotOrderListResponse:
        payload = await self._post(
            "orders/recent", json={"telegram_id": telegram_id, "limit": limit}
        )
        return self._validate_contract(BotOrderListResponse, payload, "order list")

    async def attach_order_file(
        self,
        *,
        telegram_id: int,
        order_id: int,
        content: bytes,
        file_id: str,
        filename: str,
        mime_type: str,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> BotOrderAttachmentResponse:
        data = {"telegram_id": str(telegram_id), "file_id": file_id}
        self._add_optional_ids(data, telegram_chat_id, telegram_message_id)
        payload = await self._post_multipart(
            f"orders/{order_id}/attachments",
            data=data,
            files={"file": (filename, content, mime_type)},
            timeout_seconds=90.0,
        )
        return self._validate_contract(BotOrderAttachmentResponse, payload, "attachment result")

    async def list_repair_nameplate_orders(
        self, *, telegram_id: int, limit: int = 5
    ) -> BotOrderListResponse:
        payload = await self._post(
            "repair-nameplates/orders",
            json={"telegram_id": telegram_id, "limit": limit},
        )
        return self._validate_contract(BotOrderListResponse, payload, "repair order list")

    async def recognize_repair_nameplate(
        self,
        *,
        telegram_id: int,
        order_id: int,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> BotNameplateRecognitionResponse:
        payload = await self._post_multipart(
            "repair-nameplates/recognize",
            data={"telegram_id": str(telegram_id), "order_id": str(order_id)},
            files={"file": (filename, content, mime_type)},
            timeout_seconds=90.0,
        )
        return self._validate_contract(BotNameplateRecognitionResponse, payload, "repair nameplate")

    async def apply_repair_nameplate(self, **kwargs) -> BotNameplateApplyResponse:
        return await self._apply_nameplate("repair-nameplates/apply", unit_type=None, **kwargs)

    async def list_warranty_nameplate_orders(
        self, *, telegram_id: int, limit: int = 5
    ) -> BotOrderListResponse:
        payload = await self._post(
            "warranty-nameplates/orders",
            json={"telegram_id": telegram_id, "limit": limit},
        )
        return self._validate_contract(BotOrderListResponse, payload, "warranty order list")

    async def recognize_warranty_nameplate(
        self,
        *,
        telegram_id: int,
        order_id: int,
        unit_type: str,
        content: bytes,
        filename: str,
        mime_type: str,
    ) -> BotNameplateRecognitionResponse:
        payload = await self._post_multipart(
            "warranty-nameplates/recognize",
            data={
                "telegram_id": str(telegram_id),
                "order_id": str(order_id),
                "unit_type": unit_type,
            },
            files={"file": (filename, content, mime_type)},
            timeout_seconds=90.0,
        )
        return self._validate_contract(BotNameplateRecognitionResponse, payload, "warranty nameplate")

    async def apply_warranty_nameplate(self, *, unit_type: str, **kwargs) -> BotNameplateApplyResponse:
        return await self._apply_nameplate(
            "warranty-nameplates/apply", unit_type=unit_type, **kwargs
        )

    async def _apply_nameplate(
        self,
        path: str,
        *,
        telegram_id: int,
        order_id: int,
        content: bytes,
        file_id: str,
        filename: str,
        mime_type: str,
        raw_text: str,
        extracted: dict,
        validation_flags: dict,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
        unit_type: str | None,
    ) -> BotNameplateApplyResponse:
        data = {
            "telegram_id": str(telegram_id),
            "order_id": str(order_id),
            "file_id": file_id,
            "raw_text": raw_text,
            "extracted_json": json.dumps(extracted, ensure_ascii=False),
            "validation_json": json.dumps(validation_flags, ensure_ascii=False),
        }
        if unit_type:
            data["unit_type"] = unit_type
        self._add_optional_ids(data, telegram_chat_id, telegram_message_id)
        payload = await self._post_multipart(
            path,
            data=data,
            files={"file": (filename, content, mime_type)},
            timeout_seconds=90.0,
        )
        return self._validate_contract(BotNameplateApplyResponse, payload, "nameplate apply result")

    @staticmethod
    def _add_optional_ids(
        data: dict[str, str], chat_id: int | None, message_id: int | None
    ) -> None:
        if chat_id is not None:
            data["telegram_chat_id"] = str(chat_id)
        if message_id is not None:
            data["telegram_message_id"] = str(message_id)
