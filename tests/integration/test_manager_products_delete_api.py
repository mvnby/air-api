import pytest
from sqlmodel import select

from core.config import settings
from models import (
    Customer,
    CustomerType,
    Order,
    OrderProductLink,
    OrderStatus,
    Product,
    ProductImage,
    TenantOffer,
)
from models.supplier import ProductSupplierMapping, Supplier, SupplierOffer
from services.product_manager_service import (
    PRODUCT_DELETE_FAILED_MESSAGE,
    PRODUCT_DELETE_TENANT_OFFER_MESSAGE,
    ProductManagerService,
)
from services.product_service import ProductService


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
async def test_product_delete_preserves_tenant_offer_for_manager_and_bot_path(
    async_client,
    db,
):
    headers = await _auth_headers(async_client)
    product = Product(
        title="Offered Product",
        slug="offered-product",
        price=2500,
        specs={"area_m2": 15},
    )
    db.add(product)
    await db.flush()
    offer = TenantOffer(
        tenant_id=1,
        storefront_id=1,
        product_id=int(product.id),
        price=2600,
        is_published=True,
        created_by_username="delete-test",
        updated_by_username="delete-test",
    )
    db.add(offer)
    await db.commit()
    product_id = int(product.id)
    offer_id = int(offer.id)

    response = await async_client.delete(
        f"/api/manager/products/{product_id}",
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == (
        PRODUCT_DELETE_TENANT_OFFER_MESSAGE
    )

    # ProductService.delete is the compatibility path used by the Telegram bot.
    with pytest.raises(ValueError, match="предложениях витрин"):
        await ProductService.delete(db, product_id)

    assert await db.get(Product, product_id) is not None
    assert await db.get(TenantOffer, offer_id) is not None


@pytest.mark.asyncio
async def test_manager_bulk_delete_reports_deleted_and_blocked_products(async_client, db):
    headers = await _auth_headers(async_client)
    customer = Customer(tenant_id=1, name="Bulk Prod Customer", phone="+375291000001", type=CustomerType.individual)
    deletable = Product(title="Bulk Clean Product", slug="bulk-clean-product", price=2500, specs={"area_m2": 15})
    blocked = Product(title="Bulk Used Product", slug="bulk-used-product", price=3000, specs={"area_m2": 20})
    offered = Product(
        title="Bulk Offered Product",
        slug="bulk-offered-product",
        price=2800,
        specs={"area_m2": 18},
    )
    db.add_all([customer, deletable, blocked, offered])
    await db.commit()
    await db.refresh(customer)
    await db.refresh(deletable)
    await db.refresh(blocked)
    await db.refresh(offered)

    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add_all(
        [
            OrderProductLink(
                order_id=order.id,
                product_id=blocked.id,
                quantity=1,
                price=3000,
                cost=1800,
            ),
            TenantOffer(
                tenant_id=1,
                storefront_id=1,
                product_id=int(offered.id),
                price=2900,
                is_published=True,
                created_by_username="bulk-delete-test",
                updated_by_username="bulk-delete-test",
            ),
        ]
    )
    await db.commit()

    resp = await async_client.post(
        "/api/manager/products/bulk-delete",
        headers=headers,
        json={"product_ids": [deletable.id, blocked.id, offered.id, 999999]},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["deleted_count"] == 1
    assert payload["failed_count"] == 3
    assert {item["product_id"] for item in payload["errors"]} == {
        blocked.id,
        offered.id,
        999999,
    }
    offered_error = next(
        item for item in payload["errors"] if item["product_id"] == offered.id
    )
    assert offered_error["message"] == PRODUCT_DELETE_TENANT_OFFER_MESSAGE

    assert await db.get(Product, deletable.id) is None
    assert await db.get(Product, blocked.id) is not None
    assert await db.get(Product, offered.id) is not None


@pytest.mark.asyncio
async def test_manager_bulk_delete_redacts_unexpected_database_details(monkeypatch):
    class FakeSession:
        rolled_back = False

        async def rollback(self):
            self.rolled_back = True

    async def fail_delete(_session, _product_id):
        raise RuntimeError("sensitive SQL constraint detail")

    monkeypatch.setattr(ProductManagerService, "delete_for_manager", fail_delete)
    session = FakeSession()

    result = await ProductManagerService.bulk_delete_for_manager(session, [42])

    assert session.rolled_back is True
    assert result["failed_count"] == 1
    assert result["errors"] == [
        {"product_id": 42, "message": PRODUCT_DELETE_FAILED_MESSAGE}
    ]
    assert "SQL" not in result["errors"][0]["message"]


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
