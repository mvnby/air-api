from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select

from api_contracts.bot_order_followup import BotOrderFollowupChange
from core.command_actor import CommandActor
from models import Customer, Order, OrderDocument, OrderProductLink, OrderProposal, OrderServiceLink, OrderStatus, Payment, Tenant
from models.tenant_commerce import TenantAuditEvent
from services.bot_order_desk import get_order_desk
from services.bot_order_followup import apply_followup, read_followup
from services.bot_workspace_service import Workspace, scoped_order_money
from services.command_transaction import command_transaction
from services.customer_creation_service import CustomerAlreadyExistsError
from services.order_projection_service import OrderProjectionService
from services.tenant_entity_access_service import TenantEntityAccessService


_CHANGE = TypeAdapter(BotOrderFollowupChange)


@pytest.fixture
def actor(tenant_scope):
    return CommandActor(42, "telegram-manager", tenant_scope, channel="telegram")


async def _order(db, actor, **fields):
    order = Order(tenant_id=actor.tenant_scope.tenant_id, storefront_id=actor.tenant_scope.storefront_id,
                  status=OrderStatus.NEGOTIATION, **fields)
    db.add(order)
    await db.flush()
    return order.id


async def _detail(db, actor, order_id):
    detail = await OrderProjectionService.get_order_detail_for_manager(
        db, order_id, tenant_scope=actor.tenant_scope, repair_legacy_state=False,
    )
    detail.update(await scoped_order_money(db, actor.tenant_scope, order_id, legacy_ungrouped_only=True))
    return detail


async def _change(db, actor, order_id, **fields):
    change = _CHANGE.validate_python(fields)
    async with command_transaction(db):
        await TenantEntityAccessService.get_order(
            db, order_id, tenant_scope=actor.tenant_scope, for_update=True, populate_existing=True,
        )
        detail = await _detail(db, actor, order_id)
        await apply_followup(db, actor, order_id, change, detail)


async def test_contact_object_and_planning_apply_only_requested_fields(db, actor):
    order_id = await _order(db, actor, delivery_address="Адрес исходный", comment="Исходный комментарий",
                            technical_meta={"contact_name": "Анна", "contact_phone": "+375291111111", "source": "catalog"},
                            auto_execution_on_payment=True, total_amount=100, balance_due=0)
    baseline = await _detail(db, actor, order_id)
    await _change(db, actor, order_id, kind="set_details", contact_name=" Анна Иванова ",
                  delivery_address="Минск, ул. Примерная, 17")
    await _change(db, actor, order_id, kind="set_schedule", field="measurement_date",
                  date="2027-01-12T09:30:00Z")
    await _change(db, actor, order_id, kind="set_schedule", field="next_followup_date",
                  date="2027-01-13T11:00:00")
    await _change(db, actor, order_id, kind="set_details", contact_phone=None)

    detail = await _detail(db, actor, order_id)
    assert detail["contact_name"] == "Анна Иванова"
    assert detail["contact_phone"] is None
    assert detail["delivery_address"] == "Минск, ул. Примерная, 17"
    assert detail["comment"] == "Исходный комментарий"
    assert detail["next_followup_date"] == datetime(2027, 1, 13, 11)
    assert detail["measurement_required"]
    assert detail["measurement_date"] == datetime(2027, 1, 12, 12, 30)
    assert detail["installation_date"] is None
    assert detail["status"] == "negotiation" and detail["negotiation_status"] == "awaiting_visit"
    assert detail["workflow_revision"] == baseline["workflow_revision"] + 4
    assert await db.scalar(select(func.count(OrderProposal.id)).where(OrderProposal.order_id == order_id)) == 0


async def test_customer_assignment_and_document_history_are_scoped(db, actor):
    db.add(Tenant(id=2, slug="followup-other", display_name="Другая компания"))
    await db.flush()
    db.add_all([
        Customer(id=21, tenant_id=1, name="Первый клиент", phone="+375291111111"),
        Customer(id=22, tenant_id=1, name="Архивный клиент", phone="", is_archived=True),
        Customer(id=23, tenant_id=2, name="Чужой клиент", phone=""),
        Customer(id=24, tenant_id=1, name="Второй клиент", phone="+375291111112"),
    ])
    order_id = await _order(db, actor, delivery_address="Адрес объекта")
    for inaccessible in (22, 23):
        with pytest.raises(LookupError, match="Клиент не найден"):
            await _change(db, actor, order_id, kind="assign_customer", customer_id=inaccessible)
    await _change(db, actor, order_id, kind="assign_customer", customer_id=21)
    with pytest.raises(ValueError, match="Подтвердите смену"):
        await _change(db, actor, order_id, kind="assign_customer", customer_id=24)
    await _change(db, actor, order_id, kind="assign_customer", customer_id=24, confirmed=True)
    db.add(OrderDocument(order_id=order_id, tenant_id=1, doc_type="contract", number="Сохранённый-1",
                         render_snapshot={"customer_name": "Второй клиент"}))
    await db.flush()

    projection = await read_followup(db, actor, await _detail(db, actor, order_id))
    assert projection.customer.id == 24 and projection.delivery_address == "Адрес объекта"
    assert not projection.can_assign_customer and projection.can_edit_details
    with pytest.raises(ValueError, match="Смена клиента недоступна"):
        await _change(db, actor, order_id, kind="assign_customer", customer_id=21, confirmed=True)
    await _change(db, actor, order_id, kind="set_details", comment="Дополнено")
    doc = await db.scalar(select(OrderDocument).where(OrderDocument.order_id == order_id))
    assert doc.number == "Сохранённый-1" and doc.render_snapshot == {"customer_name": "Второй клиент"}


async def test_new_customer_creation_links_atomically_and_checks_duplicates(db, actor):
    first_order_id = await _order(db, actor)
    next_order_id = await _order(db, actor)
    command = dict(kind="create_customer", name="ИП Сидоров", customer_type="individual_entrepreneur",
                   phone="+375 (29) 234-56-78", email="IP@EXAMPLE.BY", inn="123456789")

    # Receipt failures after a nested command must roll back the new customer and its link.
    with pytest.raises(RuntimeError, match="receipt failed"):
        async with command_transaction(db):
            await _change(db, actor, first_order_id, **command)
            raise RuntimeError("receipt failed")
    assert await db.scalar(select(Customer.id).where(Customer.inn == "123456789")) is None
    assert (await _detail(db, actor, first_order_id))["customer"] is None

    await _change(db, actor, first_order_id, **command)
    customer = await db.scalar(select(Customer).where(Customer.inn == "123456789"))
    assert customer.type == "individual_entrepreneur" and customer.signing_mode == "self"
    assert customer.email == "ip@example.by"
    assert (await _detail(db, actor, first_order_id))["customer"]["id"] == customer.id
    with pytest.raises(CustomerAlreadyExistsError):
        await _change(db, actor, next_order_id, **{**command, "phone": "80292345678"})
    assert (await _detail(db, actor, next_order_id))["customer"] is None


async def test_workflow_requires_active_customer_and_explicit_unpaid_work(db, actor):
    order_id = await _order(db, actor)
    db.add(OrderServiceLink(order_id=order_id, title="Монтаж", price=Decimal("120.00")))
    db.add(Customer(id=21, tenant_id=1, name="Иван", phone="+375291111111"))
    await db.flush()
    detail = await _detail(db, actor, order_id)
    actions = (await read_followup(db, actor, detail)).workflow_actions
    assert all(not action.action.startswith("execution:") for action in actions)
    demo_actor = replace(actor, tenant_scope=replace(actor.tenant_scope, demo_read_only=True))
    demo_followup = await read_followup(db, demo_actor, detail)
    assert not demo_followup.can_edit_details and demo_followup.workflow_status_label == "Ждёт предложение"
    await _change(db, actor, order_id, kind="assign_customer", customer_id=21)

    transition = dict(kind="transition_order", action="execution:needs_schedule")
    with pytest.raises(ValueError, match="Подтвердите изменение"):
        await _change(db, actor, order_id, **transition)
    with pytest.raises(ValueError, match="Укажите причину"):
        await _change(db, actor, order_id, **transition, confirmed=True)
    await _change(db, actor, order_id, **transition, confirmed=True, reason="Постоплата по договорённости")
    detail = await _detail(db, actor, order_id)
    assert detail["status"] == "execution" and detail["execution_status"] == "needs_schedule"
    assert detail["execution_without_payment_reason"] == "Постоплата по договорённости"
    with pytest.raises(ValueError, match="действие недоступно"):
        await _change(db, actor, order_id, kind="transition_order", action="closed_won", confirmed=True)

    await _change(db, actor, order_id, kind="set_schedule", field="installation_date", date="2027-02-01T13:00")
    assert (await _detail(db, actor, order_id))["execution_status"] == "scheduled"
    await _change(db, actor, order_id, kind="transition_order", action="execution:work_done", confirmed=True)
    await _change(db, actor, order_id, kind="set_schedule", field="installation_date", date="2027-02-01T14:00")
    assert (await _detail(db, actor, order_id))["execution_status"] == "work_done"

    db.add(Payment(order_id=order_id, amount=120))
    await _change(db, actor, order_id, kind="transition_order", action="closed_won", confirmed=True)
    detail = await _detail(db, actor, order_id)
    assert detail["status"] == "closed" and detail["closing_result"] == "won"
    closed_followup = await read_followup(db, actor, detail)
    assert not closed_followup.workflow_actions and closed_followup.workflow_status_label == "Завершён"


async def test_close_legacy_order_uses_only_ungrouped_lines_and_preserves_archived_variant(db, actor):
    customer = Customer(tenant_id=1, name="Клиент старого заказа", phone="")
    db.add(customer)
    await db.flush()
    order_id = await _order(db, actor, customer_id=customer.id, execution_status="work_done")
    order = await db.get(Order, order_id)
    order.status = OrderStatus.EXECUTION
    archived = OrderProposal(order_id=order_id, name="Архивный вариант", is_archived=True, is_selected=False)
    db.add(archived)
    await db.flush()
    historical = OrderProductLink(order_id=order_id, proposal_id=archived.id, title_snapshot="Архивная модель", price=1500)
    db.add_all([
        historical,
        OrderProductLink(order_id=order_id, title_snapshot="Согласованная модель", price=923),
        OrderServiceLink(order_id=order_id, title="Монтаж", price=Decimal("50.00")),
        Payment(order_id=order_id, amount=973),
    ])
    await db.flush()

    legacy_board = await scoped_order_money(db, actor.tenant_scope, order_id)
    assert (legacy_board["total_amount"], legacy_board["balance_due"]) == (2473, 1500)
    desk = await get_order_desk(db, Workspace(actor, "main"), order_id)
    selected = next(proposal for proposal in desk.proposals if proposal.is_selected)
    assert selected.id is None and selected.total_amount == Decimal("973.00")
    actions = {item.action: item for item in desk.followup.workflow_actions}
    assert actions["closed_won"].requires_confirmation and not actions["execution:needs_schedule"].requires_reason
    assert await db.scalar(select(func.count(OrderProposal.id)).where(OrderProposal.order_id == order_id)) == 1

    await _change(db, actor, order_id, kind="transition_order", action="closed_won", confirmed=True)
    await db.refresh(order)
    await db.refresh(historical)
    assert order.closing_result == "won"
    assert (order.total_amount, order.total_payments, order.balance_due) == (973, 973, 0)
    updated_board = await scoped_order_money(db, actor.tenant_scope, order_id)
    assert (updated_board["total_amount"], updated_board["balance_due"]) == (973, 0)
    assert historical.proposal_id == archived.id and historical.price == 1500


async def test_wait_followup_and_resume_use_manager_archive_and_audit_rules(db, actor):
    order_id = await _order(db, actor, next_followup_date=datetime(2027, 2, 2, 13))
    with pytest.raises(ValueError, match="Укажите причину"):
        await _change(db, actor, order_id, kind="transition_order", action="wait", confirmed=True, reason_code="other")
    await _change(db, actor, order_id, kind="transition_order", action="wait", confirmed=True,
                  reason_code="site_readiness", reason="Ожидаем готовность объекта")
    followup = await read_followup(db, actor, await _detail(db, actor, order_id))
    assert followup.next_followup_date == datetime(2027, 2, 2, 13)
    assert followup.is_on_hold and {action.action for action in followup.workflow_actions} == {"resume"}
    await _change(db, actor, order_id, kind="set_schedule", field="next_followup_date", date="2027-02-03T13:00")
    await _change(db, actor, order_id, kind="transition_order", action="resume", confirmed=True)
    detail = await _detail(db, actor, order_id)
    assert not detail["is_on_hold"] and detail["next_followup_date"] == datetime(2027, 2, 3, 13)
    assert detail["on_hold_reason"] == "Ожидаем готовность объекта"
    events = (await db.scalars(select(TenantAuditEvent).where(TenantAuditEvent.entity_id == order_id))).all()
    assert len(events) == 2 and all(event.actor_staff_user_id == actor.staff_user_id for event in events)

    from models.leads_inbox import InboxTriageState

    db.add(InboxTriageState(entity_kind="order", entity_id=order_id, order_id=order_id,
                           tenant_id=1, storefront_id=1, archived_at=datetime.now(timezone.utc)))
    await db.flush()
    assert not (await read_followup(db, actor, detail)).can_edit_details
    with pytest.raises(ValueError, match="Заказ недоступен"):
        await _change(db, actor, order_id, kind="set_details", comment="Попытка правки архива")


def test_followup_payload_requires_narrow_explicit_changes():
    for fields in (
        {"kind": "set_details"},
        {"kind": "set_details", "comment": "  "},
        {"kind": "set_details", "title": "Произвольный PATCH"},
        {"kind": "set_schedule", "field": "installation_date"},
        {"kind": "set_schedule", "field": "measurement_date", "date": "2027-02-03"},
        {"kind": "transition_order", "action": "delete"},
        {"kind": "assign_customer", "customer_id": 5, "confirmed": "true"},
    ):
        with pytest.raises(ValidationError):
            _CHANGE.validate_python(fields)
