import pytest
from httpx import AsyncClient
from models import Product

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
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product

@pytest.mark.asyncio
async def test_checkout_flow(async_client: AsyncClient, cart_product):
    """
    Test the Checkout flow (Create Order).
    Note: The project uses a client-side cart (Nanostores). 
    There are no /api/v1/cart/add endpoints. 
    The 'Cart' is fully passed to /api/v1/orders at checkout and
    should create a negotiation-stage order, not a raw inbox lead.
    """
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
                "product_id": cart_product.id,
                "quantity": 2,
                "with_installation": True,
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
    expected_total = (cart_product.price * 2) + (250 * 2)
    assert data["total_amount"] == expected_total
    assert "margin" not in data
    assert "total_cost" not in data
    assert "technical_meta" not in data
    assert "cost" not in data
