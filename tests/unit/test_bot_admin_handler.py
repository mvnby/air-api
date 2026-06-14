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

    callback = _DummyCallback(data="del_confirm_10", user_id=2)
    await admin_handler.delete_item(callback)

    service_mock.assert_awaited_once()
    admin_check.assert_awaited_once_with(2)
    callback.answer.assert_awaited_with("Товар не найден", show_alert=True)


@pytest.mark.asyncio
async def test_delete_item_skips_service_for_non_admin(monkeypatch):
    admin_check = AsyncMock(return_value=False)
    monkeypatch.setattr(admin_handler, "_is_admin_user", admin_check)
    service_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(admin_handler.ProductService, "delete", service_mock)

    callback = _DummyCallback(data="del_confirm_10", user_id=3)
    await admin_handler.delete_item(callback)

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
        "telegram_message_id": 55,
        "telegram_chat_id": 100,
    }
    message.answer.assert_awaited_once()
    args, kwargs = message.answer.await_args
    assert "Что сделать" in args[0]
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "req_file_extract"


@pytest.mark.asyncio
async def test_requisites_document_prompts_for_pdf(monkeypatch):
    message = _DummyMessage(text="", user_id=5)
    message.document = SimpleNamespace(
        file_id="pdf-file",
        file_name="requisites.pdf",
        mime_type="application/pdf",
    )
    state = _DummyState({})

    monkeypatch.setattr(admin_handler, "_is_admin_user", AsyncMock(return_value=True))
    download_mock = AsyncMock(return_value=b"pdf")
    monkeypatch.setattr(admin_handler, "_download_telegram_file", download_mock)

    await admin_handler.recognize_requisites_document(message, state)

    download_mock.assert_not_called()
    assert state._data["pending_requisites_file"]["file_id"] == "pdf-file"
    assert state._data["pending_requisites_file"]["mime_type"] == "application/pdf"


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
async def test_requisites_file_cancel_clears_pending(monkeypatch):
    callback = _DummyCallback(data="req_file_cancel", user_id=5)
    state = _DummyState({"pending_requisites_file": {"file_id": "file-1"}})

    await admin_handler.cancel_pending_requisites_file(callback, state)

    assert state._data["pending_requisites_file"] is None
    callback.message.edit_text.assert_awaited_once_with("Ок, файл оставил без обработки.")
    callback.answer.assert_awaited_once()
