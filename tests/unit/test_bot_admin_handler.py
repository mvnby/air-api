import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ["BOT_TOKEN"] = "123:test"

from core.config import settings

settings.BOT_TOKEN = "123:test"
from bot_app.handlers import admin as admin_handler


class _DummyMessage:
    def __init__(self, text: str, user_id: int = 1):
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.chat = SimpleNamespace(id=100)
        self.message_id = 55
        self.answer = AsyncMock()
        self.edit_text = AsyncMock()
        self.delete = AsyncMock()


class _DummyState:
    def __init__(self, data: dict):
        self._data = data
        self.clear = AsyncMock()
        self.update_data = AsyncMock(side_effect=self._update_data)
        self.set_state = AsyncMock()

    async def get_data(self):
        return self._data

    async def _update_data(self, **kwargs):
        self._data.update(kwargs)


class _DummyCallback:
    def __init__(self, data: str, user_id: int):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _DummyMessage(text="")
        self.answer = AsyncMock()


class _DummyProgress:
    def __init__(self):
        self.edit_text = AsyncMock()


class _DummySessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _fake_async_session_maker():
    return _DummySessionContext()


def test_admin_handler_has_no_direct_dao_import():
    source = Path("bot_app/handlers/admin.py").read_text(encoding="utf-8")
    assert "from crud.product import ProductDAO" not in source
    assert "from services.product_service import ProductService" in source


def test_requisites_preview_marks_field_errors_by_field_key():
    text = admin_handler._preview_text(
        {
            "extracted": {
                "name": "ООО Тест",
                "iban": "BAD",
            },
            "validation_flags": {
                "field_errors": {"iban": "Некорректный IBAN"},
                "warnings": {},
            },
        }
    )

    assert "<b>IBAN:</b> ⚠️ BAD" in text
    assert "Некорректный IBAN" in text


@pytest.mark.asyncio
async def test_edit_price_finish_calls_service(monkeypatch):
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler, "_is_admin_user", AsyncMock(return_value=True))
    service_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(admin_handler.ProductService, "update_price", service_mock)

    msg = _DummyMessage(text="12345")
    state = _DummyState({"product_id": "7"})
    await admin_handler.edit_price_finish(msg, state)

    service_mock.assert_awaited_once()
    msg.answer.assert_awaited_with("✅ Цена обновлена.")
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_item_uses_callback_answer(monkeypatch):
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    admin_check = AsyncMock(return_value=True)
    monkeypatch.setattr(admin_handler, "_is_admin_user", admin_check)
    service_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(admin_handler.ProductService, "delete", service_mock)

    callback = _DummyCallback(data="del_confirm_10_abcd1234", user_id=2)
    state = _DummyState({"delete_product_confirmation": {"product_id": 10, "token": "abcd1234"}})
    await admin_handler.delete_item(callback, state)

    service_mock.assert_awaited_once()
    admin_check.assert_awaited_once_with(2)
    callback.answer.assert_awaited_with("Товар не найден", show_alert=True)


@pytest.mark.asyncio
async def test_delete_item_prompt_requires_second_confirmation(monkeypatch):
    admin_check = AsyncMock(return_value=True)
    monkeypatch.setattr(admin_handler, "_is_admin_user", admin_check)
    service_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(admin_handler.ProductService, "delete", service_mock)

    callback = _DummyCallback(data="del_prompt_10", user_id=2)
    state = _DummyState({})
    await admin_handler.prompt_delete_item(callback, state)

    service_mock.assert_not_called()
    callback.message.answer.assert_awaited_once()
    text = callback.message.answer.await_args.args[0]
    keyboard = callback.message.answer.await_args.kwargs["reply_markup"]
    assert "Удалить товар #10" in text
    confirm_data = keyboard.inline_keyboard[0][0].callback_data
    assert confirm_data.startswith("del_confirm_10_")
    assert keyboard.inline_keyboard[0][1].callback_data == "del_cancel"
    assert state._data["delete_product_confirmation"]["product_id"] == 10
    assert state._data["delete_product_confirmation"]["token"] == confirm_data.split("_")[-1]
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_item_rejects_stale_direct_confirmation(monkeypatch):
    admin_check = AsyncMock(return_value=True)
    monkeypatch.setattr(admin_handler, "_is_admin_user", admin_check)
    service_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(admin_handler.ProductService, "delete", service_mock)

    callback = _DummyCallback(data="del_confirm_10", user_id=2)
    state = _DummyState({})
    await admin_handler.delete_item(callback, state)

    service_mock.assert_not_called()
    callback.answer.assert_awaited_with("Подтверждение устарело. Нажмите удалить ещё раз.", show_alert=True)


@pytest.mark.asyncio
async def test_delete_item_skips_service_for_non_admin(monkeypatch):
    admin_check = AsyncMock(return_value=False)
    monkeypatch.setattr(admin_handler, "_is_admin_user", admin_check)
    service_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(admin_handler.ProductService, "delete", service_mock)

    callback = _DummyCallback(data="del_confirm_10", user_id=3)
    await admin_handler.delete_item(callback, _DummyState({}))

    admin_check.assert_awaited_once_with(3)
    service_mock.assert_not_called()
    callback.answer.assert_not_called()


@pytest.mark.asyncio
async def test_is_admin_user_uses_staff_service(monkeypatch):
    session = object()

    class _StaticSessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    admin_check = AsyncMock(return_value=True)
    monkeypatch.setattr(admin_handler.StaffUserService, "is_active_owner_admin_telegram_user", admin_check)
    monkeypatch.setattr(admin_handler, "async_session_maker", lambda: _StaticSessionContext())

    assert await admin_handler._is_admin_user(7)
    admin_check.assert_awaited_once()
    assert admin_check.await_args.args == (session, 7)


@pytest.mark.asyncio
async def test_requisites_file_rejects_non_admin(monkeypatch):
    monkeypatch.setattr(admin_handler, "_is_admin_user", AsyncMock(return_value=False))
    message = _DummyMessage(text="", user_id=5)

    await admin_handler._handle_requisites_file(
        message,
        file_id="file-1",
        filename="req.png",
        mime_type="image/png",
    )

    message.answer.assert_awaited_once_with("Распознавание реквизитов доступно только администраторам.")


@pytest.mark.asyncio
async def test_requisites_file_sends_preview_for_admin(monkeypatch):
    progress = _DummyProgress()
    message = _DummyMessage(text="", user_id=5)
    message.answer = AsyncMock(return_value=progress)

    monkeypatch.setattr(admin_handler, "_is_admin_user", AsyncMock(return_value=True))
    monkeypatch.setattr(admin_handler, "_download_telegram_file", AsyncMock(return_value=b"image"))

    async def fake_recognize(session, **kwargs):
        assert kwargs["content"] == b"image"
        assert kwargs["source"] == "telegram"
        return {
            "id": 12,
            "status": "recognized",
            "source": "telegram",
            "raw_text": "raw",
            "extracted": {
                "name": "ООО Тест",
                "inn": "123456789",
                "signer_name": "Иванова Ивана Ивановича",
                "signer_position": "директора",
                "acting_basis": "Устава",
            },
            "validation_flags": {"field_errors": {}, "warnings": {}, "is_valid": True},
            "duplicate_customer": None,
        }

    monkeypatch.setattr(admin_handler.CustomerRequisitesRecognitionService, "recognize_bytes", fake_recognize)
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)

    await admin_handler._handle_requisites_file(
        message,
        file_id="file-1",
        filename="req.png",
        mime_type="image/png",
    )

    progress.edit_text.assert_awaited_once()
    args, kwargs = progress.edit_text.await_args
    assert "ООО Тест" in args[0]
    assert kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_requisites_photo_prompts_for_action_without_recognition(monkeypatch):
    message = _DummyMessage(text="", user_id=5)
    message.photo = [
        SimpleNamespace(file_id="small-photo"),
        SimpleNamespace(file_id="large-photo"),
    ]
    state = _DummyState({})

    monkeypatch.setattr(admin_handler, "_is_staff_user", AsyncMock(return_value=True))
    monkeypatch.setattr(admin_handler, "_is_admin_user", AsyncMock(return_value=True))
    recognize_mock = AsyncMock()
    monkeypatch.setattr(admin_handler.CustomerRequisitesRecognitionService, "recognize_bytes", recognize_mock)

    await admin_handler.recognize_requisites_photo(message, state)

    recognize_mock.assert_not_called()
    state.update_data.assert_awaited_once()
    pending = state._data["pending_requisites_file"]
    assert pending == {
        "file_id": "large-photo",
        "filename": "telegram-photo-55.jpg",
        "mime_type": "image/jpeg",
        "file_size": None,
        "telegram_message_id": 55,
        "telegram_chat_id": 100,
    }
    message.answer.assert_awaited_once()
    args, kwargs = message.answer.await_args
    assert "Что сделать" in args[0]
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "req_file_extract"
    assert kwargs["reply_markup"].inline_keyboard[1][0].callback_data == "repair_nameplate_start"
    assert kwargs["reply_markup"].inline_keyboard[2][0].callback_data == "warranty_nameplate_start"
    assert kwargs["reply_markup"].inline_keyboard[3][0].callback_data == "req_file_attach"


@pytest.mark.asyncio
async def test_requisites_photo_for_staff_non_admin_allows_attach_only(monkeypatch):
    message = _DummyMessage(text="", user_id=5)
    message.photo = [SimpleNamespace(file_id="large-photo")]
    state = _DummyState({})

    monkeypatch.setattr(admin_handler, "_is_staff_user", AsyncMock(return_value=True))
    monkeypatch.setattr(admin_handler, "_is_admin_user", AsyncMock(return_value=False))

    await admin_handler.recognize_requisites_photo(message, state)

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.await_args
    assert "Что сделать" in args[0]
    callbacks = [
        row[0].callback_data
        for row in kwargs["reply_markup"].inline_keyboard
    ]
    assert callbacks == ["repair_nameplate_start", "warranty_nameplate_start", "req_file_attach", "req_file_cancel"]
    assert state._data["pending_requisites_file"]["file_id"] == "large-photo"


@pytest.mark.asyncio
async def test_requisites_photo_rejects_non_staff(monkeypatch):
    message = _DummyMessage(text="", user_id=5)
    message.photo = [SimpleNamespace(file_id="large-photo")]
    state = _DummyState({})

    monkeypatch.setattr(admin_handler, "_is_staff_user", AsyncMock(return_value=False))
    monkeypatch.setattr(admin_handler, "_is_admin_user", AsyncMock(return_value=False))

    await admin_handler.recognize_requisites_photo(message, state)

    message.answer.assert_awaited_once_with("Файл получил, но действия с файлами доступны только сотрудникам.")
    assert "pending_requisites_file" not in state._data


@pytest.mark.asyncio
async def test_requisites_document_prompts_for_pdf(monkeypatch):
    message = _DummyMessage(text="", user_id=5)
    message.document = SimpleNamespace(
        file_id="pdf-file",
        file_name="requisites.pdf",
        mime_type="application/pdf",
        file_size=512,
    )
    state = _DummyState({})

    monkeypatch.setattr(admin_handler, "_is_staff_user", AsyncMock(return_value=True))
    monkeypatch.setattr(admin_handler, "_is_admin_user", AsyncMock(return_value=True))
    download_mock = AsyncMock(return_value=b"pdf")
    monkeypatch.setattr(admin_handler, "_download_telegram_file", download_mock)

    await admin_handler.recognize_requisites_document(message, state)

    download_mock.assert_not_called()
    assert state._data["pending_requisites_file"]["file_id"] == "pdf-file"
    assert state._data["pending_requisites_file"]["mime_type"] == "application/pdf"
    assert state._data["pending_requisites_file"]["file_size"] == 512
    args, kwargs = message.answer.await_args
    callbacks = [row[0].callback_data for row in kwargs["reply_markup"].inline_keyboard]
    assert "repair_nameplate_start" not in callbacks
    assert "warranty_nameplate_start" not in callbacks


@pytest.mark.asyncio
async def test_requisites_document_rejects_large_file_before_pending(monkeypatch):
    message = _DummyMessage(text="", user_id=5)
    message.document = SimpleNamespace(
        file_id="large-pdf-file",
        file_name="large.pdf",
        mime_type="application/pdf",
        file_size=admin_handler.CustomerRequisitesRecognitionService.MAX_FILE_SIZE_BYTES + 1,
    )
    state = _DummyState({})

    monkeypatch.setattr(admin_handler, "_is_staff_user", AsyncMock(return_value=True))
    admin_check = AsyncMock(return_value=True)
    monkeypatch.setattr(admin_handler, "_is_admin_user", admin_check)

    await admin_handler.recognize_requisites_document(message, state)

    assert "pending_requisites_file" not in state._data
    state.update_data.assert_not_called()
    admin_check.assert_not_called()
    message.answer.assert_awaited_once_with("Файл слишком большой. Максимум 10 МБ.")


@pytest.mark.asyncio
async def test_download_telegram_file_rejects_large_metadata_before_download(monkeypatch):
    download_file = AsyncMock()
    fake_bot = SimpleNamespace(
        get_file=AsyncMock(
            return_value=SimpleNamespace(
                file_path="documents/large.pdf",
                file_size=admin_handler.CustomerRequisitesRecognitionService.MAX_FILE_SIZE_BYTES + 1,
            )
        ),
        download_file=download_file,
    )
    monkeypatch.setattr(admin_handler, "bot", fake_bot)

    with pytest.raises(ValueError, match="Файл слишком большой"):
        await admin_handler._download_telegram_file("large-file")

    fake_bot.get_file.assert_awaited_once_with("large-file")
    download_file.assert_not_called()


@pytest.mark.asyncio
async def test_download_telegram_file_rejects_unknown_size_before_download(monkeypatch):
    download_file = AsyncMock()
    fake_bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="documents/unknown.pdf", file_size=None)),
        download_file=download_file,
    )
    monkeypatch.setattr(admin_handler, "bot", fake_bot)

    with pytest.raises(ValueError, match="размер файла"):
        await admin_handler._download_telegram_file("unknown-file")

    fake_bot.get_file.assert_awaited_once_with("unknown-file")
    download_file.assert_not_called()


@pytest.mark.asyncio
async def test_requisites_file_extract_callback_runs_recognition(monkeypatch):
    callback = _DummyCallback(data="req_file_extract", user_id=5)
    state = _DummyState(
        {
            "pending_requisites_file": {
                "file_id": "file-1",
                "filename": "req.png",
                "mime_type": "image/png",
                "telegram_message_id": 77,
                "telegram_chat_id": 200,
            }
        }
    )

    monkeypatch.setattr(admin_handler, "_is_admin_user", AsyncMock(return_value=True))
    monkeypatch.setattr(admin_handler, "_download_telegram_file", AsyncMock(return_value=b"image"))

    async def fake_recognize(session, **kwargs):
        assert kwargs["content"] == b"image"
        assert kwargs["filename"] == "req.png"
        assert kwargs["mime_type"] == "image/png"
        assert kwargs["telegram_user_id"] == 5
        assert kwargs["telegram_chat_id"] == 200
        assert kwargs["telegram_message_id"] == 77
        return {
            "id": 12,
            "status": "recognized",
            "source": "telegram",
            "raw_text": "raw",
            "extracted": {"name": "ООО Тест", "inn": "123456789"},
            "validation_flags": {"field_errors": {}, "warnings": {}, "is_valid": True},
            "duplicate_customer": None,
        }

    monkeypatch.setattr(admin_handler.CustomerRequisitesRecognitionService, "recognize_bytes", fake_recognize)
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)

    await admin_handler.extract_pending_requisites_file(callback, state)

    assert state._data["pending_requisites_file"] is None
    callback.answer.assert_awaited_once()
    assert callback.message.edit_text.await_count == 2
    final_args, final_kwargs = callback.message.edit_text.await_args
    assert "ООО Тест" in final_args[0]
    assert final_kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_requisites_file_attach_callback_shows_recent_orders(monkeypatch):
    callback = _DummyCallback(data="req_file_attach", user_id=5)
    state = _DummyState(
        {
            "pending_requisites_file": {
                "file_id": "file-1",
                "filename": "photo.jpg",
                "mime_type": "image/jpeg",
            }
        }
    )

    async def fake_list_recent(session, *, limit):
        assert limit == 5
        return [
            {
                "id": 42,
                "title": "Монтаж",
                "customer_name": "Иван",
                "address": "Победы 15",
            }
        ]

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=True)),
    )
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler.BotOrderAttachmentService, "list_recent_orders", fake_list_recent)

    await admin_handler.choose_order_for_pending_file(callback, state)

    callback.message.edit_text.assert_awaited_once()
    args, kwargs = callback.message.edit_text.await_args
    assert "К какому заказу" in args[0]
    assert "#42" in args[0]
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "req_file_attach_order_42"
    assert kwargs["reply_markup"].inline_keyboard[-2][0].callback_data == "req_file_attach_manual"
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_requisites_file_attach_callback_shows_executor_tasks(monkeypatch):
    callback = _DummyCallback(data="req_file_attach", user_id=5)
    state = _DummyState({"pending_requisites_file": {"file_id": "file-1"}})

    list_recent_mock = AsyncMock()

    async def fake_list_tasks(session, telegram_id, *, limit):
        assert telegram_id == 5
        assert limit == 5
        return [
            {
                "id": 7,
                "order_id": 42,
                "title": "Монтаж",
                "customer_name": "Иван",
                "address": "Победы 15",
            }
        ]

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=False)),
    )
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler.BotOrderAttachmentService, "list_recent_orders", list_recent_mock)
    monkeypatch.setattr(admin_handler.BotTaskService, "list_my_tasks", fake_list_tasks)

    await admin_handler.choose_order_for_pending_file(callback, state)

    list_recent_mock.assert_not_called()
    args, kwargs = callback.message.edit_text.await_args
    assert "#42" in args[0]
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "req_file_attach_order_42"


@pytest.mark.asyncio
async def test_requisites_file_attach_chosen_order_saves_and_clears_pending(monkeypatch):
    callback = _DummyCallback(data="req_file_attach_order_42", user_id=5)
    state = _DummyState(
        {
            "pending_requisites_file": {
                "file_id": "file-1",
                "filename": "photo.jpg",
                "mime_type": "image/jpeg",
                "telegram_message_id": 77,
                "telegram_chat_id": 200,
            }
        }
    )

    async def fake_attach(session, order_id, **kwargs):
        assert order_id == 42
        assert kwargs["file_id"] == "file-1"
        assert kwargs["telegram_user_id"] == 5
        assert kwargs["telegram_chat_id"] == 200
        assert kwargs["telegram_message_id"] == 77
        return {"id": 42, "already_attached": False}

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=True)),
    )
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler.BotOrderAttachmentService, "can_attach_to_order", AsyncMock(return_value=True))
    monkeypatch.setattr(admin_handler.BotOrderAttachmentService, "attach_to_order", fake_attach)

    await admin_handler.attach_pending_file_to_chosen_order(callback, state)

    assert state._data["pending_requisites_file"] is None
    state.set_state.assert_awaited_with(None)
    callback.message.edit_text.assert_awaited_once_with("✅ Файл прикреплен к заказу #42.")
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_requisites_file_attach_chosen_order_blocks_unassigned_executor(monkeypatch):
    callback = _DummyCallback(data="req_file_attach_order_42", user_id=5)
    state = _DummyState({"pending_requisites_file": {"file_id": "file-1"}})

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=False)),
    )
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler.BotOrderAttachmentService, "can_attach_to_order", AsyncMock(return_value=False))
    attach_mock = AsyncMock()
    monkeypatch.setattr(admin_handler.BotOrderAttachmentService, "attach_to_order", attach_mock)

    await admin_handler.attach_pending_file_to_chosen_order(callback, state)

    attach_mock.assert_not_called()
    callback.answer.assert_awaited_once_with("Этот заказ вам не назначен.", show_alert=True)
    assert state._data["pending_requisites_file"]["file_id"] == "file-1"


@pytest.mark.asyncio
async def test_requisites_file_attach_typed_order_validates_number(monkeypatch):
    message = _DummyMessage(text="не номер", user_id=5)
    state = _DummyState({"pending_requisites_file": {"file_id": "file-1"}})

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=True)),
    )

    await admin_handler.attach_pending_file_to_typed_order(message, state)

    message.answer.assert_awaited_once_with("Введите номер заказа числом, например: 123")
    assert state._data["pending_requisites_file"]["file_id"] == "file-1"


@pytest.mark.asyncio
async def test_repair_nameplate_start_shows_repair_orders(monkeypatch):
    callback = _DummyCallback(data="repair_nameplate_start", user_id=5)
    state = _DummyState(
        {
            "pending_requisites_file": {
                "file_id": "photo-file",
                "filename": "nameplate.jpg",
                "mime_type": "image/jpeg",
            }
        }
    )

    async def fake_list_repair_orders(session, *, telegram_user_id, can_attach_any, limit):
        assert telegram_user_id == 5
        assert can_attach_any is True
        assert limit == 5
        return [
            {
                "id": 42,
                "title": "Ремонт",
                "customer_name": "Иван",
                "address": "Победы 15",
            }
        ]

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=True)),
    )
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler.BotRepairNameplateService, "list_repair_orders", fake_list_repair_orders)

    await admin_handler.choose_order_for_repair_nameplate(callback, state)

    callback.message.edit_text.assert_awaited_once()
    args, kwargs = callback.message.edit_text.await_args
    assert "ремонтному заказу" in args[0]
    assert "#42" in args[0]
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "repair_nameplate_order_42"
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_repair_nameplate_chosen_order_runs_recognition_preview(monkeypatch):
    callback = _DummyCallback(data="repair_nameplate_order_42", user_id=5)
    state = _DummyState(
        {
            "pending_requisites_file": {
                "file_id": "photo-file",
                "filename": "nameplate.jpg",
                "mime_type": "image/jpeg",
                "telegram_message_id": 77,
                "telegram_chat_id": 200,
            }
        }
    )

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=True)),
    )
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler.BotRepairNameplateService, "can_use_order", AsyncMock(return_value=True))
    monkeypatch.setattr(admin_handler, "_download_telegram_file", AsyncMock(return_value=b"image"))
    monkeypatch.setattr(
        admin_handler.BotRepairNameplateService,
        "recognize_bytes",
        AsyncMock(
            return_value={
                "raw_text": "MODEL ALASKA AL-12LHJ",
                "extracted": {
                    "equipment_model": "ALASKA AL-12LHJ",
                    "refrigerant_type": "R22",
                },
                "validation_flags": {"warnings": {}, "is_valid": True},
            }
        ),
    )
    monkeypatch.setattr(
        admin_handler.BotRepairNameplateService,
        "build_merge_preview",
        AsyncMock(
            return_value={
                "applied": {"equipment_model": "ALASKA AL-12LHJ"},
                "conflicts": {},
                "skipped": {},
            }
        ),
    )

    await admin_handler.recognize_repair_nameplate_for_chosen_order(callback, state)

    assert callback.message.edit_text.await_count == 2
    final_args, final_kwargs = callback.message.edit_text.await_args
    assert "ALASKA AL-12LHJ" in final_args[0]
    assert final_kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "repair_nameplate_confirm"
    assert state._data["pending_repair_nameplate"]["order_id"] == 42
    assert state._data["pending_repair_nameplate"]["extracted"]["refrigerant_type"] == "R22"


@pytest.mark.asyncio
async def test_repair_nameplate_confirm_applies_and_clears_pending(monkeypatch):
    callback = _DummyCallback(data="repair_nameplate_confirm", user_id=5)
    state = _DummyState(
        {
            "pending_requisites_file": {"file_id": "photo-file"},
            "pending_repair_nameplate": {
                "order_id": 42,
                "file": {
                    "file_id": "photo-file",
                    "filename": "nameplate.jpg",
                    "mime_type": "image/jpeg",
                    "telegram_message_id": 77,
                    "telegram_chat_id": 200,
                },
                "raw_text": "MODEL ALASKA",
                "extracted": {"equipment_model": "ALASKA"},
                "validation_flags": {"warnings": {}, "is_valid": True},
            },
        }
    )

    async def fake_apply(session, order_id, **kwargs):
        assert order_id == 42
        assert kwargs["file_id"] == "photo-file"
        assert kwargs["telegram_user_id"] == 5
        assert kwargs["can_attach_any"] is True
        return {"id": 42, "applied": {"equipment_model": "ALASKA"}, "conflicts": {}}

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=True)),
    )
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler.BotRepairNameplateService, "apply_to_order", fake_apply)

    await admin_handler.confirm_repair_nameplate(callback, state)

    assert state._data["pending_repair_nameplate"] is None
    assert state._data["pending_requisites_file"] is None
    assert state._data["active_repair_order_context"] == {"order_id": 42}
    state.set_state.assert_awaited_with(admin_handler.ShopState.waiting_for_repair_context_comment)
    callback.message.edit_text.assert_awaited_once()
    args, kwargs = callback.message.edit_text.await_args
    assert "Данные со шильдика записаны" in args[0]
    assert "можно отправлять комментарии" in args[0]
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "repair_context_finish"


@pytest.mark.asyncio
async def test_warranty_nameplate_start_asks_unit_type(monkeypatch):
    callback = _DummyCallback(data="warranty_nameplate_start", user_id=5)
    state = _DummyState(
        {
            "pending_requisites_file": {
                "file_id": "photo-file",
                "filename": "nameplate.jpg",
                "mime_type": "image/jpeg",
            }
        }
    )

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=True)),
    )

    await admin_handler.choose_warranty_nameplate_unit(callback, state)

    callback.message.edit_text.assert_awaited_once()
    args, kwargs = callback.message.edit_text.await_args
    assert "Что фотографируем" in args[0]
    callbacks = [row[0].callback_data for row in kwargs["reply_markup"].inline_keyboard]
    assert callbacks[:2] == ["warranty_nameplate_unit_indoor_unit", "warranty_nameplate_unit_outdoor_unit"]


@pytest.mark.asyncio
async def test_warranty_nameplate_unit_shows_installation_orders(monkeypatch):
    callback = _DummyCallback(data="warranty_nameplate_unit_indoor_unit", user_id=5)
    state = _DummyState(
        {
            "pending_requisites_file": {
                "file_id": "photo-file",
                "filename": "nameplate.jpg",
                "mime_type": "image/jpeg",
            }
        }
    )

    async def fake_list_installation_orders(session, *, telegram_user_id, can_attach_any, limit):
        assert telegram_user_id == 5
        assert can_attach_any is True
        assert limit == 5
        return {
            "scope": "today",
            "items": [
                {
                    "id": 42,
                    "title": "Монтаж",
                    "customer_name": "Иван",
                    "address": "Победы 15",
                }
            ],
        }

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=True)),
    )
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler.BotWarrantyNameplateService, "list_installation_orders", fake_list_installation_orders)

    await admin_handler.choose_order_for_warranty_nameplate(callback, state)

    assert state._data["pending_warranty_nameplate"] == {"unit_type": "indoor_unit"}
    args, kwargs = callback.message.edit_text.await_args
    assert "сегодняшнему монтажу" in args[0]
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "warranty_nameplate_order_42"


@pytest.mark.asyncio
async def test_warranty_nameplate_chosen_order_runs_recognition_preview(monkeypatch):
    callback = _DummyCallback(data="warranty_nameplate_order_42", user_id=5)
    state = _DummyState(
        {
            "pending_requisites_file": {
                "file_id": "photo-file",
                "filename": "nameplate.jpg",
                "mime_type": "image/jpeg",
                "telegram_message_id": 77,
                "telegram_chat_id": 200,
            },
            "pending_warranty_nameplate": {"unit_type": "outdoor_unit"},
        }
    )

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=True)),
    )
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler.BotWarrantyNameplateService, "can_use_order", AsyncMock(return_value=True))
    monkeypatch.setattr(admin_handler, "_download_telegram_file", AsyncMock(return_value=b"image"))
    monkeypatch.setattr(
        admin_handler.BotRepairNameplateService,
        "recognize_bytes",
        AsyncMock(
            return_value={
                "raw_text": "MODEL 1U25S2SM1FA",
                "extracted": {
                    "equipment_model": "1U25S2SM1FA",
                    "equipment_serial_number": "SN-OUT-001",
                },
                "validation_flags": {"warnings": {}, "is_valid": True},
            }
        ),
    )
    monkeypatch.setattr(
        admin_handler.BotWarrantyNameplateService,
        "build_merge_preview",
        AsyncMock(
            return_value={
                "unit_type": "outdoor_unit",
                "unit_label": "наружный блок",
                "will_create_equipment": False,
                "will_create_component": False,
                "component": {"applied": {"serial": "SN-OUT-001"}, "conflicts": {}, "skipped": {}},
                "equipment": {"applied": {}, "conflicts": {}, "skipped": {}},
            }
        ),
    )

    await admin_handler.recognize_warranty_nameplate_for_chosen_order(callback, state)

    final_args, final_kwargs = callback.message.edit_text.await_args
    assert "наружный блок" in final_args[0]
    assert "SN-OUT-001" in final_args[0]
    assert final_kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "warranty_nameplate_confirm"
    assert state._data["pending_warranty_nameplate"]["order_id"] == 42


def test_nameplate_preview_shows_serial_candidates():
    text = admin_handler._warranty_nameplate_preview_text(
        {
            "unit_type": "outdoor_unit",
            "extracted": {
                "equipment_model": "TAC-12CHSD/UG11V3AH",
                "equipment_serial_number": "140202APZ5W16254N000085",
            },
            "validation_flags": {
                "serial_candidates": [
                    "140202APZ5W16254N000085",
                    "MO250310695980",
                    "2503106959",
                ],
                "serial_details": {
                    "format": "tcl_factory_20",
                    "unit_type_label": "наружный блок",
                    "batch_code": "44",
                    "production_date": "2016-01-25",
                    "product_serial_number": "00060",
                },
                "warnings": {},
            },
            "merge_preview": {
                "unit_type": "outdoor_unit",
                "unit_label": "наружный блок",
                "component": {"applied": {}, "conflicts": {}, "skipped": {}},
                "equipment": {"applied": {}, "conflicts": {}, "skipped": {}},
            },
        }
    )

    assert "Возможные серийные номера" in text
    assert "140202APZ5W16254N000085 (выбран)" in text
    assert "MO250310695980" in text
    assert "Расшифровка серийника TCL" in text
    assert "25.01.2016" in text
    assert "партия: 44" in text


@pytest.mark.asyncio
async def test_repair_context_comment_builds_ai_preview(monkeypatch):
    message = _DummyMessage(text="фреона нет, утечку нашли, компрессор не качает", user_id=5)
    state = _DummyState({"active_repair_order_context": {"order_id": 42}})
    progress = _DummyProgress()
    message.answer = AsyncMock(return_value=progress)

    async def fake_build(session, *, order_id, comment):
        assert order_id == 42
        assert "компрессор" in comment
        return {
            "order": {"id": 42},
            "comment": comment,
            "repair_meta": {"diagnostic_result": "Компрессор не создает давление."},
            "merge_preview": {
                "changes": {
                    "diagnostic_result": {
                        "existing": "",
                        "candidate": "Компрессор не создает давление.",
                    }
                },
                "unchanged": {},
            },
        }

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=True)),
    )
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler.BotRepairNameplateService, "build_diagnostic_comment_draft", fake_build)

    await admin_handler.handle_repair_context_comment(message, state)

    message.answer.assert_awaited_once_with("Готовлю поля дефектного акта из комментария…")
    progress.edit_text.assert_awaited_once()
    args, kwargs = progress.edit_text.await_args
    assert "Компрессор не создает давление" in args[0]
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "repair_comment_confirm"
    assert state._data["pending_repair_comment"]["repair_meta"]["diagnostic_result"] == "Компрессор не создает давление."


@pytest.mark.asyncio
async def test_repair_context_comment_confirm_applies_and_keeps_context(monkeypatch):
    callback = _DummyCallback(data="repair_comment_confirm", user_id=5)
    state = _DummyState(
        {
            "active_repair_order_context": {"order_id": 42},
            "pending_repair_comment": {
                "comment": "компрессор не качает",
                "repair_meta": {"diagnostic_result": "Компрессор не создает давление."},
                "telegram_message_id": 77,
                "telegram_chat_id": 200,
            },
        }
    )

    async def fake_apply(session, order_id, **kwargs):
        assert order_id == 42
        assert kwargs["telegram_user_id"] == 5
        assert kwargs["can_attach_any"] is True
        return {
            "id": 42,
            "changes": {"diagnostic_result": {"existing": "", "candidate": "Компрессор не создает давление."}},
            "unchanged": {},
        }

    monkeypatch.setattr(
        admin_handler,
        "_get_bot_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=True)),
    )
    monkeypatch.setattr(admin_handler, "async_session_maker", _fake_async_session_maker)
    monkeypatch.setattr(admin_handler.BotRepairNameplateService, "apply_diagnostic_comment", fake_apply)

    await admin_handler.confirm_repair_context_comment(callback, state)

    assert state._data["pending_repair_comment"] is None
    state.set_state.assert_awaited_with(admin_handler.ShopState.waiting_for_repair_context_comment)
    callback.message.edit_text.assert_awaited_once()
    args, kwargs = callback.message.edit_text.await_args
    assert "Комментарий записан" in args[0]
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "repair_context_finish"


@pytest.mark.asyncio
async def test_requisites_file_cancel_clears_pending(monkeypatch):
    callback = _DummyCallback(data="req_file_cancel", user_id=5)
    state = _DummyState({"pending_requisites_file": {"file_id": "file-1"}})

    await admin_handler.cancel_pending_requisites_file(callback, state)

    assert state._data["pending_requisites_file"] is None
    callback.message.edit_text.assert_awaited_once_with("Ок, файл оставил без обработки.")
    callback.answer.assert_awaited_once()
