from decimal import Decimal

import pytest

from models import GlobalConfig, Order, OrderProductLink, OrderStatus, Product
from models.supplier import ProductSupplierMapping, Supplier, SupplierOffer
from services.supply_request_service import SupplierProfileService, SupplyRequestService


async def _seed_supplier_product(db):
    product = Product(title="MDV Iera 09", slug="mdv-iera-09-supply", price=2100, area=25)
    supplier_a = Supplier(
        name="Оптконд",
        code="supply-optkond",
        priority=1,
        default_payment_method="bank",
    )
    supplier_b = Supplier(
        name="Наличный склад",
        code="supply-cash-stock",
        priority=2,
        default_payment_method="cash",
    )
    db.add_all([
        product,
        supplier_a,
        supplier_b,
        GlobalConfig(key="fx_rate_usd_byn", value="3.2", description="fx"),
        GlobalConfig(key="fx_supplier_markup_percent", value="0", description="test"),
    ])
    await db.commit()
    await db.refresh(product)
    await db.refresh(supplier_a)
    await db.refresh(supplier_b)

    order = Order(status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    order_line = OrderProductLink(
        order_id=order.id,
        product_id=product.id,
        quantity=2,
        price=2100,
        cost=1200,
    )
    db.add(order_line)

    db.add_all([
        SupplierOffer(
            supplier_id=supplier_a.id,
            external_id="A-low-no-stock",
            title_raw="MDV Iera 09 без наличия",
            qty=0,
            wholesale_value=Decimal("900"),
            wholesale_currency="BYN",
            is_active=True,
        ),
        SupplierOffer(
            supplier_id=supplier_a.id,
            external_id="A-best",
            title_raw="MDV Iera 09 склад",
            qty=3,
            wholesale_value=Decimal("1000"),
            wholesale_currency="BYN",
            is_active=True,
        ),
        SupplierOffer(
            supplier_id=supplier_b.id,
            external_id="B-usd",
            title_raw="MDV Iera 09 USD",
            qty=5,
            wholesale_value=Decimal("400"),
            wholesale_currency="USD",
            is_active=True,
        ),
        ProductSupplierMapping(product_id=product.id, supplier_id=supplier_a.id, external_id="A-low-no-stock"),
        ProductSupplierMapping(product_id=product.id, supplier_id=supplier_a.id, external_id="A-best"),
        ProductSupplierMapping(product_id=product.id, supplier_id=supplier_b.id, external_id="B-usd"),
    ])
    await db.commit()
    await db.refresh(order_line)
    return product, supplier_a, supplier_b, order, order_line


@pytest.mark.asyncio
async def test_supplier_contacts_and_warehouses_crud_defaults(db):
    supplier = Supplier(name="Биоконд", code="supply-biokond", default_payment_method="mixed")
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    first = await SupplierProfileService.create_contact(
        db,
        supplier.id,
        {"name": "Анна", "phone": "+375 29", "default_for_orders": True},
    )
    second = await SupplierProfileService.create_contact(
        db,
        supplier.id,
        {"name": "Склад", "phone": "+375 33", "default_for_orders": True, "default_for_logistics": True},
    )
    contacts = (await SupplierProfileService.list_contacts(db, supplier.id))["items"]
    refreshed_first = next(item for item in contacts if item.id == first.id)
    refreshed_second = next(item for item in contacts if item.id == second.id)
    assert refreshed_first.default_for_orders is False
    assert refreshed_second.default_for_orders is True
    assert refreshed_second.default_for_logistics is True

    warehouse = await SupplierProfileService.create_warehouse(
        db,
        supplier.id,
        {
            "name": "Центральный склад",
            "address": "Минск, Складская, 1",
            "contact_id": second.id,
            "is_default": True,
        },
    )
    warehouses = (await SupplierProfileService.list_warehouses(db, supplier.id))["items"]
    assert warehouses[0].id == warehouse.id
    assert warehouses[0].address == "Минск, Складская, 1"


@pytest.mark.asyncio
async def test_create_supply_request_from_order_lines_selects_available_min_cost_offer(db):
    _product, supplier_a, _supplier_b, order, order_line = await _seed_supplier_product(db)
    await SupplierProfileService.create_warehouse(
        db,
        supplier_a.id,
        {"name": "Оптконд склад", "address": "Минск, адрес склада", "is_default": True},
    )
    await SupplierProfileService.create_contact(
        db,
        supplier_a.id,
        {"name": "Менеджер", "phone": "123", "default_for_orders": True},
    )

    result = await SupplyRequestService.create_from_order_lines(
        db,
        {"order_product_link_ids": [order_line.id], "intent": "order"},
        created_by="pytest",
    )

    request = result["items"][0]
    assert request["supplier_id"] == supplier_a.id
    assert request["payment_method"] == "bank"
    assert request["warehouse_name"] == "Оптконд склад"
    assert request["supplier_contact_name"] == "Менеджер"
    assert request["lines"][0]["order_product_link_id"] == order_line.id
    assert request["lines"][0]["supplier_offer_external_id"] == "A-best"
    assert request["lines"][0]["unit_cost_snapshot"] == 1000.0
    assert request["lines"][0]["qty"] == 2
    assert order.id is not None


@pytest.mark.asyncio
async def test_create_stock_request_and_generate_messages(db):
    product, supplier_a, _supplier_b, _order, _order_line = await _seed_supplier_product(db)
    warehouse = await SupplierProfileService.create_warehouse(
        db,
        supplier_a.id,
        {
            "name": "Склад A",
            "address": "Витебск, склад 1",
            "contact_name": "Кладовщик",
            "contact_phone": "+375 44",
            "work_hours": "9-18",
            "is_default": True,
        },
    )

    result = await SupplyRequestService.create_stock_requests(
        db,
        {
            "intent": "reserve",
            "comment": "на склад",
            "lines": [
                {
                    "supplier_id": supplier_a.id,
                    "warehouse_id": warehouse.id,
                    "product_id": product.id,
                    "qty": 1,
                    "payment_method": "cash",
                }
            ],
        },
    )
    request = result["items"][0]
    assert request["intent"] == "reserve"
    assert request["payment_method"] == "cash"
    assert request["lines"][0]["source_type"] == "stock"
    assert request["lines"][0]["supplier_offer_external_id"] == "A-best"

    supplier_message = await SupplyRequestService.generate_supplier_message(db, request["id"], mark_sent=True)
    assert "забронируйте" in supplier_message["text"]
    assert "MDV Iera 09" in supplier_message["text"]
    updated = await SupplyRequestService.get_request(db, request["id"])
    assert updated["status"] == "awaiting_reply"

    logistics_message = await SupplyRequestService.generate_logistics_message(db, [request["id"]], mark_sent=True)
    assert "Витебск, склад 1" in logistics_message["text"]
    assert "Кладовщик" in logistics_message["text"]
    updated = await SupplyRequestService.get_request(db, request["id"])
    assert updated["status"] == "ready_for_pickup"


@pytest.mark.asyncio
async def test_supply_status_transitions_and_partial_receipt(db):
    _product, supplier_a, _supplier_b, _order, order_line = await _seed_supplier_product(db)
    result = await SupplyRequestService.create_from_order_lines(
        db,
        {"order_product_link_ids": [order_line.id], "intent": "order"},
    )
    request = result["items"][0]
    line = request["lines"][0]

    ordered = await SupplyRequestService.update_request(db, request["id"], {"status": "ordered"})
    assert ordered["status"] == "ordered"
    assert ordered["lines"][0]["status"] == "ordered"

    partial = await SupplyRequestService.update_line(db, line["id"], {"received_qty": 1})
    assert partial["status"] == "ordered"
    assert partial["lines"][0]["received_qty"] == 1

    received = await SupplyRequestService.update_line(db, line["id"], {"received_qty": 2})
    assert received["status"] == "received"
    assert received["lines"][0]["status"] == "received"
