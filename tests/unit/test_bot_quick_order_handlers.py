from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api_contracts.bot import (
    BotCustomerBriefResponse,
    BotCustomerRequisitesActionResponse,
    BotCustomerRequisitesRecognitionResponse,
    BotQuickOrderCreateResponse,
    BotQuickOrderDraft,
    BotQuickOrderParseResponse,
)
from bot_app.handlers import requisites as admin_handlers
from bot_app.handlers import work as work_handlers


@pytest.mark.asyncio
async def test_quick_order_parse_uses_api_and_stores_message_idempotency_key(monkeypatch):
    draft = BotQuickOrderDraft(
        name="Иван",
        phone="+375291234567",
        address="Победы 15",
        service_type="maintenance",
        service_label="Обслуживание",
        target_date="2026-07-20T14:00:00",
        request_text="ТО Иван",
    )
    gateway = SimpleNamespace(
        parse_quick_order=AsyncMock(return_value=BotQuickOrderParseResponse(draft=draft))
    )
    monkeypatch.setattr(work_handlers, "get_bot_api_gateway", lambda: gateway)
    monkeypatch.setattr(
        work_handlers,
        "_require_staff",
        AsyncMock(return_value=SimpleNamespace(is_manager=True, is_staff=True)),
    )
    monkeypatch.setattr(work_handlers.BotTelegramService, "send_rich_message", AsyncMock(return_value=True))
    message = SimpleNamespace(
        text=" ТО Иван ",
        from_user=SimpleNamespace(id=123),
        chat=SimpleNamespace(id=-100),
        message_id=55,
        answer=AsyncMock(),
    )
    state = SimpleNamespace(update_data=AsyncMock())

    await work_handlers.quick_order_parse(message, state)

    gateway.parse_quick_order.assert_awaited_once_with(telegram_id=123, text="ТО Иван")
    state.update_data.assert_awaited_once()
    assert state.update_data.await_args.kwargs["quick_order_idempotency_key"] == "telegram:-100:55"
    assert state.update_data.await_args.kwargs["quick_order_draft"]["service_label"] == "Обслуживание"


@pytest.mark.asyncio
async def test_quick_order_create_uses_api_and_reports_idempotent_replay(monkeypatch):
    gateway = SimpleNamespace(
        create_quick_order=AsyncMock(
            return_value=BotQuickOrderCreateResponse(
                order_id=42,
                customer_id=7,
                created=False,
            )
        )
    )
    monkeypatch.setattr(work_handlers, "get_bot_api_gateway", lambda: gateway)
    monkeypatch.setattr(
        work_handlers,
        "_access_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True, is_manager=True)),
    )
    monkeypatch.setattr(work_handlers, "_answer_with_staff_menu", AsyncMock())
    draft = BotQuickOrderDraft(
        service_label="Обслуживание",
        service_type="maintenance",
        request_text="ТО Иван",
    ).model_dump(mode="json")

    class State:
        async def get_data(self):
            return {
                "quick_order_draft": draft,
                "quick_order_idempotency_key": "telegram:-100:55",
            }

        update_data = AsyncMock()
        clear = AsyncMock()

    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
        answer=AsyncMock(),
    )

    await work_handlers.quick_order_create(callback, State())

    gateway.create_quick_order.assert_awaited_once_with(
        telegram_id=123,
        idempotency_key="telegram:-100:55",
        draft=draft,
    )
    assert "уже был создан" in callback.message.edit_text.await_args.args[0]
    State.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_customer_requisites_confirmation_uses_api_without_db(monkeypatch):
    recognition = BotCustomerRequisitesRecognitionResponse(
        id=12,
        status="confirmed",
        source="telegram_text",
        extracted={"name": "ООО Тест"},
        validation_flags={},
        confirmed_customer_id=7,
        confirmed_action="create",
        created_at=datetime(2026, 7, 17, 12, 0),
    )
    gateway = SimpleNamespace(
        apply_customer_requisites_action=AsyncMock(
            return_value=BotCustomerRequisitesActionResponse(
                recognition=recognition,
                customer=BotCustomerBriefResponse(id=7, name="ООО Тест"),
                changed=True,
            )
        )
    )
    monkeypatch.setattr(admin_handlers, "get_bot_api_gateway", lambda: gateway)
    monkeypatch.setattr(admin_handlers, "_is_admin_user", AsyncMock(return_value=True))
    callback = SimpleNamespace(
        data="ocr_create_12",
        from_user=SimpleNamespace(id=123),
        message=SimpleNamespace(edit_text=AsyncMock()),
        answer=AsyncMock(),
    )

    await admin_handlers.confirm_requisites_recognition(callback)

    gateway.apply_customer_requisites_action.assert_awaited_once_with(
        telegram_id=123,
        recognition_id=12,
        action="create",
    )
    assert "ООО Тест" in callback.message.edit_text.await_args.args[0]
