import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from models import Order, OrderProductLink, Payment, PaymentCurrency
from routers import manager_settings
from schemas import PaymentCreatePayload
from services.fx_rate_service import FxRateService
from services.order_service import OrderService


def test_order_calculate_totals_handles_mixed_currency_payments():
    order = Order(
        tenant_id=1,
        storefront_id=1,
        target_currency=PaymentCurrency.USD,
        target_currency_amount=1000,
    )
    order.product_links = [OrderProductLink(quantity=1, price=3200, cost=0)]
    order.service_links = []
    order.installers = []
    order.payments = [
        Payment(amount=320, currency=PaymentCurrency.BYN),
        Payment(amount=100, currency=PaymentCurrency.USD),
    ]
    order.calculate_totals()

    assert order.total_payments == pytest.approx(640)
    assert order.target_currency_payments == pytest.approx(200)
    assert order.balance_due == pytest.approx(2560)


def test_normalize_payment_currency_accepts_upper_and_lowercase():
    assert OrderService._normalize_payment_currency("USD") == PaymentCurrency.USD
    assert OrderService._normalize_payment_currency("usd") == PaymentCurrency.USD

    with pytest.raises(ValueError):
        OrderService._normalize_payment_currency("USDT")


def test_payment_payload_rejects_invalid_currency():
    payload = PaymentCreatePayload(amount=10, currency=PaymentCurrency.EUR, type="prepayment")
    assert payload.currency == PaymentCurrency.EUR

    with pytest.raises(Exception):
        PaymentCreatePayload(amount=10, currency="USDT", type="prepayment")


def test_payment_payload_rejects_non_positive_amounts():
    with pytest.raises(ValidationError):
        PaymentCreatePayload(amount=0, currency=PaymentCurrency.BYN, type="prepayment")


@pytest.mark.asyncio
async def test_effective_eur_rate_is_none_in_manual_mode(monkeypatch):
    async def fake_source(_session):
        return "manual"

    monkeypatch.setattr(FxRateService, "_get_rate_source", fake_source)
    assert await FxRateService.get_effective_eur_byn_rate(None) is None


@pytest.mark.asyncio
async def test_address_suggest_hides_upstream_details(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "super-secret-key")

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, *args, **kwargs):
            raise manager_settings.httpx.ConnectError(
                "upstream failed for https://suggest-maps.yandex.ru/v1/suggest?apikey=super-secret-key",
            )

    monkeypatch.setattr(manager_settings.httpx, "AsyncClient", lambda timeout: FakeAsyncClient())

    with pytest.raises(HTTPException) as exc:
        await manager_settings.suggest_address("Минск")

    assert exc.value.status_code == 502
    assert "super-secret-key" not in str(exc.value.detail)
