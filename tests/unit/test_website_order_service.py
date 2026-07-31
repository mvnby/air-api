from datetime import datetime
from types import SimpleNamespace

import pytest

from models import LeadSource, OrderStatus
from schemas import OrderPayload
from services.bot_service import BotService
from services.installation_pricing_service import InstallationPricingService
from services.order_service import OrderService
from services.staff_user_service import StaffUserService
from services.website_order_service import WebsiteOrderService


@pytest.mark.asyncio
async def test_website_checkout_creates_negotiation_order(monkeypatch, tenant_scope):
    captured_kwargs = {}

    async def fake_create_from_website(**kwargs):
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            id=55,
            status=OrderStatus.NEGOTIATION,
            total_amount=3456,
            created_at=datetime.now(),
        )

    async def fake_notify_admins(*_args, **_kwargs):
        return None

    async def fake_price_items(_session, items):
        return [item.model_dump() for item in items]

    monkeypatch.setattr(OrderService, "create_from_website", fake_create_from_website)
    monkeypatch.setattr(InstallationPricingService, "price_public_items", fake_price_items)
    monkeypatch.setattr(WebsiteOrderService, "_notify_admins", fake_notify_admins)

    payload = OrderPayload.model_validate(
        {
            "customer": {
                "name": "Тестовый клиент",
                "phone": "+375291112233",
                "email": "checkout@example.com",
                "address": "г. Минск, ул. Тестовая 10",
            },
            "items": [
                {
                    "product_id": 7,
                    "quantity": 1,
                    "with_installation": True,
                    "installation_price": 280,
                    "installation_meta": {"source": "web"},
                    "installation_options": ["standard"],
                }
            ],
            "comment": "Нужен монтаж",
        }
    )

    response = await WebsiteOrderService.create_order(
        SimpleNamespace(),
        payload,
        tenant_scope=tenant_scope,
    )

    assert response.id == 55
    assert response.status == OrderStatus.NEGOTIATION
    assert captured_kwargs["lead_source"] == LeadSource.SITE
    assert captured_kwargs["initial_status"] == OrderStatus.NEGOTIATION
    assert captured_kwargs["customer_address"] == "г. Минск, ул. Тестовая 10"
    assert captured_kwargs["items"][0]["product_id"] == 7
    assert captured_kwargs["items"][0]["with_installation"] is True
    assert captured_kwargs["tenant_scope"] == tenant_scope


@pytest.mark.asyncio
async def test_website_checkout_does_not_attempt_telegram_without_recipients(
    monkeypatch,
    tenant_scope,
):
    order = SimpleNamespace(
        id=56,
        status=OrderStatus.NEGOTIATION,
        total_amount=100,
        created_at=datetime.now(),
    )
    send_attempted = False

    async def fake_create_from_website(**_kwargs):
        return order

    async def fake_recipients(_session, *, tenant_scope):
        return []

    async def fail_if_sent(*_args, **_kwargs):
        nonlocal send_attempted
        send_attempted = True
        raise AssertionError("checkout attempted Telegram network delivery")

    async def fake_price_items(_session, items):
        return [item.model_dump() for item in items]

    monkeypatch.setattr(OrderService, "create_from_website", fake_create_from_website)
    monkeypatch.setattr(InstallationPricingService, "price_public_items", fake_price_items)
    monkeypatch.setattr(
        StaffUserService,
        "get_active_owner_admin_telegram_recipient_ids",
        fake_recipients,
    )
    monkeypatch.setattr(BotService, "send_message", fail_if_sent)

    payload = OrderPayload.model_validate(
        {
            "customer": {
                "name": "Тестовый клиент",
                "phone": "+375291112233",
                "email": "checkout@example.com",
            },
            "items": [{"product_id": 7, "quantity": 1}],
        }
    )

    response = await WebsiteOrderService.create_order(
        object(),
        payload,
        tenant_scope=tenant_scope,
    )

    assert response.id == 56
    assert send_attempted is False


@pytest.mark.asyncio
async def test_website_order_notification_escapes_and_bounds_untrusted_fields(
    monkeypatch,
    caplog,
    tenant_scope,
):
    payload = OrderPayload.model_validate(
        {
            "customer": {
                "name": "Иван <script>",
                "phone": "+375291112233",
                "email": "checkout@example.com",
                "address": "Минск <центр>",
            },
            "items": [{"product_id": 7, "quantity": 1}],
            "comment": "Нужно <b>срочно</b> & аккуратно",
        }
    )
    order = SimpleNamespace(
        id=55,
        total_amount=3456,
        product_links=[
            SimpleNamespace(
                product=SimpleNamespace(title="Model <X>"),
                product_id=7,
                price=3000,
                quantity=1,
                is_installation_included=True,
                installation_price=280,
            )
        ],
        service_links=[SimpleNamespace(title="Сервис <премиум>", price=176, quantity=1)],
    )
    sent_messages = []

    class _Session:
        async def refresh(self, *_args, **_kwargs):
            return None

    async def fake_recipients(_session, *, tenant_scope):
        return [101, 202]

    async def fake_send_message(admin_id, text):
        sent_messages.append((admin_id, text))
        return admin_id == 101

    monkeypatch.setattr(
        StaffUserService,
        "get_active_owner_admin_telegram_recipient_ids",
        fake_recipients,
    )
    monkeypatch.setattr(BotService, "send_message", fake_send_message)

    with caplog.at_level("WARNING"):
        await WebsiteOrderService._notify_admins(
            _Session(),
            order,
            payload,
            tenant_scope=tenant_scope,
        )

    assert [admin_id for admin_id, _text in sent_messages] == [101, 202]
    sent_text = sent_messages[0][1]
    assert "Иван &lt;script&gt;" in sent_text
    assert "Минск &lt;центр&gt;" in sent_text
    assert "Нужно &lt;b&gt;срочно&lt;/b&gt; &amp; аккуратно" in sent_text
    assert "Model &lt;X&gt;" in sent_text
    assert "Сервис &lt;премиум&gt;" in sent_text
    assert "<script>" not in sent_text
    assert len(sent_text) <= BotService.MAX_MESSAGE_LENGTH
    assert "WEBSITE_ORDER_NOTIFY_DELIVERY_FAILED order_id=55 admin_id=202" in caplog.text
