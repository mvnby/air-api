from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.database import get_session
from core.tenant_scope import get_public_tenant_scope
from routers.api_orders import router
from services.installation_pricing_service import InstallationPricingError
from services.website_order_service import WebsiteOrderService
from services.tenant_scope_service import TenantScope


def _payload_with_item(item: dict) -> dict:
    return {
        "customer": {
            "name": "Тестовый клиент",
            "phone": "+375291112233",
        },
        "items": [item],
    }


@pytest.fixture
def checkout_app(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    async def override_session():
        yield object()

    async def override_tenant_scope():
        return TenantScope(
            tenant_id=1,
            storefront_id=1,
            is_system=True,
        )

    create_order = AsyncMock()
    monkeypatch.setattr(WebsiteOrderService, "create_order", create_order)
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_public_tenant_scope] = override_tenant_scope
    return app, create_order


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [-1, 0, 21, 1_000_000])
async def test_public_checkout_rejects_out_of_range_quantity(checkout_app, quantity):
    app, create_order = checkout_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/orders",
            json=_payload_with_item({"product_id": 1, "quantity": quantity}),
        )

    assert response.status_code == 422
    create_order.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"product_id": index + 1, "quantity": 1} for index in range(21)],
    ],
)
async def test_public_checkout_rejects_empty_or_oversized_cart(checkout_app, items):
    app, create_order = checkout_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/orders",
            json={
                "customer": {"name": "Тест", "phone": "+375291112233"},
                "items": items,
            },
        )

    assert response.status_code == 422
    create_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_checkout_rejects_omitted_cart_items(checkout_app):
    app, create_order = checkout_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/orders",
            json={"customer": {"name": "Тест", "phone": "+375291112233"}},
        )

    assert response.status_code == 422
    create_order.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item",
    [
        {"product_id": None, "quantity": 1},
        {
            "product_id": None,
            "quantity": 1,
            "with_installation": True,
        },
        {
            "product_id": 1,
            "quantity": 1,
            "with_installation": True,
            "installation_options": ["same-option", "same-option"],
        },
        {
            "product_id": 1,
            "quantity": 1,
            "with_installation": True,
            "installation_options": ["INVALID OPTION"],
        },
        {
            "product_id": 1,
            "quantity": 1,
            "with_installation": True,
            "installation_meta": {"meters": 0},
        },
        {
            "product_id": 1,
            "quantity": 1,
            "with_installation": True,
            "installation_meta": {"meters": 51},
        },
        {
            "product_id": 1,
            "quantity": 1,
            "with_installation": True,
            "installation_options": [f"option-{index}" for index in range(21)],
        },
    ],
)
async def test_public_checkout_rejects_ambiguous_installation_payloads(checkout_app, item):
    app, create_order = checkout_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/orders", json=_payload_with_item(item))

    assert response.status_code == 422
    create_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_checkout_maps_authoritative_pricing_error_to_documented_conflict(checkout_app):
    app, create_order = checkout_app
    create_order.side_effect = InstallationPricingError(
        "Неизвестный тариф монтажа #999",
        code="installation_rate_not_available",
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/orders",
            json=_payload_with_item({"product_id": 1, "quantity": 1}),
        )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "installation_rate_not_available",
        "message": "Неизвестный тариф монтажа #999",
    }
    responses = app.openapi()["paths"]["/api/v1/orders"]["post"]["responses"]
    assert responses["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PublicOrderPricingErrorResponse"
    }


@pytest.mark.asyncio
async def test_public_checkout_rejects_oversized_customer_and_comment(checkout_app):
    app, create_order = checkout_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/orders",
            json={
                "customer": {
                    "name": "x" * 161,
                    "phone": "+375291112233",
                },
                "items": [{"product_id": 1, "quantity": 1}],
                "comment": "x" * 2001,
            },
        )

    assert response.status_code == 422
    create_order.assert_not_awaited()
