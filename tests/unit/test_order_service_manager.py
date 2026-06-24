import pytest
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel import select

from models import (
    BankReceipt,
    Customer,
    CustomerType,
    Installer,
    Order,
    OrderWorkStage,
    OrderProposal,
    OrderStageStatus,
    OrderStatus,
    OutgoingEmail,
    PaymentCurrency,
    Product,
    Service,
    ServiceTariff,
)
from schemas import ManagerOrderUpdatePayload, OrderWorkStageCreatePayload, OrderWorkStageUpdatePayload
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


@pytest.mark.asyncio
async def test_service_lists_cancels_and_deletes_stale_work_stages(sqlite_order_session):
    installer = Installer(name="Монтажник")
    customer = Customer(name="Иван", phone="+375291234567")
    sqlite_order_session.add(installer)
    sqlite_order_session.add(customer)
    await sqlite_order_session.commit()
    await sqlite_order_session.refresh(installer)
    await sqlite_order_session.refresh(customer)

    order = Order(
        customer_id=customer.id,
        status=OrderStatus.EXECUTION,
        title="Монтаж",
        delivery_address="Победы 15",
    )
    sqlite_order_session.add(order)
    await sqlite_order_session.commit()
    await sqlite_order_session.refresh(order)

    stale_stage = OrderWorkStage(
        order_id=order.id,
        name="Старый выезд",
        installer_id=installer.id,
        start_time=datetime.now() - timedelta(days=30),
        status=OrderStageStatus.PLANNED,
    )
    unscheduled_stage = OrderWorkStage(
        order_id=order.id,
        name="Без даты",
        installer_id=installer.id,
        start_time=None,
        status=OrderStageStatus.PLANNED,
    )
    upcoming_stage = OrderWorkStage(
        order_id=order.id,
        name="Будущий выезд",
        installer_id=installer.id,
        start_time=datetime.now() + timedelta(days=2),
        status=OrderStageStatus.PLANNED,
    )
    completed_stage = OrderWorkStage(
        order_id=order.id,
        name="Закрытый выезд",
        installer_id=installer.id,
        start_time=datetime.now() - timedelta(days=30),
        status=OrderStageStatus.COMPLETED,
    )
    sqlite_order_session.add_all([stale_stage, unscheduled_stage, upcoming_stage, completed_stage])
    await sqlite_order_session.commit()
    for stage in (stale_stage, unscheduled_stage, upcoming_stage, completed_stage):
        await sqlite_order_session.refresh(stage)

    result = await OrderService.list_stale_order_stages(sqlite_order_session, older_than_days=7)
    names = {item["name"] for item in result["items"]}

    assert result["total"] == 2
    assert names == {"Старый выезд", "Без даты"}
    assert result["items"][0]["customer_name"] == "Иван"

    canceled = await OrderService.cancel_order_stage_direct(sqlite_order_session, stale_stage.id)
    assert canceled["status"] == "canceled"

    after_cancel = await OrderService.list_stale_order_stages(sqlite_order_session, older_than_days=7)
    assert {item["name"] for item in after_cancel["items"]} == {"Без даты"}

    deleted = await OrderService.delete_order_stage_direct(sqlite_order_session, unscheduled_stage.id)
    assert deleted == {"ok": True, "id": unscheduled_stage.id}
    assert await sqlite_order_session.get(OrderWorkStage, unscheduled_stage.id) is None


@pytest.mark.asyncio
async def test_service_validates_work_stage_status_and_order(sqlite_order_session):
    customer = Customer(name="Stage Customer", phone="+375291234500")
    sqlite_order_session.add(customer)
    await sqlite_order_session.commit()
    await sqlite_order_session.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.EXECUTION, title="Монтаж")
    sqlite_order_session.add(order)
    await sqlite_order_session.commit()
    await sqlite_order_session.refresh(order)

    created = await OrderService.add_order_stage(
        sqlite_order_session,
        int(order.id),
        OrderWorkStageCreatePayload(name="Монтаж", status="in_progress"),
    )
    assert created["work_stages"][0]["status"] == "in_progress"

    stage = (await sqlite_order_session.execute(select(OrderWorkStage))).scalars().first()
    assert stage is not None

    with pytest.raises(ValueError, match="Invalid work stage status"):
        await OrderService.update_order_stage(
            sqlite_order_session,
            int(order.id),
            int(stage.id),
            OrderWorkStageUpdatePayload(status="waiting_for_magic"),
        )

    with pytest.raises(ValueError, match="Order not found"):
        await OrderService.add_order_stage(
            sqlite_order_session,
            999999,
            OrderWorkStageCreatePayload(name="Невозможный заказ"),
        )


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


def test_service_repair_meta_normalizes_status_and_booleanish_values():
    meta = OrderService.normalize_repair_meta(
        {
            "repair_status": "Awaiting Customer Approval",
            "customer_complaint": "  Не охлаждает  ",
            "diagnostic_result": "Недостаток хладагента.",
            "repair_recommendation": "Проверить контур на утечку.",
            "repair_possible": "Да",
            "repair_not_viable": " нет ",
            "empty": "   ",
        },
        default_status=OrderService.REPAIR_DEFAULT_STATUS,
    )

    assert meta["repair_status"] == "awaiting_customer_approval"
    assert meta["customer_complaint"] == "Не охлаждает"
    assert meta["diagnostic_result"] == "Недостаток хладагента."
    assert meta["repair_recommendation"] == "Проверить контур на утечку."
    assert meta["repair_possible"] is True
    assert meta["repair_not_viable"] is False
    assert "empty" not in meta

    with pytest.raises(ValueError, match="Invalid repair_status"):
        OrderService.normalize_repair_meta({"repair_status": "waiting_for_magic"})


def test_service_repair_meta_preserves_canonical_and_refrigerant_fields():
    meta = OrderService.normalize_repair_meta(
        {
            "customer_complaint": "Не запускается",
            "complaint_official": "Отсутствие запуска оборудования",
            "additional_conditions": "Работы после согласования.",
            "customer_approval_status": "pending",
            "customer_approval_note": "Ждет звонка.",
            "parts_status": "ordered",
            "refrigerant_type": " R32 ",
            "refrigerant_amount": " 0,35 кг ",
            "refrigerant_pricing_mode": " по фактической массе ",
        },
        default_status=OrderService.REPAIR_DEFAULT_STATUS,
    )

    assert meta["repair_status"] == "new"
    assert meta["complaint_official"] == "Отсутствие запуска оборудования"
    assert meta["additional_conditions"] == "Работы после согласования."
    assert meta["customer_approval_status"] == "pending"
    assert meta["customer_approval_note"] == "Ждет звонка."
    assert meta["parts_status"] == "ordered"
    assert meta["refrigerant_type"] == "R32"
    assert meta["refrigerant_amount"] == "0,35 кг"
    assert meta["refrigerant_pricing_mode"] == "по фактической массе"


def test_service_repair_transition_helpers_complete_without_global_status_change():
    order = Order(status=OrderStatus.NEW_LEAD, workflow_type="repair")

    OrderService.set_repair_workflow_status(order, "new", {"customer_complaint": "Не охлаждает"})
    OrderService.mark_repair_diagnostic_in_progress(order)
    OrderService.record_repair_diagnostic_result(
        order,
        "Выявлена утечка хладагента.",
        repair_recommendation="Устранить утечку и дозаправить контур.",
        repair_possible="да",
    )
    OrderService.mark_repair_approved_for_repair(order, note="Клиент согласовал ремонт.")
    OrderService.mark_repair_in_progress(order)
    final_meta = OrderService.mark_repair_completed(order, note="Работы выполнены.")

    assert order.status == OrderStatus.NEW_LEAD
    assert final_meta["repair_status"] == "completed"
    assert final_meta["customer_complaint"] == "Не охлаждает"
    assert final_meta["diagnostic_result"] == "Выявлена утечка хладагента."
    assert final_meta["repair_recommendation"] == "Устранить утечку и дозаправить контур."
    assert final_meta["repair_possible"] is True
    assert final_meta["customer_approval_status"] == "approved"
    assert final_meta["repair_completion_note"] == "Работы выполнены."


def test_service_repair_transition_helpers_support_not_repairable_path():
    order = Order(status=OrderStatus.NEGOTIATION, workflow_type="repair")

    OrderService.set_repair_workflow_status(order, "new", {"customer_complaint": "Не запускается"})
    meta = OrderService.mark_repair_not_repairable(
        order,
        "Компрессор разрушен, ремонт экономически нецелесообразен.",
        diagnostic_result="Диагностика подтвердила критический отказ компрессора.",
    )

    assert order.status == OrderStatus.NEGOTIATION
    assert meta["repair_status"] == "not_repairable"
    assert meta["repair_possible"] is False
    assert meta["repair_not_viable"] is True
    assert meta["repair_not_viable_reason"] == "Компрессор разрушен, ремонт экономически нецелесообразен."
    assert meta["diagnostic_result"] == "Диагностика подтвердила критический отказ компрессора."


def test_service_repair_transition_helpers_reject_non_repair_orders():
    order = Order(status=OrderStatus.NEW_LEAD, workflow_type="sales_installation")

    with pytest.raises(ValueError, match="repair orders"):
        OrderService.mark_repair_in_progress(order)


@pytest.mark.asyncio
async def test_service_get_orders_for_manager_segment_and_search(db):
    c1 = Customer(name="Alice", phone="+375291111111", type=CustomerType.individual)
    c2 = Customer(name="Acme LLC", phone="+375292222222", type=CustomerType.individual, inn="999000111")
    db.add(c1)
    db.add(c2)
    await db.commit()
    await db.refresh(c1)
    await db.refresh(c2)

    db.add(Order(customer_id=c1.id, status=OrderStatus.NEGOTIATION, comment="note 1"))
    db.add(Order(customer_id=c2.id, status=OrderStatus.NEGOTIATION, comment="note 2"))
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
            status=OrderStatus.NEGOTIATION,
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
    db.add(Order(customer_id=None, status=OrderStatus.NEGOTIATION, comment="legacy"))
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

    db.add(Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION, next_followup_date=datetime.now() - timedelta(days=1)))
    db.add(Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION, next_followup_date=datetime.now() + timedelta(days=1)))
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
        products=[{"product_id": product.id, "quantity": 2, "price": 1300}],
        services=[{"service_id": service.id, "title": "Srv", "quantity": 1, "price": 200}],
    )

    data = await OrderService.update_order_for_manager(db, order.id, payload)
    assert data is not None
    assert data["status"] == "negotiation"
    assert len(data["product_lines"]) == 1
    assert data["product_lines"][0]["cost"] == 0
    assert data["service_lines"][0]["cost"] == 150
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
async def test_service_non_repair_update_has_no_repair_side_effects(db):
    customer = Customer(name="No Repair", phone="+375294444446", type=CustomerType.individual)
    tariff = ServiceTariff(
        service_kind="repair",
        selector_label="Диагностика кондиционера",
        estimate_template="Диагностика кондиционера",
        category="diagnostic",
        base_price=80,
        is_active=True,
    )
    db.add(customer)
    db.add(tariff)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD, workflow_type="sales_installation")
    db.add(order)
    await db.commit()
    await db.refresh(order)

    data = await OrderService.update_order_for_manager(
        db,
        order.id,
        ManagerOrderUpdatePayload(comment="Обычная заявка без ремонта"),
    )

    assert data is not None
    assert data["workflow_type"] == "sales_installation"
    assert data["repair_meta"] == {}
    assert data["service_lines"] == []


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

    with pytest.raises(ValueError, match="Product not found"):
        await OrderService.update_order_for_manager(
            db,
            order.id,
            ManagerOrderUpdatePayload(products=[{"product_id": 999999, "quantity": 1, "price": 100}]),
        )

    product = Product(title="Validation Product", slug="validation-product", price=100)
    service = Service(title="Validation Service", slug="validation-service", base_price=50)
    db.add(product)
    db.add(service)
    await db.commit()
    await db.refresh(product)
    await db.refresh(service)

    with pytest.raises(ValueError, match="Product cost cannot be negative"):
        await OrderService.update_order_for_manager(
            db,
            order.id,
            ManagerOrderUpdatePayload(products=[{"product_id": product.id, "quantity": 1, "price": 100, "cost": -1}]),
        )

    with pytest.raises(ValueError, match="Service not found"):
        await OrderService.update_order_for_manager(
            db,
            order.id,
            ManagerOrderUpdatePayload(services=[{"service_id": 999999, "title": "Bad", "quantity": 1, "price": 100}]),
        )

    with pytest.raises(ValueError, match="Service cost cannot be negative"):
        await OrderService.update_order_for_manager(
            db,
            order.id,
            ManagerOrderUpdatePayload(
                services=[{"service_id": service.id, "title": service.title, "quantity": 1, "price": 100, "cost": -1}]
            ),
        )


@pytest.mark.asyncio
async def test_service_update_order_lost_archives_customer_in_same_flow(db):
    customer = Customer(name="Lost Only", phone="+375295551111", type=CustomerType.individual)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    updated = await OrderService.update_order_for_manager(
        db,
        order.id,
        ManagerOrderUpdatePayload(status="closed", closing_result="lost"),
    )

    assert updated is not None
    refreshed_customer = await db.get(Customer, customer.id)
    assert refreshed_customer is not None
    assert refreshed_customer.is_archived is True


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
