import pytest
from datetime import datetime, timedelta

from models import Customer, CustomerType, Order, OrderStatus, Product, Service
from schemas import ManagerOrderUpdatePayload
from services.order_service import OrderService


@pytest.mark.asyncio
async def test_service_get_orders_for_manager_segment_and_search(db):
    c1 = Customer(name="Alice", phone="+375291111111", type=CustomerType.individual)
    c2 = Customer(name="Acme LLC", phone="+375292222222", type=CustomerType.individual, inn="999000111")
    db.add(c1)
    db.add(c2)
    await db.commit()
    await db.refresh(c1)
    await db.refresh(c2)

    db.add(Order(customer_id=c1.id, status=OrderStatus.NEW_LEAD, comment="note 1"))
    db.add(Order(customer_id=c2.id, status=OrderStatus.NEW_LEAD, comment="note 2"))
    await db.commit()

    b2c = await OrderService.get_orders_for_manager(db, "b2c", page=1, limit=20)
    assert len(b2c["items"]) == 1
    assert b2c["items"][0]["customer"]["name"] == "Alice"

    b2b = await OrderService.get_orders_for_manager(db, "b2b", page=1, limit=20, search="999000111")
    assert len(b2b["items"]) == 1
    assert b2b["items"][0]["customer"]["name"] == "Acme LLC"


@pytest.mark.asyncio
async def test_service_get_orders_for_manager_b2c_includes_legacy_without_customer(db):
    db.add(Order(customer_id=None, status=OrderStatus.NEW_LEAD, comment="legacy"))
    await db.commit()

    b2c = await OrderService.get_orders_for_manager(db, "b2c", page=1, limit=20)
    assert len(b2c["items"]) == 1
    assert b2c["items"][0]["customer"] is None

    b2b = await OrderService.get_orders_for_manager(db, "b2b", page=1, limit=20)
    assert len(b2b["items"]) == 0


@pytest.mark.asyncio
async def test_service_get_orders_for_manager_overdue_filter(db):
    customer = Customer(name="Over", phone="+375293333333", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    db.add(Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD, next_followup_date=datetime.now() - timedelta(days=1)))
    db.add(Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD, next_followup_date=datetime.now() + timedelta(days=1)))
    await db.commit()

    result = await OrderService.get_orders_for_manager(db, "b2c", page=1, limit=20, overdue_only=True)
    assert len(result["items"]) == 1


@pytest.mark.asyncio
async def test_service_update_order_for_manager_line_sync(db):
    customer = Customer(name="Edit", phone="+375294444444", type=CustomerType.individual)
    product = Product(title="T1", slug="t1", price=1000, area=20)
    service = Service(title="Srv", slug="srv", base_price=150)
    db.add(customer)
    db.add(product)
    db.add(service)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(product)
    await db.refresh(service)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    payload = ManagerOrderUpdatePayload(
        status="negotiation",
        products=[{"product_id": product.id, "quantity": 2, "price": 1300, "cost": 700}],
        services=[{"service_id": service.id, "title": "Srv", "quantity": 1, "price": 200, "cost": 50}],
    )

    data = await OrderService.update_order_for_manager(db, order.id, payload)
    assert data is not None
    assert data["status"] == "negotiation"
    assert len(data["product_lines"]) == 1
    assert data["total_amount"] == 2800


@pytest.mark.asyncio
async def test_service_update_order_for_manager_validation(db):
    customer = Customer(name="Validation", phone="+375295555555", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    with pytest.raises(ValueError):
        await OrderService.update_order_for_manager(db, order.id, ManagerOrderUpdatePayload(status="bad_status"))

    with pytest.raises(ValueError):
        await OrderService.update_order_for_manager(
            db,
            order.id,
            ManagerOrderUpdatePayload(products=[{"product_id": 1, "quantity": 1, "price": -1}]),
        )
