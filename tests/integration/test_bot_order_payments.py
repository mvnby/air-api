"""Verify real Telegram payment records against the Manager finance command."""

import asyncio
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot_order_desk import BotOrderCommandRequest
from api_contracts.bot_order_payments import BotRecordPayment
from core.command_actor import CommandActor
from models import BankReceipt, Order, OrderProductLink, OrderProposal, OrderWorkStage, Payment, StaffUser, Storefront, Tenant
from models.leads_inbox import InboxTriageState
from schemas_manager_orders import PaymentCreatePayload
from services.bot_order_desk import change_order, get_order_desk
from services.bot_workspace_service import Workspace
from services.order_payment_command_service import OrderPaymentCommandService
from services.tenant_entity_access_service import TenantEntityAccessService


@pytest.fixture
async def workspace(db_engine, tenant_scope):
    async with AsyncSession(db_engine) as db:
        db.add(StaffUser(id=42, telegram_id=501, username="test-payment-manager", display_name="Менеджер", primary_role="owner"))
        await db.commit()
    return Workspace(CommandActor(42, "test-payment-manager", tenant_scope, channel="telegram"), "main")


async def seed_order(db, **fields):
    values = {"tenant_id": 1, "storefront_id": 1, "status": "negotiation", **fields}
    order = Order(**values)
    db.add(order)
    await db.flush()
    db.add(OrderProductLink(order_id=order.id, title_snapshot="Согласованная модель", price=300))
    await db.flush()
    return order


def payment_change(**fields):
    return {
        "kind": "record_payment", "amount": "50.00", "currency": "BYN", "type": "postpayment",
        "received_on": "2025-05-12", "confirmed": True, **fields,
    }


def request(desk, **fields):
    return BotOrderCommandRequest(
        telegram_id=501, expected_context_version=0, expected_revision=desk.revision,
        idempotency_key=uuid4(), change=payment_change(**fields),
    )


@pytest.mark.parametrize("fields", [
    {"amount": "0"}, {"amount": "-3.4"}, {"amount": "3.401"}, {"amount": "Infinity"},
    {"type": "bank_confirmed"}, {"currency": "GBP"}, {"bank_receipt_id": 1}, {"confirmed": "true"},
])
def test_record_requires_valid_actual_amount_and_cannot_forge_bank_link(fields):
    with pytest.raises(ValidationError):
        BotRecordPayment.model_validate(payment_change(**fields))


async def test_legacy_payment_totals_fx_bank_history_and_workflow(db, workspace):
    order = await seed_order(db, target_currency="USD", target_currency_amount=100, auto_execution_on_payment=True)
    order_id = order.id
    archived = OrderProposal(order_id=order.id, name="Архивный вариант", is_archived=True)
    receipt = BankReceipt(sender_email="bank@example.test", subject="Тестовое поступление", fingerprint="test-fx",
                          raw_body="", status="matched", amount=75)
    db.add_all([archived, receipt])
    await db.flush()
    historic = OrderProductLink(order_id=order_id, proposal_id=archived.id, title_snapshot="Архив", price=1750)
    db.add_all([
        historic,
        Payment(order_id=order_id, amount=75, bank_receipt_id=receipt.id, date=datetime(2025, 5, 10), type="prepayment"),
        Payment(order_id=order_id, amount=24.75, currency="USD", date=datetime(2025, 5, 11), type="prepayment"),
    ])
    await db.flush()
    card = await get_order_desk(db, workspace, order_id)
    info = card.payments
    assert card.selected_proposal_id is None
    assert (info.total_amount, info.total_payments, info.balance_due) == tuple(map(Decimal, ["300", "149.25", "150.75"]))
    assert (info.target_currency, info.exchange_rate, info.target_currency_balance_due) == ("USD", Decimal(3), Decimal("50.25"))
    assert info.currencies == ["BYN", "USD"]
    assert [(row.received_on, row.bank_confirmed) for row in info.entries] == [
        (date(2025, 5, 11), False), (date(2025, 5, 10), True),
    ]
    assert "перейдёт в работу" in info.workflow_notice
    call = request(card, amount="50.25", currency="USD", comment="  Квитанция № 14  ")
    result = await change_order(db, workspace, order_id, call)
    assert result.status == "execution" and result.payments.balance_due == 0
    assert result.payments.total_payments == 300 and result.payments.target_currency_balance_due == 0
    row = result.payments.entries[0]
    assert (row.amount, row.currency, row.received_on, row.comment, row.bank_confirmed) == (
        Decimal("50.25"), "USD", date(2025, 5, 12), "Квитанция № 14", False,
    )
    await db.refresh(historic)
    await db.refresh(order)
    assert historic.proposal_id == archived.id
    assert (order.total_amount, order.total_payments, order.balance_due) == (300, 300, 0)
    replay = await change_order(db, workspace, order_id, call)
    assert replay == result and len(replay.payments.entries) == 3


@pytest.mark.parametrize(("on_hold", "stage", "expected"), [
    (False, "completed", "closed"), (False, "planned", "execution"), (True, "completed", "execution"),
])
async def test_full_payment_respects_canonical_close_and_waiting_rules(db, workspace, on_hold, stage, expected):
    order = await seed_order(
        db, status="execution", execution_status="awaiting_payment", auto_close_on_payment=True, is_on_hold=on_hold,
    )
    db.add(OrderWorkStage(order_id=order.id, name="Монтаж", status=stage))
    await db.flush()
    card = await get_order_desk(db, workspace, order.id)
    if expected == "closed":
        assert "завершиться автоматически" in card.payments.workflow_notice
    elif on_hold:
        assert "останется в ожидании" in card.payments.workflow_notice
    else:
        assert card.payments.workflow_notice is None
    result = await change_order(db, workspace, order.id, request(card, amount="300.00"))
    assert result.status == expected and result.payments.balance_due == 0
    assert result.payments.can_record is (expected != "closed")


async def test_payment_policy_rejects_unconfirmed_future_foreign_demo_closed_and_archived(db, workspace):
    order = await seed_order(db)
    card = await get_order_desk(db, workspace, order.id)
    future = (card.payments.received_on_max + timedelta(days=1)).isoformat()
    for fields, error in [
        ({"confirmed": False}, "уже получена"), ({"received_on": future}, "в будущем"), ({"currency": "EUR"}, "сумма сделки"),
    ]:
        with pytest.raises(ValueError, match=error):
            await change_order(db, workspace, order.id, request(card, **fields))

    demo = replace(workspace, actor=replace(workspace.actor, tenant_scope=replace(workspace.scope, demo_read_only=True)))
    view = await get_order_desk(db, demo, order.id)
    assert not view.payments.can_record
    with pytest.raises(PermissionError):
        await change_order(db, demo, order.id, request(view))

    db.add(InboxTriageState(
        entity_kind="order", entity_id=order.id, order_id=order.id, tenant_id=1, storefront_id=1,
        outcome="refusal", archived_at=datetime.now(timezone.utc),
    ))
    await db.flush()
    archived = await get_order_desk(db, workspace, order.id)
    assert not archived.payments.can_record
    with pytest.raises(ValueError, match="в архиве"):
        await change_order(db, workspace, order.id, request(archived))

    closed = await seed_order(db, status="closed", closing_result="lost")
    view = await get_order_desk(db, workspace, closed.id)
    assert not view.payments.can_record
    with pytest.raises(ValueError, match="в открытом заказе"):
        await change_order(db, workspace, closed.id, request(view))
    assert not (await db.scalars(select(Payment.id))).all()


async def test_archived_only_proposal_has_no_payable_total(db, workspace):
    order = Order(tenant_id=1, storefront_id=1, status="negotiation", auto_execution_on_payment=True)
    db.add(order)
    await db.flush()
    archived = OrderProposal(order_id=order.id, name="Архивный вариант", is_archived=True)
    db.add(archived)
    await db.flush()
    db.add(OrderProductLink(order_id=order.id, proposal_id=archived.id, title_snapshot="Архив", price=1750))
    await db.flush()
    card = await get_order_desk(db, workspace, order.id)
    assert card.payments.total_amount == 0 and not card.payments.can_record
    with pytest.raises(ValueError, match="Добавьте позиции"):
        await change_order(db, workspace, order.id, request(card))
    assert (await db.scalars(select(OrderProposal.id))).all() == [archived.id]


async def test_payment_read_and_write_are_fenced_by_company_and_storefront(db, workspace):
    db.add(Tenant(id=2, slug="payments-other", display_name="Другая компания"))
    await db.flush()
    db.add_all([
        Storefront(id=2, tenant_id=1, slug="different-site", display_name="Другая витрина"),
        Storefront(id=3, tenant_id=2, slug="other", display_name="Другая компания"),
    ])
    await db.flush()
    secondary = await seed_order(db, storefront_id=2)
    outsider = await seed_order(db, tenant_id=2, storefront_id=3)
    visible = await seed_order(db)
    card = await get_order_desk(db, workspace, visible.id)
    for order in (secondary, outsider):
        with pytest.raises(HTTPException) as error:
            await get_order_desk(db, workspace, order.id)
        assert error.value.status_code == 404
        with pytest.raises(HTTPException) as error:
            await change_order(db, workspace, order.id, request(card))
        assert error.value.status_code == 404
    assert not (await db.scalars(select(Payment.id))).all()


async def test_web_first_invalidates_open_telegram_confirmation(db_engine, workspace):
    async with AsyncSession(db_engine, expire_on_commit=False) as bot, AsyncSession(db_engine) as web:
        order = await seed_order(bot)
        await bot.commit()
        card = await get_order_desk(bot, workspace, order.id)
        await OrderPaymentCommandService.add_payment(
            web, order.id, PaymentCreatePayload(amount=50, type="postpayment"), tenant_scope=workspace.scope,
        )
        with pytest.raises(HTTPException) as error:
            await change_order(bot, workspace, order.id, request(card))
        assert error.value.status_code == 409
        fresh = await get_order_desk(bot, workspace, order.id)
        assert len(fresh.payments.entries) == 1 and fresh.payments.balance_due == 250


async def test_overlapping_web_retry_checks_new_payment_under_same_lock(db_engine, workspace, monkeypatch):
    async with AsyncSession(db_engine, expire_on_commit=False) as bot, AsyncSession(db_engine) as web:
        order = await seed_order(bot)
        await bot.commit()
        card = await get_order_desk(bot, workspace, order.id)
        scope = workspace.scope
        access = TenantEntityAccessService.get_order
        await access(bot, order.id, tenant_scope=scope, for_update=True)

        reached_lock = asyncio.Event()

        async def mark_pending_lock(session, *args, **kwargs):
            if session is web and kwargs.get("for_update"):
                reached_lock.set()
            return await access(session, *args, **kwargs)

        monkeypatch.setattr(TenantEntityAccessService, "get_order", mark_pending_lock)
        payload = PaymentCreatePayload(amount=50, type="postpayment")
        candidate = asyncio.create_task(OrderPaymentCommandService.add_payment(web, order.id, payload, tenant_scope=scope))
        try:
            await asyncio.wait_for(reached_lock.wait(), timeout=3)
            saved = await change_order(bot, workspace, order.id, request(card))
            assert len(saved.payments.entries) == 1
            with pytest.raises(ValueError, match="только что учтена"):
                await asyncio.wait_for(candidate, timeout=3)
        finally:
            if not candidate.done():
                candidate.cancel()
                await asyncio.gather(candidate, return_exceptions=True)
        separate = await OrderPaymentCommandService.add_payment(web, order.id, payload, tenant_scope=scope)
        assert len(separate) == 2
