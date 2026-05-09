import pytest
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel import select

from models import BankReceipt, Customer, CustomerType, Order, OrderProposal, OrderStatus, OutgoingEmail, PaymentCurrency, Product, Service
from schemas import ManagerOrderUpdatePayload
from services.order_service import OrderService


@pytest.fixture
async def sqlite_order_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'order_service.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_service_default_order_title_inference():
    assert OrderService._build_default_order_title(service_type="maintenance", comment="что угодно") == "Обслуживание"
    assert OrderService._build_default_order_title(comment="Нужен монтаж с закладкой трассы") == "Монтаж"
    assert OrderService._build_default_order_title(comment="Купить кондиционер") == "Продажа"
    assert OrderService._build_default_order_title(items=[{"product_id": 1, "with_installation": True}]) == "Продажа + монтаж"
    assert OrderService._build_default_order_title(items=[{"product_id": 1}]) == "Продажа"


def test_service_display_order_title_hides_legacy_site_title():
    order = Order(title="Заказ с сайта от 03.05 12:00")
    assert OrderService._display_order_title(order) is None

    order.title = "Монтаж магазина"
    assert OrderService._display_order_title(order) == "Монтаж магазина"


def test_service_json_text_search_variants_include_escaped_cyrillic():
    assert OrderService._json_text_search_variants("адрес") == [
        "адрес",
        "\\u0430\\u0434\\u0440\\u0435\\u0441",
        "\\\\u0430\\\\u0434\\\\u0440\\\\u0435\\\\u0441",
    ]


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
async def test_service_get_orders_for_manager_title_and_labels(db):
    customer = Customer(name="Labels", phone="+375291111112", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    db.add(
        Order(
            customer_id=customer.id,
            status=OrderStatus.NEW_LEAD,
            title="Монтаж магазина в Дубровно",
            technical_meta={"manager_labels": ["срочно", "уточнить оплату"]},
        )
    )
    await db.commit()

    by_title = await OrderService.get_orders_for_manager(db, "b2c", page=1, limit=20, search="Дубровно")
    assert len(by_title["items"]) == 1
    assert by_title["items"][0]["title"] == "Монтаж магазина в Дубровно"
    assert by_title["items"][0]["manager_labels"] == ["срочно", "уточнить оплату"]

    by_label = await OrderService.get_orders_for_manager(db, "b2c", page=1, limit=20, search="оплату")
    assert len(by_label["items"]) == 1


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
async def test_service_update_order_for_manager_title_and_labels(db):
    customer = Customer(name="Meta", phone="+375294444445", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    payload = ManagerOrderUpdatePayload(
        title="  Монтаж   магазина  ",
        manager_labels=[" срочно ", "Срочно", "", "ждём оплату"],
    )

    data = await OrderService.update_order_for_manager(db, order.id, payload)
    assert data is not None
    assert data["title"] == "Монтаж магазина"
    assert data["manager_labels"] == ["срочно", "ждём оплату"]

    cleared = await OrderService.update_order_for_manager(
        db,
        order.id,
        ManagerOrderUpdatePayload(title="", manager_labels=[]),
    )
    assert cleared is not None
    assert cleared["title"] is None
    assert cleared["manager_labels"] == []


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


@pytest.mark.asyncio
async def test_service_delete_order_cleans_proposals_and_detaches_audit_rows(sqlite_order_session):
    db = sqlite_order_session
    customer = Customer(name="Delete", phone="+375296666666", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    proposal = OrderProposal(order_id=order.id, name="Основное", is_selected=True)
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)

    receipt = BankReceipt(
        status="matched",
        operation_type="incoming_funds",
        sender_email="noreply@service.belapb.by",
        subject="Поступление средств на счет",
        message_id="<delete-order-bank@example.test>",
        fingerprint="delete-order-bank-fingerprint",
        amount=100,
        currency=PaymentCurrency.BYN,
        matched_order_id=order.id,
        matched_payment_id=123,
        raw_body="raw",
    )
    email = OutgoingEmail(
        status="sent",
        order_id=order.id,
        customer_id=customer.id,
        recipient_email="client@example.test",
        subject="Документы",
    )
    db.add(receipt)
    db.add(email)
    await db.commit()

    assert await OrderService.delete_order(db, order.id) is True

    assert await db.get(Order, order.id) is None
    assert (await db.execute(select(OrderProposal).where(OrderProposal.id == proposal.id))).scalar_one_or_none() is None

    detached_receipt = (await db.execute(select(BankReceipt).where(BankReceipt.id == receipt.id))).scalar_one()
    assert detached_receipt.status == "requires_review"
    assert detached_receipt.matched_order_id is None
    assert detached_receipt.matched_payment_id is None
    assert detached_receipt.match_meta == {"reason": "matched_order_deleted", "deleted_order_id": order.id}

    detached_email = (await db.execute(select(OutgoingEmail).where(OutgoingEmail.id == email.id))).scalar_one()
    assert detached_email.order_id is None
