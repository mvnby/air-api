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
    BotQuickOrderDraftSessionResponse,
    BotQuickOrderParseResponse,
)
from bot_app.handlers import requisites as admin_handlers
from bot_app.handlers import work as work_handlers


@pytest.mark.asyncio
async def test_quick_order_parse_stores_server_draft_reference(monkeypatch):
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
        start_quick_order_draft=AsyncMock(return_value=BotQuickOrderDraftSessionResponse(
            draft_id="a" * 32, version=1, status="active", draft=draft,
            expires_at=datetime(2026, 9, 28, 12, 0),
        ))
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
    state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())

    await work_handlers.quick_order_parse(message, state)

    gateway.start_quick_order_draft.assert_awaited_once_with(telegram_id=123, text="ТО Иван")
    state.update_data.assert_awaited_once()
    assert state.update_data.await_args.kwargs["quick_order_draft_id"] == "a" * 32
    assert state.update_data.await_args.kwargs["quick_order_version"] == 1


@pytest.mark.asyncio
async def test_quick_order_create_uses_api_and_reports_idempotent_replay(monkeypatch):
    gateway = SimpleNamespace(
        get_quick_order_draft=AsyncMock(return_value=BotQuickOrderDraftSessionResponse(
            draft_id="a" * 32, version=1, status="active",
            draft=BotQuickOrderDraft(
                service_label="Обслуживание", service_type="maintenance", request_text="ТО Иван"
            ),
            expires_at=datetime(2026, 9, 28, 12, 0),
        )),
        create_quick_order_from_draft=AsyncMock(
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
    class State:
        async def get_data(self):
            return {
                "quick_order_draft_id": "a" * 32,
                "quick_order_version": 1,
            }

        update_data = AsyncMock()
        clear = AsyncMock()

    callback = SimpleNamespace(
        data=f"qo_create:{'a' * 32}:1",
        from_user=SimpleNamespace(id=123),
        message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
        answer=AsyncMock(),
    )

    await work_handlers.quick_order_action(callback, State())

    gateway.create_quick_order_from_draft.assert_awaited_once_with(
        telegram_id=123,
        draft_id="a" * 32,
        expected_version=1,
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

    await admin_handlers.confirm_requisites_recognition(callback, SimpleNamespace(update_data=AsyncMock()))

    gateway.apply_customer_requisites_action.assert_awaited_once_with(
        telegram_id=123,
        recognition_id=12,
        action="create",
    )
    assert "ООО Тест" in callback.message.edit_text.await_args.args[0]
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == "req_order:12:7"


@pytest.mark.asyncio
async def test_requisites_customer_starts_trusted_order_draft_with_work_note(monkeypatch):
    draft = BotQuickOrderDraft(
        customer_id=7, name="ООО Тест", service_label="Обслуживание",
        service_type="maintenance", request_text="Нужно обслуживание по адресу Витебск",
    )
    draft_session = BotQuickOrderDraftSessionResponse(
        draft_id="b" * 32, version=1, status="active", draft=draft,
        expires_at=datetime(2026, 9, 28, 12, 0),
    )
    gateway = SimpleNamespace(start_quick_order_draft=AsyncMock(return_value=draft_session))
    monkeypatch.setattr(admin_handlers, "get_bot_api_gateway", lambda: gateway)
    monkeypatch.setattr(admin_handlers, "_is_admin_user", AsyncMock(return_value=True))
    from bot_app.handlers import work as work_handlers
    monkeypatch.setattr(work_handlers, "_send_quick_order_preview", AsyncMock())
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={
            "requisites_order_context": {"12": "Нужно обслуживание по адресу Витебск"},
            "requisites_confirmed_customer": {"12": 7},
        }),
        update_data=AsyncMock(), set_state=AsyncMock(),
    )
    callback = SimpleNamespace(
        data="req_order:12:7", from_user=SimpleNamespace(id=123),
        message=SimpleNamespace(), answer=AsyncMock(),
    )

    await admin_handlers.start_order_after_requisites(callback, state)

    gateway.start_quick_order_draft.assert_awaited_once_with(
        telegram_id=123, customer_id=7, text="Нужно обслуживание по адресу Витебск"
    )
    assert state.update_data.await_args.kwargs["quick_order_draft_id"] == "b" * 32
