import pytest
from sqlmodel import select

from core.config import settings
from models import Customer, CustomerType, Order, OrderProductLink, OrderStatus, Product, ProductImage
from models.supplier import ProductSupplierMapping, Supplier, SupplierOffer


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
    customer = Customer(tenant_id=1, name="Prod Customer", phone="+375291000000", type=CustomerType.individual)
    product = Product(title="Used Product", slug="used-product", price=3000, specs={"area_m2": 20})
    db.add(customer)
    db.add(product)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)

    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.NEW_LEAD)
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
    product = Product(title="Clean Product", slug="clean-product", price=2500, specs={"area_m2": 15})
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


@pytest.mark.asyncio
async def test_manager_bulk_delete_reports_deleted_and_blocked_products(async_client, db):
    headers = await _auth_headers(async_client)
    customer = Customer(tenant_id=1, name="Bulk Prod Customer", phone="+375291000001", type=CustomerType.individual)
    deletable = Product(title="Bulk Clean Product", slug="bulk-clean-product", price=2500, specs={"area_m2": 15})
    blocked = Product(title="Bulk Used Product", slug="bulk-used-product", price=3000, specs={"area_m2": 20})
    db.add_all([customer, deletable, blocked])
    await db.commit()
    await db.refresh(customer)
    await db.refresh(deletable)
    await db.refresh(blocked)

    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add(OrderProductLink(order_id=order.id, product_id=blocked.id, quantity=1, price=3000, cost=1800))
    await db.commit()

    resp = await async_client.post(
        "/api/manager/products/bulk-delete",
        headers=headers,
        json={"product_ids": [deletable.id, blocked.id, 999999]},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["deleted_count"] == 1
    assert payload["failed_count"] == 2
    assert {item["product_id"] for item in payload["errors"]} == {blocked.id, 999999}

    assert await db.get(Product, deletable.id) is None
    assert await db.get(Product, blocked.id) is not None


@pytest.mark.asyncio
async def test_manager_bulk_set_rrc_price_updates_only_products_with_rrc(async_client, db):
    headers = await _auth_headers(async_client)
    with_rrc = Product(title="Bulk RRC Product", slug="bulk-rrc-product", price=2100, specs={"area_m2": 20})
    without_rrc = Product(title="Bulk No RRC Product", slug="bulk-no-rrc-product", price=1900, specs={"area_m2": 20})
    already_rrc = Product(title="Bulk Already RRC Product", slug="bulk-already-rrc-product", price=2700, specs={"area_m2": 20})
    supplier = Supplier(name="Bulk RRC Supplier", code="bulk-rrc-supplier", priority=1)
    db.add_all([with_rrc, without_rrc, already_rrc, supplier])
    await db.commit()
    for row in [with_rrc, without_rrc, already_rrc, supplier]:
        await db.refresh(row)

    db.add_all(
        [
            SupplierOffer(supplier_id=supplier.id, external_id="rrc-1", qty=1, rrc_byn=2555, is_active=True),
            SupplierOffer(supplier_id=supplier.id, external_id="rrc-2", qty=1, rrc_byn=2700, is_active=True),
            ProductSupplierMapping(product_id=with_rrc.id, supplier_id=supplier.id, external_id="rrc-1", is_active=True),
            ProductSupplierMapping(product_id=already_rrc.id, supplier_id=supplier.id, external_id="rrc-2", is_active=True),
        ]
    )
    await db.commit()

    resp = await async_client.post(
        "/api/manager/products/bulk-set-rrc-price",
        headers=headers,
        json={"product_ids": [with_rrc.id, without_rrc.id, already_rrc.id]},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["processed_count"] == 3
    assert payload["updated_count"] == 1
    assert payload["skipped_count"] == 2

    await db.refresh(with_rrc)
    await db.refresh(without_rrc)
    await db.refresh(already_rrc)
    assert with_rrc.price == 2555
    assert without_rrc.price == 1900
    assert already_rrc.price == 2700
