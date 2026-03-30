import pytest
from datetime import datetime, timedelta
from sqlmodel import select

from core.config import settings
from models import (
    Customer,
    CustomerType,
    Installer,
    Order,
    OrderDocument,
    OrderInstaller,
    OrderProductLink,
    OrderServiceLink,
    OrderStatus,
    Payment,
    Product,
    Service,
)
from models.order import OrderWorkStage


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

    async def _fake_create_or_get_document(session, order_id, doc_type, template_id=None):
        _ = (session, order_id, doc_type, template_id)
        return _FakeDoc()

    from services import document_service

    monkeypatch.setattr(document_service.DocumentService, "create_or_get_document", _fake_create_or_get_document)

    headers = await _auth_headers(async_client)
    response = await async_client.post(f"/api/manager/orders/{order.id}/documents/contract", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["doc_type"] == "contract"
    assert data["edit_url"].startswith("https://docs.google.com")


@pytest.mark.asyncio
async def test_manager_order_patch_customer_critical_requisites_requires_confirmation(async_client, db):
    customer = Customer(
        name="Critical Requisites",
        phone="+375299999999",
        type=CustomerType.company,
        inn="123456789",
        iban="BY12ALFA30120000000000000000",
        bic="ALFABY2X",
        bank_name="Альфа-Банк",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    headers = await _auth_headers(async_client)
    payload = {
        "customer_iban": "BY88ALFA30120000000000000000",
        "customer_bic": "ALFABY2Y",
        "customer_bank_name": "Новый Банк",
    }

    without_confirm = await async_client.patch(f"/api/manager/orders/{order.id}", json=payload, headers=headers)
    assert without_confirm.status_code == 400
    assert "requires confirmation" in str(without_confirm.json()["detail"]).lower()

    with_confirm = await async_client.patch(
        f"/api/manager/orders/{order.id}",
        json={**payload, "confirm_critical_customer_changes": True},
        headers=headers,
    )
    assert with_confirm.status_code == 200
    data = with_confirm.json()
    assert data["customer"]["iban"] == payload["customer_iban"]
    assert data["customer"]["bic"] == payload["customer_bic"]
    assert data["customer"]["bank_name"] == payload["customer_bank_name"]


@pytest.mark.asyncio
async def test_manager_order_list_documents(async_client, db):
    customer = Customer(name="DocList", phone="+375298888888", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    
    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    from models import OrderDocument
    doc1 = OrderDocument(
        order_id=order.id, 
        doc_type="contract", 
        number="D-001", 
        google_file_id="fid1", 
        google_edit_url="http://edit1"
    )
    doc2 = OrderDocument(
        order_id=order.id, 
        doc_type="invoice", 
        number="I-001", 
        google_file_id="fid2", 
        google_edit_url="http://edit2"
    )
    db.add(doc1)
    db.add(doc2)
    await db.commit()
    
    headers = await _auth_headers(async_client)
    resp = await async_client.get(f"/api/manager/orders/{order.id}/documents", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert {i["doc_type"] for i in items} == {"contract", "invoice"}


@pytest.mark.asyncio
async def test_manager_doc_download_404(async_client, db):
    headers = await _auth_headers(async_client)
    resp = await async_client.get("/api/manager/docs/999999/download", headers=headers)
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"]["error_code"] == "document_not_found"


@pytest.mark.asyncio
async def test_manager_doc_delete_success(async_client, db, monkeypatch):
    customer = Customer(name="DocDel", phone="+375290000000", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    
    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    from models import OrderDocument
    doc = OrderDocument(
        order_id=order.id, 
        doc_type="act", 
        number="A-001", 
        google_file_id="fid_del", 
        google_edit_url="http://edit_del"
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    doc_id = doc.id
    
    # Mock google service delete
    from services.google_service import get_google_service
    deleted_ids = []
    def _fake_delete_file(file_id):
        deleted_ids.append(file_id)
        
    monkeypatch.setattr(get_google_service(), "delete_file", _fake_delete_file)
    
    headers = await _auth_headers(async_client)
    resp = await async_client.delete(f"/api/manager/docs/{doc_id}", headers=headers)
    assert resp.status_code == 200
    
    # Verify DB
    from sqlmodel import select
    res = await db.execute(select(OrderDocument).where(OrderDocument.id == doc_id))
    assert res.scalar_one_or_none() is None
    
    # Verify Google Call
    assert "fid_del" in deleted_ids


@pytest.mark.asyncio
async def test_manager_order_delete_cascades_related_entities(async_client, db, monkeypatch):
    customer = Customer(name="Delete Order", phone="+375290001234", type=CustomerType.individual)
    product = Product(title="Delete Product", slug="delete-product", price=4000, area=35)
    service = Service(title="Delete Service", slug="delete-service", base_price=200)
    installer = Installer(name="Delete Installer", is_active=True)
    db.add(customer)
    db.add(product)
    db.add(service)
    db.add(installer)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)
    await db.refresh(service)
    await db.refresh(installer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD, delivery_address="Минск")
    db.add(order)
    await db.commit()
    await db.refresh(order)

    db.add(OrderProductLink(order_id=order.id, product_id=product.id, quantity=1, price=4000, cost=2500))
    db.add(OrderServiceLink(order_id=order.id, service_id=service.id, title=service.title, quantity=1, price=200, cost=80))
    db.add(OrderInstaller(order_id=order.id, installer_id=installer.id, role="main", agreed_pay=100))
    db.add(OrderWorkStage(order_id=order.id, name="Монтаж"))
    db.add(Payment(order_id=order.id, amount=500))
    db.add(
        OrderDocument(
            order_id=order.id,
            doc_type="contract",
            number="D-DELETE-1",
            google_file_id="google-file-delete-1",
            google_edit_url="https://docs.google.com/fake",
        )
    )
    await db.commit()

    from services.google_service import get_google_service

    deleted_ids = []

    def _fake_delete_file(file_id):
        deleted_ids.append(file_id)

    monkeypatch.setattr(get_google_service(), "delete_file", _fake_delete_file)

    headers = await _auth_headers(async_client)
    resp = await async_client.delete(f"/api/manager/orders/{order.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    assert await db.get(Order, order.id) is None

    plinks = await db.execute(select(OrderProductLink).where(OrderProductLink.order_id == order.id))
    assert plinks.scalars().first() is None
    slinks = await db.execute(select(OrderServiceLink).where(OrderServiceLink.order_id == order.id))
    assert slinks.scalars().first() is None
    installers = await db.execute(select(OrderInstaller).where(OrderInstaller.order_id == order.id))
    assert installers.scalars().first() is None
    stages = await db.execute(select(OrderWorkStage).where(OrderWorkStage.order_id == order.id))
    assert stages.scalars().first() is None
    payments = await db.execute(select(Payment).where(Payment.order_id == order.id))
    assert payments.scalars().first() is None
    docs = await db.execute(select(OrderDocument).where(OrderDocument.order_id == order.id))
    assert docs.scalars().first() is None
    assert "google-file-delete-1" in deleted_ids
