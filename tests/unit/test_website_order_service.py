from datetime import datetime
from types import SimpleNamespace

import pytest

from models import LeadSource, OrderStatus
from schemas import OrderPayload
from services.order_service import OrderService
from services.website_order_service import WebsiteOrderService


@pytest.mark.asyncio
async def test_website_checkout_creates_negotiation_order(monkeypatch):
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

    monkeypatch.setattr(OrderService, "create_from_website", fake_create_from_website)
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

    response = await WebsiteOrderService.create_order(SimpleNamespace(), payload)

    assert response.id == 55
    assert response.status == OrderStatus.NEGOTIATION
    assert captured_kwargs["lead_source"] == LeadSource.SITE
    assert captured_kwargs["initial_status"] == OrderStatus.NEGOTIATION
    assert captured_kwargs["customer_address"] == "г. Минск, ул. Тестовая 10"
    assert captured_kwargs["items"][0]["product_id"] == 7
    assert captured_kwargs["items"][0]["with_installation"] is True
