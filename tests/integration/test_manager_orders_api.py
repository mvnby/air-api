import pytest
from datetime import datetime, timedelta

from core.config import settings
from models import (
    Customer,
    CustomerType,
    Installer,
    Order,
    OrderInstaller,
    OrderProductLink,
    OrderServiceLink,
    OrderStatus,
    Product,
    Service,
)


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_orders_list_segment_filter(async_client, db):
    c1 = Customer(name="B2C", phone="+375291111111", type=CustomerType.individual)
    c2 = Customer(name="B2B", phone="+375292222222", type=CustomerType.individual, inn="123456789")
    db.add(c1)
    db.add(c2)
    await db.commit()
    await db.refresh(c1)
    await db.refresh(c2)

    db.add(Order(customer_id=c1.id, status=OrderStatus.NEW_LEAD, total_amount=100))
    db.add(Order(customer_id=c2.id, status=OrderStatus.NEW_LEAD, total_amount=200))
    db.add(Order(customer_id=None, status=OrderStatus.NEW_LEAD, total_amount=50))
    await db.commit()

    headers = await _auth_headers(async_client)

    r_b2c = await async_client.get("/api/manager/orders?segment=b2c", headers=headers)
    assert r_b2c.status_code == 200
    b2c_items = r_b2c.json()["items"]
    assert any(item["customer"] is None for item in b2c_items)
    assert all((item["customer"] is None) or (item["customer"]["inn"] in (None, "")) for item in b2c_items)

    r_b2b = await async_client.get("/api/manager/orders?segment=b2b", headers=headers)
    assert r_b2b.status_code == 200
    b2b_items = r_b2b.json()["items"]
    assert len(b2b_items) == 1
    assert b2b_items[0]["customer"]["inn"] == "123456789"


@pytest.mark.asyncio
async def test_manager_orders_overdue_filter(async_client, db):
    customer = Customer(name="Overdue", phone="+375293333333", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            next_followup_date=datetime.now() - timedelta(days=1),
        )
    )
    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            next_followup_date=datetime.now() + timedelta(days=1),
        )
    )
    await db.commit()

    headers = await _auth_headers(async_client)
    response = await async_client.get(
        "/api/manager/orders?segment=b2c&overdue_only=true",
        headers=headers,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1


@pytest.mark.asyncio
async def test_manager_order_detail_uses_snapshot_prices(async_client, db):
    customer = Customer(name="Snapshot", phone="+375294444444", type=CustomerType.individual)
    product = Product(title="Snapshot Product", slug="snapshot-product", price=5000, area=30)
    db.add(customer)
    db.add(product)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add(
        OrderProductLink(
            order_id=order.id,
            product_id=product.id,
            quantity=2,
            price=1200,
            cost=700,
            installation_price=0,
            is_installation_included=False,
        )
    )
    await db.commit()

    product.price = 9100
    db.add(product)
    await db.commit()

    # Expunge the order from the session's identity map so the endpoint's
    # selectinload creates a fresh instance with up-to-date product_links.
    db.expunge(order)

    headers = await _auth_headers(async_client)
    response = await async_client.get(f"/api/manager/orders/{order.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["product_lines"][0]["price"] == 1200


@pytest.mark.asyncio
async def test_manager_order_patch_scalar_fields(async_client, db):
    customer = Customer(name="Patch", phone="+375295555555", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD, is_paid=False)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    payload = {
        "status": "negotiation",
        "comment": "updated from manager",
        "is_paid": True,
    }
    response = await async_client.patch(f"/api/manager/orders/{order.id}", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "negotiation"
    assert data["comment"] == "updated from manager"
    assert data["is_paid"] is True


@pytest.mark.asyncio
async def test_manager_order_patch_lines_preserves_installers(async_client, db):
    customer = Customer(name="Lines", phone="+375296666666", type=CustomerType.individual)
    product = Product(title="P", slug="prod-p", price=3000, area=30)
    service = Service(title="S", slug="service-s", base_price=100)
    installer = Installer(name="Installer 1", is_active=True)
    db.add(customer)
    db.add(product)
    db.add(service)
    db.add(installer)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)
    await db.refresh(service)
    await db.refresh(installer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=3000, cost=2000))
    db.add(OrderServiceLink(order_id=order.id, service_id=service.id, title=service.title, quantity=1, price=100, cost=50))
    db.add(OrderInstaller(order_id=order.id, installer_id=installer.id, role="main", agreed_pay=100))
    await db.commit()

    headers = await _auth_headers(async_client)
    payload = {
        "products": [{"product_id": product.id, "quantity": 2, "price": 1500, "cost": 1000}],
        "services": [{"service_id": service.id, "title": "S2", "quantity": 1, "price": 200, "cost": 80}],
    }
    response = await async_client.patch(f"/api/manager/orders/{order.id}", json=payload, headers=headers)
    assert response.status_code == 200

    await db.refresh(order, attribute_names=["installers"])
    assert len(order.installers) == 1


@pytest.mark.asyncio
async def test_manager_order_patch_validation_errors(async_client, db):
    customer = Customer(name="Validation", phone="+375299999999", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    payload = {
        "products": [{"product_id": 1, "quantity": 0, "price": 100, "cost": 10}],
    }
    response = await async_client.patch(f"/api/manager/orders/{order.id}", json=payload, headers=headers)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_code"] == "bad_request"
    assert detail["message"] == "Product quantity must be > 0"


@pytest.mark.asyncio
async def test_manager_order_generate_document(async_client, db, monkeypatch):
    customer = Customer(name="Doc", phone="+375297777777", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    class _FakeDoc:
        id = 1
        doc_type = "contract"
        google_edit_url = "https://docs.google.com/fake"

    async def _fake_create_or_get_document(session, order_id, doc_type):
        _ = (session, order_id, doc_type)
        return _FakeDoc()

    from services import document_service

    monkeypatch.setattr(document_service.DocumentService, "create_or_get_document", _fake_create_or_get_document)

    headers = await _auth_headers(async_client)
    response = await async_client.post(f"/api/manager/orders/{order.id}/documents/contract", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["doc_type"] == "contract"
    assert data["edit_url"].startswith("https://docs.google.com")
