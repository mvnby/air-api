import pytest

from models import Customer, CustomerType, Order, OrderStatus
from services.customer_service import CustomerService


@pytest.mark.asyncio
async def test_list_for_manager_defaults_to_only_with_orders(db):
    customer_with_order = Customer(name="With Order", phone="+375291000001", type=CustomerType.individual)
    customer_without_order = Customer(name="No Order", phone="+375291000002", type=CustomerType.individual)
    db.add(customer_with_order)
    db.add(customer_without_order)
    await db.commit()
    await db.refresh(customer_with_order)
    await db.refresh(customer_without_order)

    db.add(Order(customer_id=customer_with_order.id, status=OrderStatus.NEW_LEAD))
    await db.commit()

    result_default = await CustomerService.list_for_manager(db, page=1, limit=20)
    ids_default = {item["id"] for item in result_default["items"]}
    assert customer_with_order.id in ids_default
    assert customer_without_order.id not in ids_default

    result_all = await CustomerService.list_for_manager(db, page=1, limit=20, only_with_orders=False)
    ids_all = {item["id"] for item in result_all["items"]}
    assert customer_with_order.id in ids_all
    assert customer_without_order.id in ids_all
