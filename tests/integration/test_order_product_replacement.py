import pytest

from core.config import settings
from models import Customer, Order, OrderProductLink, OrderStatus, Product
from services.order_product_description import product_line_document_title


@pytest.mark.asyncio
@pytest.mark.parametrize("description", [None, "  Новая модель: серебристый корпус  "])
async def test_product_replacement_drops_previous_model_snapshot(async_client, db, description):
    customer = Customer(tenant_id=1, name="Замена товара", phone="+375291113333")
    old_product = Product(title="Прежняя модель", slug="replacement-old", price=1000)
    new_product = Product(title="Новая модель", slug="replacement-new", price=2000)
    db.add_all([customer, old_product, new_product])
    await db.commit()
    order = Order(
        tenant_id=1, storefront_id=1, customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
    )
    db.add(order)
    await db.commit()
    line = OrderProductLink(
        order_id=order.id, product_id=old_product.id, quantity=1,
        price=1000, cost=500, title_snapshot="Прежняя модель при покупке",
        client_description="Старая модель: белый корпус",
    )
    db.add(line)
    await db.commit()

    login = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    product_payload = {
        "link_id": line.id, "product_id": new_product.id,
        "quantity": 2, "price": 2100, "cost": 1200,
    }
    if description is not None:
        product_payload["client_description"] = description

    saved = await async_client.patch(
        f"/api/manager/orders/{order.id}", json={"products": [product_payload]}, headers=headers,
    )
    assert saved.status_code == 200, saved.text
    reopened = await async_client.get(f"/api/manager/orders/{order.id}", headers=headers)
    assert reopened.status_code == 200
    actual = reopened.json()["product_lines"][0]
    assert actual["id"] == line.id
    assert actual["product_id"] == new_product.id
    assert actual["product_title"] == new_product.title
    assert actual["title_snapshot"] is None
    expected_description = description.strip() if description is not None else None
    assert actual["client_description"] == expected_description
    assert actual["quantity"] == 2
    assert actual["price"] == 2100

    await db.refresh(line)
    await db.refresh(line, attribute_names=["product"])
    expected_title = new_product.title
    if expected_description:
        expected_title += "\n" + expected_description
    assert product_line_document_title(line) == expected_title
