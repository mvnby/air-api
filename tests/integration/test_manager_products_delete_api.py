import pytest
from sqlmodel import select

from core.config import settings
from models import Customer, CustomerType, Order, OrderProductLink, OrderStatus, Product, ProductImage


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_product_delete_blocked_if_used_in_orders(async_client, db):
    headers = await _auth_headers(async_client)
    customer = Customer(name="Prod Customer", phone="+375291000000", type=CustomerType.individual)
    product = Product(title="Used Product", slug="used-product", price=3000, area=20)
    db.add(customer)
    db.add(product)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=3000, cost=1800))
    await db.commit()

    resp = await async_client.delete(f"/api/manager/products/{product.id}", headers=headers)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error_code"] == "bad_request"
    assert detail["message"] == "Товар используется в заказах. Снимите его с публикации вместо удаления."

    still_exists = await db.get(Product, product.id)
    assert still_exists is not None


@pytest.mark.asyncio
async def test_manager_product_delete_success_when_unlinked(async_client, db):
    headers = await _auth_headers(async_client)
    product = Product(title="Clean Product", slug="clean-product", price=2500, area=15)
    db.add(product)
    await db.commit()
    await db.refresh(product)

    db.add(ProductImage(product_id=product.id, url="https://example.com/p1.jpg"))
    db.add(ProductImage(product_id=product.id, url="https://example.com/p2.jpg"))
    await db.commit()

    resp = await async_client.delete(f"/api/manager/products/{product.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    p_result = await db.execute(select(Product).where(Product.id == product.id))
    assert p_result.scalar_one_or_none() is None
    img_result = await db.execute(select(ProductImage).where(ProductImage.product_id == product.id))
    assert img_result.scalars().first() is None
