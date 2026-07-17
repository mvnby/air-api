from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api_contracts.bot import (
    BotNameplateRecognitionResponse,
    BotOrderAttachmentResponse,
    BotOrderBriefResponse,
    BotOrderListResponse,
    BotProductMutationResponse,
    BotRepairApplyResponse,
    BotRepairDraftResponse,
)
from bot_app.handlers import admin_common, attachments, nameplates, product_admin, repair_context, requisites


class Message:
    def __init__(self, text: str = "", user_id: int = 5):
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.chat = SimpleNamespace(id=100)
        self.message_id = 55
        self.answer = AsyncMock()
        self.edit_text = AsyncMock()
        self.delete = AsyncMock()


class Callback:
    def __init__(self, data: str, user_id: int = 5):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = Message(user_id=user_id)
        self.answer = AsyncMock()


class State:
    def __init__(self, data: dict | None = None):
        self.data = data or {}
        self.update_data = AsyncMock(side_effect=self._update)
        self.set_state = AsyncMock()
        self.clear = AsyncMock()

    async def get_data(self):
        return self.data

    async def _update(self, **values):
        self.data.update(values)


def staff(*, manager: bool = True):
    return SimpleNamespace(is_staff=True, is_manager=manager)


def test_requisites_preview_marks_field_errors():
    text = admin_common._preview_text(
        {
            "extracted": {"name": "ООО Тест", "iban": "BAD"},
            "validation_flags": {
                "field_errors": {"iban": "Некорректный IBAN"},
                "warnings": {},
            },
        }
    )
    assert "<b>IBAN:</b> ⚠️ BAD" in text
    assert "Некорректный IBAN" in text


@pytest.mark.asyncio
async def test_requisites_photo_builds_staff_action_menu(monkeypatch):
    message = Message()
    message.photo = [SimpleNamespace(file_id="photo", file_size=100)]
    state = State()
    monkeypatch.setattr(admin_common, "_is_staff_user", AsyncMock(return_value=True))
    monkeypatch.setattr(admin_common, "_is_admin_user", AsyncMock(return_value=True))

    await requisites.recognize_requisites_photo(message, state)

    assert state.data["pending_requisites_file"]["file_id"] == "photo"
    callbacks = [row[0].callback_data for row in message.answer.await_args.kwargs["reply_markup"].inline_keyboard]
    assert callbacks == [
        "req_file_extract",
        "repair_nameplate_start",
        "warranty_nameplate_start",
        "req_file_attach",
        "req_file_cancel",
    ]


@pytest.mark.asyncio
async def test_manager_attachment_order_list_uses_api(monkeypatch):
    callback = Callback("req_file_attach")
    state = State({"pending_requisites_file": {"file_id": "file"}})
    gateway = SimpleNamespace(
        list_recent_orders=AsyncMock(
            return_value=BotOrderListResponse(
                items=[BotOrderBriefResponse(id=42, title="Монтаж", status="execution")]
            )
        )
    )
    monkeypatch.setattr(attachments, "_get_bot_access_context", AsyncMock(return_value=staff()))
    monkeypatch.setattr(attachments, "get_bot_api_gateway", lambda: gateway)

    await attachments.choose_order_for_pending_file(callback, state)

    gateway.list_recent_orders.assert_awaited_once_with(telegram_id=5, limit=5)
    assert "#42" in callback.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_attachment_upload_uses_api_bytes(monkeypatch):
    state = State(
        {
            "pending_requisites_file": {
                "file_id": "file",
                "filename": "photo.jpg",
                "mime_type": "image/jpeg",
                "telegram_chat_id": 100,
                "telegram_message_id": 55,
            }
        }
    )
    gateway = SimpleNamespace(
        attach_order_file=AsyncMock(
            return_value=BotOrderAttachmentResponse(order_id=42, already_attached=False)
        )
    )
    monkeypatch.setattr(attachments, "_download_telegram_file", AsyncMock(return_value=b"image"))
    monkeypatch.setattr(attachments, "get_bot_api_gateway", lambda: gateway)

    result = await attachments._attach_pending_file_to_order(
        order_id=42, telegram_user_id=5, can_attach_any=True, state=state
    )

    assert result == {"id": 42, "already_attached": False}
    gateway.attach_order_file.assert_awaited_once()
    assert gateway.attach_order_file.await_args.kwargs["content"] == b"image"


@pytest.mark.asyncio
async def test_repair_nameplate_recognition_uses_api(monkeypatch):
    state = State(
        {"pending_requisites_file": {"file_id": "photo", "filename": "plate.jpg", "mime_type": "image/jpeg"}}
    )
    progress = Message()
    response = BotNameplateRecognitionResponse(
        order_id=42,
        raw_text="MODEL X",
        extracted={"equipment_model": "X"},
        merge_preview={"applied": {"equipment_model": "X"}},
    )
    gateway = SimpleNamespace(recognize_repair_nameplate=AsyncMock(return_value=response))
    monkeypatch.setattr(nameplates, "_download_telegram_file", AsyncMock(return_value=b"image"))
    monkeypatch.setattr(nameplates, "get_bot_api_gateway", lambda: gateway)

    await nameplates._run_repair_nameplate_recognition_for_order(
        progress, order_id=42, telegram_user_id=5, can_attach_any=True, state=state
    )

    gateway.recognize_repair_nameplate.assert_awaited_once()
    assert state.data["pending_repair_nameplate"]["extracted"]["equipment_model"] == "X"


@pytest.mark.asyncio
async def test_product_price_update_uses_api(monkeypatch):
    message = Message("12345")
    state = State({"product_id": "7"})
    gateway = SimpleNamespace(
        update_product_price=AsyncMock(
            return_value=BotProductMutationResponse(product_id=7, changed=True)
        )
    )
    monkeypatch.setattr(product_admin, "_is_admin_user", AsyncMock(return_value=True))
    monkeypatch.setattr(product_admin, "get_bot_api_gateway", lambda: gateway)

    await product_admin.edit_price_finish(message, state)

    gateway.update_product_price.assert_awaited_once_with(
        telegram_id=5, product_id=7, price=12345
    )
    message.answer.assert_awaited_with("✅ Цена обновлена.")


@pytest.mark.asyncio
async def test_product_delete_requires_token_and_uses_api(monkeypatch):
    callback = Callback("del_confirm_10_abcd")
    state = State({"delete_product_confirmation": {"product_id": 10, "token": "abcd"}})
    gateway = SimpleNamespace(
        delete_product=AsyncMock(
            return_value=BotProductMutationResponse(product_id=10, changed=True)
        )
    )
    monkeypatch.setattr(product_admin, "_is_admin_user", AsyncMock(return_value=True))
    monkeypatch.setattr(product_admin, "get_bot_api_gateway", lambda: gateway)

    await product_admin.delete_item(callback, state)

    gateway.delete_product.assert_awaited_once_with(telegram_id=5, product_id=10)
    callback.message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_repair_context_comment_draft_uses_api(monkeypatch):
    message = Message("компрессор не качает")
    progress = Message()
    message.answer = AsyncMock(return_value=progress)
    state = State({"active_repair_order_context": {"order_id": 42}})
    draft = {
        "comment": message.text,
        "repair_meta": {"diagnostic_result": "Нет давления"},
        "merge_preview": {"changes": {}, "unchanged": {}},
    }
    gateway = SimpleNamespace(
        build_repair_comment_draft=AsyncMock(
            return_value=BotRepairDraftResponse(draft=draft)
        )
    )
    monkeypatch.setattr(repair_context, "_access_context", AsyncMock(return_value=staff()))
    monkeypatch.setattr(repair_context, "get_bot_api_gateway", lambda: gateway)

    await repair_context.handle_repair_context_comment(message, state)

    gateway.build_repair_comment_draft.assert_awaited_once_with(
        telegram_id=5, order_id=42, comment="компрессор не качает"
    )
    assert state.data["pending_repair_comment"]["telegram_message_id"] == 55


@pytest.mark.asyncio
async def test_repair_context_apply_uses_api(monkeypatch):
    callback = Callback("repair_comment_confirm")
    state = State(
        {
            "active_repair_order_context": {"order_id": 42},
            "pending_repair_comment": {
                "comment": "компрессор не качает",
                "repair_meta": {"diagnostic_result": "Нет давления"},
                "telegram_chat_id": 100,
                "telegram_message_id": 55,
            },
        }
    )
    gateway = SimpleNamespace(
        apply_repair_context=AsyncMock(
            return_value=BotRepairApplyResponse(result={"id": 42, "changes": {}})
        )
    )
    monkeypatch.setattr(repair_context, "_access_context", AsyncMock(return_value=staff()))
    monkeypatch.setattr(repair_context, "get_bot_api_gateway", lambda: gateway)

    await repair_context.confirm_repair_context_comment(callback, state)

    gateway.apply_repair_context.assert_awaited_once()
    assert state.data["pending_repair_comment"] is None


def test_repair_context_preview_counts_replacements():
    text = repair_context.repair_comment_preview_text(
        {
            "repair_meta": {"likely_diagnosis": "КЗ компрессора"},
            "merge_preview": {
                "changes": {
                    "likely_diagnosis": {"existing": "Старое", "candidate": "Новое"}
                }
            },
        }
    )
    assert "КЗ компрессора" in text
    assert "обновлены: 1" in text
