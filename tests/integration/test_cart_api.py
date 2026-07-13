from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from models import InstallationRate, Product
from services.bot_service import BotService

@pytest.fixture
async def cart_product(db):
    """Seed a product for cart/checkout tests."""
    product = Product(
        title="Cart Test Product",
        slug="cart-test-product",
        price=2000,
        area=35,
        is_published=True
    )
    rate = InstallationRate(
        category="Wall",
        power_range="07-12",
        base_price=250,
        extra_pipe_price=50,
        included_pipe_meters=3,
        is_fixed=True,
    )
    db.add(product)
    db.add(rate)
    await db.commit()
    await db.refresh(product)
    await db.refresh(rate)
    return product, rate

@pytest.mark.asyncio
async def test_checkout_flow(async_client: AsyncClient, cart_product, monkeypatch):
    """
    Test the Checkout flow (Create Order).
    Note: The project uses a client-side cart (Nanostores). 
    There are no /api/v1/cart/add endpoints. 
    The 'Cart' is fully passed to /api/v1/orders at checkout and
    should create a negotiation-stage order, not a raw inbox lead.
    """
    telegram_send = AsyncMock(side_effect=AssertionError("checkout test attempted Telegram delivery"))
    monkeypatch.setattr(BotService, "send_message", telegram_send)

    product, rate = cart_product
    payload = {
        "customer": {
            "name": "Integration Tester",
            "phone": "+375291112233",
            "email": "test@integration.com",
            "address": "Test Street 1",
            "type": "individual"
        },
        "items": [
            {
                "product_id": product.id,
                "quantity": 2,
                "with_installation": True,
                "installation_rate_id": rate.id,
                "installation_price": 250,
                "installation_meta": {"meters": 3},
                "installation_options": []
            }
        ],
        "comment": "Integration test order"
    }
    
    response = await async_client.post("/api/v1/orders", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["status"] == "negotiation"
    
    # Calculate expected total: (Product * 2) + (Install * 2)
    # 2000 * 2 + 250 * 2 = 4000 + 500 = 4500
    expected_total = (product.price * 2) + (250 * 2)
    assert data["total_amount"] == expected_total
    assert "margin" not in data
    assert "total_cost" not in data
    assert "technical_meta" not in data
    assert "cost" not in data
    telegram_send.assert_not_awaited()
