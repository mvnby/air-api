from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.config import settings
from services.notification_service import NotificationService


class _DummyResult:
    def __init__(self, order):
        self._order = order

    def scalar_one_or_none(self):
        return self._order


class _DummySession:
    def __init__(self, order):
        self._order = order
        self.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, _stmt):
        return _DummyResult(self._order)


@pytest.mark.asyncio
async def test_notify_admins_new_order_skips_when_no_admins(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)

    session = _DummySession(order=None)
    send_mock = AsyncMock()
    monkeypatch.setattr("services.notification_service.BotService.send_message", send_mock)

    await NotificationService.notify_admins_new_order(
        session=session,
        order_id=1,
        customer_name="User",
        customer_username="user",
        customer_phone="+123",
    )

    session.execute.assert_not_called()
    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_notify_admins_new_order_warns_for_missing_order(monkeypatch, caplog):
    monkeypatch.setattr(settings, "ADMIN_IDS", "999", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)

    session = _DummySession(order=None)
    send_mock = AsyncMock()
    monkeypatch.setattr("services.notification_service.BotService.send_message", send_mock)

    with caplog.at_level("WARNING"):
        await NotificationService.notify_admins_new_order(
            session=session,
            order_id=404,
            customer_name="User",
            customer_username="user",
            customer_phone="+123",
        )

    assert "NOTIFY_NEW_ORDER_SKIPPED missing_order_id=404" in caplog.text
    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_notify_admins_new_order_sends_to_admins(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_IDS", "10,11", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 12, raising=False)

    order = SimpleNamespace(
        id=77,
        total_amount=999,
        user_id=500,
        delivery_address="phone",
        product_links=[
            SimpleNamespace(
                product=SimpleNamespace(title="Model X"),
                product_id=1,
                price=500,
                quantity=2,
                is_installation_included=True,
                installation_price=120,
            ),
        ],
    )
    session = _DummySession(order=order)
    send_mock = AsyncMock()
    monkeypatch.setattr("services.notification_service.BotService.send_message", send_mock)

    await NotificationService.notify_admins_new_order(
        session=session,
        order_id=77,
        customer_name="Ivan",
        customer_username="ivanov",
        customer_phone="+375291234567",
    )

    assert send_mock.await_count == 3
    sent_text = send_mock.await_args_list[0].args[1]
    assert "НОВЫЙ ЗАКАЗ #77" in sent_text
    assert "Model X x2" in sent_text
    assert "Монтаж: 120 BYN" in sent_text
