"""Installer remuneration acceptance through real HTTP, auth and transactions."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select

from models import Order, OrderWorkAssignment, Payment, StaffUser, TenantMembership, TenantWorkerProfile
from models.worker_money import WorkerCashAccount, WorkerCashHandover
from models.worker_pay import WorkerPayAgreement, WorkerPayOffsetCashAllocation, WorkerPayPayout, WorkerPayPayoutAllocation
from tests.unit.test_worker_money import (
    balance as cash_balance,
    cash,
    command,
    handover,
    headers,
    money_db as money_db,
    multi_db as multi_db,
    receive,
    responsibility_db as responsibility_db,
    worker_headers,
    workspace as cash_workspace,
    workspace_db as workspace_db,
)


@pytest.fixture
async def pay_db(money_db):  # noqa: F811 - shared authenticated workspace fixture
    from routers.worker_pay import installer_router, manager_router

    session, original = money_db
    app = original._transport.app
    app.include_router(installer_router)
    app.include_router(manager_router)
    member = await session.get(TenantMembership, 10)
    member.permissions = [*member.permissions, "worker.pay.manage"]
    await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield session, client


async def ok_post(client, path, payload, actor=None):
    response = await client.post(path, headers=actor or headers(), json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


async def pay_workspace(client, profile=None, actor=None):
    path = "/api/installer/pay" if profile is None else f"/api/manager/worker-pay/{profile}"
    response = await client.get(path, headers=actor or (worker_headers() if profile is None else headers()))
    assert response.status_code == 200, response.text
    return response.json()


def pay_balance(view, currency="BYN"):
    return next(row for row in view["balances"] if row["currency"] == currency)


async def agree(client, amount="200.00", currency="BYN", *, order_id=100, assignment_id=None, **kwargs):
    if assignment_id is None:
        assigned = await ok_post(client, f"/api/manager/orders/{order_id}/installer-workspace/assignments", {"staff_user_id": 22})
        assignment_id = assigned["assignments"][0]["id"]
    path = f"/api/manager/orders/{order_id}/worker-pay"
    view = await client.get(path, headers=headers())
    assert view.status_code == 200, view.text
    candidate = next(row for row in view.json()["candidates"] if row["assignment_id"] == assignment_id)
    payload = cash(candidate["account_version"], amount, currency, assignment_id=assignment_id, **kwargs)
    result = await ok_post(client, path + "/agreements", payload)
    profile = candidate["worker_profile_id"]
    current = await pay_workspace(client, profile)
    row = next(row for row in current["agreements"] if row["id"] == result["id"])
    return profile, row, payload, result


async def accrue(client, profile, agreement_id):
    view = await pay_workspace(client, profile)
    row = next(row for row in view["agreements"] if row["id"] == agreement_id)
    payload = command(view["version"], expected_agreement_version=row["version"])
    result = await ok_post(client, f"/api/manager/worker-pay/{profile}/agreements/{agreement_id}/accrue", payload)
    return payload, result


async def settle(client, profile, amount="200.00", *, kind="payouts", currency="BYN", **kwargs):
    view = await pay_workspace(client, profile)
    payload = cash(view["version"], amount, currency, **kwargs)
    result = await ok_post(client, f"/api/manager/worker-pay/{profile}/{kind}", payload)
    return payload, result


async def test_client_cash_offset_then_recipient_confirmed_handover_is_one_payment(pay_db):
    session, client = pay_db
    assignment, _, _ = await receive(client, "1000.00")
    profile, agreement, _, _ = await agree(client, assignment_id=assignment)
    before = await pay_workspace(client)
    assert pay_balance(before) == {"currency": "BYN", "agreed": "200.00", "accrued": "0.00", "paid": "0.00", "owed": "0.00"}
    await accrue(client, profile, agreement["id"])
    assert pay_balance(await pay_workspace(client))["owed"] == "200.00"
    await settle(client, profile, kind="offsets")
    assert pay_balance(await pay_workspace(client))["owed"] == "0.00"
    assert cash_balance(await cash_workspace(client))["held"] == "800.00"
    _, sent = await handover(client, "800.00")
    await ok_post(client, f"/api/manager/worker-money/{profile}/handovers/{sent['id']}/confirm", command(sent["version"]))
    final = await cash_workspace(client)
    assert sum((Decimal(row["held"]) for row in final["balances"]), Decimal(0)) == 0
    payments = list((await session.scalars(select(Payment))).all())
    assert len(payments) == 1 and Decimal(str(payments[0].amount)) == Decimal("1000.00")
    own = await pay_workspace(client)
    assert pay_balance(own)["paid"] == "200.00"
    assert own["items"][0]["kind"] == "offset"


@pytest.mark.parametrize("method", ["cash", "bank"])
async def test_company_payout_reduces_only_pay_liability_and_keeps_customer_cash(pay_db, method):
    session, client = pay_db
    assignment, _, _ = await receive(client, "1000.00")
    profile, agreement, _, _ = await agree(client, assignment_id=assignment)
    await accrue(client, profile, agreement["id"])
    await settle(client, profile, "75.25", method=method)
    assert pay_balance(await pay_workspace(client))["owed"] == "124.75"
    await settle(client, profile, "124.75", method=method)
    assert pay_balance(await pay_workspace(client))["owed"] == "0.00"
    assert cash_balance(await cash_workspace(client))["held"] == "1000.00"
    assert len(list((await session.scalars(select(Payment))).all())) == 1


async def test_partial_settlement_allocates_oldest_accrued_work_across_orders(pay_db):
    session, client = pay_db
    profile, first, _, _ = await agree(client, "40.25")
    await accrue(client, profile, first["id"])
    session.add(Order(id=101, tenant_id=1, storefront_id=1))
    await session.commit()
    _, second, _, _ = await agree(client, "60.75", order_id=101)
    await accrue(client, profile, second["id"])
    _, payout = await settle(client, profile, "50.00")
    view = await pay_workspace(client)
    rows = {row["id"]: row for row in view["agreements"]}
    assert (rows[first["id"]]["paid"], rows[first["id"]]["owed"]) == ("40.25", "0.00")
    assert (rows[second["id"]]["paid"], rows[second["id"]]["owed"]) == ("9.75", "51.00")
    allocations = list((await session.scalars(select(WorkerPayPayoutAllocation).where(WorkerPayPayoutAllocation.payout_id == payout["id"]).order_by(WorkerPayPayoutAllocation.agreement_id))).all())
    assert [(row.agreement_id, row.amount) for row in allocations] == [(first["id"], Decimal("40.25")), (second["id"], Decimal("9.75"))]


async def test_agreement_uuid_replay_payload_reuse_and_stale_account_or_row(pay_db):
    session, client = pay_db
    profile, row, payload, created = await agree(client)
    path = "/api/manager/orders/100/worker-pay/agreements"
    assert await ok_post(client, path, payload) == created
    reused = await client.post(path, headers=headers(), json={**payload, "amount": "201.00"})
    assert reused.status_code == 409, reused.text
    stale = await client.post(path, headers=headers(), json={**payload, "idempotency_key": str(uuid4())})
    assert stale.status_code == 409, stale.text
    view = await pay_workspace(client, profile)
    revise_path = f"/api/manager/worker-pay/{profile}/agreements/{row['id']}/revise"
    revision = cash(view["version"], "225.25", expected_agreement_version=row["version"])
    revised = await ok_post(client, revise_path, revision)
    assert await ok_post(client, revise_path, revision) == revised
    view = await pay_workspace(client, profile)
    stale_row = await client.post(revise_path, headers=headers(), json=cash(view["version"], "230.00", expected_agreement_version=row["version"]))
    assert stale_row.status_code == 409, stale_row.text
    accrued_payload, accrued = await accrue(client, profile, row["id"])
    assert await ok_post(client, f"/api/manager/worker-pay/{profile}/agreements/{row['id']}/accrue", accrued_payload) == accrued
    assert len(list((await session.scalars(select(WorkerPayAgreement))).all())) == 1


async def test_order_expense_tracks_agreement_revision_once_and_never_settlement(pay_db):
    session, client = pay_db
    profile, row, payload, _ = await agree(client)
    order = await session.get(Order, 100)
    await session.refresh(order)
    assert order.worker_pay_cost_byn == Decimal("200.00")
    initial_cost = Decimal(str(order.total_cost))
    view = await pay_workspace(client, profile)
    await ok_post(client, f"/api/manager/worker-pay/{profile}/agreements/{row['id']}/revise", cash(view["version"], "225.25", expected_agreement_version=row["version"]))
    await session.refresh(order)
    assert order.worker_pay_cost_byn == Decimal("225.25")
    assert Decimal(str(order.total_cost)) == initial_cost + Decimal("25.25")
    view = await pay_workspace(client, profile)
    current = view["agreements"][0]
    await ok_post(client, f"/api/manager/worker-pay/{profile}/agreements/{row['id']}/cancel", command(view["version"], expected_agreement_version=current["version"], reason="Изменение объёма работ"))
    await session.refresh(order)
    assert order.worker_pay_cost_byn == Decimal("0.00")
    assert Decimal(str(order.total_cost)) == initial_cost - Decimal("200.00")
    _, replacement, _, _ = await agree(client, "100.00", assignment_id=payload["assignment_id"])
    await session.refresh(order)
    expected_cost = order.total_cost
    await accrue(client, profile, replacement["id"])
    _, settled = await settle(client, profile, "25.25")
    await session.refresh(order)
    assert order.worker_pay_cost_byn == Decimal("100.00") and order.total_cost == expected_cost
    view = await pay_workspace(client, profile)
    await ok_post(client, f"/api/manager/worker-pay/{profile}/payouts/{settled['id']}/reverse", command(view["version"], reason="Ошибочный перевод"))
    await session.refresh(order)
    assert order.worker_pay_cost_byn == Decimal("100.00") and order.total_cost == expected_cost


async def test_agreement_audit_preserves_original_and_revised_foreign_pay_and_frozen_cost(pay_db):
    from models import TenantAuditEvent

    session, client = pay_db
    profile, row, _, _ = await agree(client, "100.00", "EUR", cost_byn_amount="350.00")
    original = await session.scalar(select(TenantAuditEvent).where(TenantAuditEvent.action == "worker_money.pay_agreed", TenantAuditEvent.entity_id == row["id"]))
    assert original.change_set["before"] is None
    initial = original.change_set["after"]
    assert {key: initial[key] for key in ("amount", "currency", "cost_byn_amount", "status", "version")} == {"amount": "100.00", "currency": "EUR", "cost_byn_amount": "350.00", "status": "agreed", "version": 0}
    view = await pay_workspace(client, profile)
    await ok_post(client, f"/api/manager/worker-pay/{profile}/agreements/{row['id']}/revise", cash(view["version"], "125.00", "EUR", cost_byn_amount="440.00", expected_agreement_version=row["version"]))
    revision = await session.scalar(select(TenantAuditEvent).where(TenantAuditEvent.action == "worker_money.pay_revise", TenantAuditEvent.entity_id == row["id"]))
    assert revision.change_set["before"] == initial
    assert {key: revision.change_set["after"][key] for key in ("amount", "currency", "cost_byn_amount", "status", "version")} == {"amount": "125.00", "currency": "EUR", "cost_byn_amount": "440.00", "status": "agreed", "version": 1}
    await session.refresh(original)
    assert original.change_set["after"] == initial
    order = await session.get(Order, 100)
    await session.refresh(order)
    assert order.worker_pay_cost_byn == Decimal("440.00")
    assert pay_balance(await pay_workspace(client), "EUR")["agreed"] == "125.00"


async def test_positive_legacy_pay_prevents_new_duplicate_commitment(pay_db):
    from models import Installer, OrderInstaller

    session, client = pay_db
    session.add(Installer(id=1, name="Existing payroll"))
    (await session.get(StaffUser, 22)).legacy_installer_id = 1
    session.add(OrderInstaller(order_id=100, installer_id=1, agreed_pay=200.00))
    await session.commit()
    assigned = await ok_post(client, "/api/manager/orders/100/installer-workspace/assignments", {"staff_user_id": 22})
    assignment_id = assigned["assignments"][0]["id"]
    view = await client.get("/api/manager/orders/100/worker-pay", headers=headers())
    assert view.status_code == 200, view.text
    candidate = next(row for row in view.json()["candidates"] if row["assignment_id"] == assignment_id)
    response = await client.post("/api/manager/orders/100/worker-pay/agreements", headers=headers(), json=cash(candidate["account_version"], "200.00", assignment_id=assignment_id))
    assert response.status_code in (400, 409), response.text
    assert await session.scalar(select(WorkerPayAgreement.id)) is None


@pytest.mark.parametrize("method", ["update_order_installers", "update_all_items"])
async def test_legacy_write_paths_cannot_reintroduce_duplicate_installer_expense(pay_db, method):
    from models import Installer, OrderInstaller
    from services.order_service import OrderService
    from tests.unit.test_order_responsibility import auth

    session, client = pay_db
    session.add(Installer(id=1, name="Existing payroll"))
    (await session.get(StaffUser, 22)).legacy_installer_id = 1
    await session.commit()
    await agree(client)
    installers = [{"installer_id": 1, "agreed_pay": 200.00}]
    data = installers if method == "update_order_installers" else {"installers": installers}
    with pytest.raises(ValueError, match="расчётах с монтажниками"):
        await getattr(OrderService, method)(session, 100, data, tenant_scope=auth().tenant_scope())
    await session.rollback()
    assert await session.scalar(select(OrderInstaller.installer_id)) is None


async def test_cancellation_releases_work_key_and_does_not_create_a_payable(pay_db):
    _, client = pay_db
    profile, row, payload, _ = await agree(client)
    view = await pay_workspace(client, profile)
    cancel = command(view["version"], expected_agreement_version=row["version"], reason="Работа отменена")
    path = f"/api/manager/worker-pay/{profile}/agreements/{row['id']}/cancel"
    cancelled = await ok_post(client, path, cancel)
    assert await ok_post(client, path, cancel) == cancelled
    view = await pay_workspace(client)
    assert all(Decimal(item["owed"]) == 0 for item in view["balances"])
    assert view["agreements"][0]["status"] == "cancelled"
    _, replacement, _, _ = await agree(client, "125.25", assignment_id=payload["assignment_id"])
    assert replacement["id"] != row["id"]


@pytest.mark.parametrize("amount,currency", [("0", "BYN"), ("-1", "BYN"), ("0.001", "BYN"), ("NaN", "BYN"), ("1.00", "RUB")])
async def test_pay_commands_require_positive_exact_supported_money(pay_db, amount, currency):
    session, client = pay_db
    profile, row, _, _ = await agree(client)
    await accrue(client, profile, row["id"])
    view = await pay_workspace(client, profile)
    response = await client.post(f"/api/manager/worker-pay/{profile}/payouts", headers=headers(), json=cash(view["version"], amount, currency))
    assert response.status_code == 422, response.text
    assert await session.scalar(select(WorkerPayPayout.id)) is None


async def test_no_advance_overpayment_or_currency_cross_and_no_revision_after_accrual(pay_db):
    session, client = pay_db
    profile, row, _, _ = await agree(client)
    path = f"/api/manager/worker-pay/{profile}"
    view = await pay_workspace(client, profile)
    for amount, currency in [("1.00", "BYN"), ("1.00", "EUR")]:
        response = await client.post(path + "/payouts", headers=headers(), json=cash(view["version"], amount, currency))
        assert response.status_code in (400, 409), response.text
    await accrue(client, profile, row["id"])
    view = await pay_workspace(client, profile)
    for amount, currency in [("200.01", "BYN"), ("1.00", "EUR")]:
        response = await client.post(path + "/payouts", headers=headers(), json=cash(view["version"], amount, currency))
        assert response.status_code in (400, 409), response.text
    current = view["agreements"][0]
    response = await client.post(path + f"/agreements/{row['id']}/revise", headers=headers(), json=cash(view["version"], "201.00", expected_agreement_version=current["version"]))
    assert response.status_code == 409, response.text
    assert await session.scalar(select(WorkerPayPayout.id)) is None


@pytest.mark.parametrize("kind", ["payouts", "offsets"])
async def test_payout_replay_and_immutable_reversal_restore_original_liability(pay_db, kind):
    session, client = pay_db
    assignment, _, _ = await receive(client, "1000.00")
    profile, row, _, _ = await agree(client, assignment_id=assignment)
    await accrue(client, profile, row["id"])
    payload, settled = await settle(client, profile, "75.25", kind=kind)
    path = f"/api/manager/worker-pay/{profile}"
    assert await ok_post(client, path + "/" + kind, payload) == settled
    reused = await client.post(path + "/" + kind, headers=headers(), json={**payload, "amount": "75.26"})
    assert reused.status_code == 409, reused.text
    view = await pay_workspace(client, profile)
    correction = command(view["version"], reason="Ошибочная выплата")
    reversed_result = await ok_post(client, path + f"/payouts/{settled['id']}/reverse", correction)
    assert await ok_post(client, path + f"/payouts/{settled['id']}/reverse", correction) == reversed_result
    assert pay_balance(await pay_workspace(client))["owed"] == "200.00"
    assert cash_balance(await cash_workspace(client))["held"] == "1000.00"
    original = await session.get(WorkerPayPayout, settled["id"])
    assert original.amount == Decimal("75.25") and original.reversed_at is not None
    assert original.method == ("offset" if kind == "offsets" else "cash")
    assert len(list((await session.scalars(select(WorkerPayPayout))).all())) == 1
    assert len(list((await session.scalars(select(Payment))).all())) == 1
    own = await pay_workspace(client)
    expected_kinds = {"offset", "offset_reversal"} if kind == "offsets" else {"payout", "payout_reversal"}
    assert {item["kind"] for item in own["items"]} == expected_kinds


async def test_pending_cash_handover_and_other_currency_cannot_fund_offset(pay_db):
    _, client = pay_db
    assignment, _, _ = await receive(client, "100.00", "EUR")
    profile, row, _, _ = await agree(client, assignment_id=assignment)
    await accrue(client, profile, row["id"])
    view = await pay_workspace(client, profile)
    path = f"/api/manager/worker-pay/{profile}/offsets"
    response = await client.post(path, headers=headers(), json=cash(view["version"], "1.00"))
    assert response.status_code in (400, 409), response.text
    assert pay_balance(await pay_workspace(client))["owed"] == "200.00"
    assert cash_balance(await cash_workspace(client), "EUR")["held"] == "100.00"


async def test_offset_cannot_spend_pending_handover_or_reverse_spent_receipt(pay_db):
    _, client = pay_db
    assignment, _, receipt = await receive(client, "1000.00")
    profile, row, _, _ = await agree(client, assignment_id=assignment)
    await accrue(client, profile, row["id"])
    _, pending = await handover(client, "900.00")
    view = await pay_workspace(client, profile)
    response = await client.post(f"/api/manager/worker-pay/{profile}/offsets", headers=headers(), json=cash(view["version"], "200.00"))
    assert response.status_code in (400, 409), response.text
    await ok_post(client, f"/api/installer/money/handovers/{pending['id']}/cancel", command(pending["version"]), worker_headers())
    _, offset = await settle(client, profile, kind="offsets")
    view = await cash_workspace(client)
    path = f"/api/manager/worker-money/{profile}/receipts/{receipt['id']}/reverse"
    response = await client.post(path, headers=headers(), json=command(view["version"], reason="Ошибка получения"))
    assert response.status_code == 409, response.text
    pay = await pay_workspace(client, profile)
    await ok_post(client, f"/api/manager/worker-pay/{profile}/payouts/{offset['id']}/reverse", command(pay["version"], reason="Исправление зачёта"))
    view = await cash_workspace(client)
    await ok_post(client, path, command(view["version"], reason="Ошибка получения"))
    final = await cash_workspace(client)
    assert sum((Decimal(row["held"]) for row in final["balances"]), Decimal(0)) == 0


async def test_confirmed_handover_correction_preserves_original_and_client_payment(pay_db):
    session, client = pay_db
    await receive(client, "1000.00")
    _, pending = await handover(client, "800.00")
    profile = (await cash_workspace(client))["worker_profile_id"]
    await ok_post(client, f"/api/manager/worker-money/{profile}/handovers/{pending['id']}/confirm", command(pending["version"]))
    assert cash_balance(await cash_workspace(client))["held"] == "200.00"
    original = await session.get(WorkerCashHandover, pending["id"])
    original_recipient, original_resolved_at = original.recipient_staff_user_id, original.resolved_at
    view = await cash_workspace(client)
    path = f"/api/manager/worker-money/{profile}/handovers/{pending['id']}/reverse"
    payload = command(view["version"], reason="Получатель сообщил об ошибке")
    result = await ok_post(client, path, payload)
    assert await ok_post(client, path, payload) == result
    assert cash_balance(await cash_workspace(client))["held"] == "1000.00"
    original = await session.get(WorkerCashHandover, pending["id"])
    assert original.status == "reversed" and original.amount == Decimal("800.00")
    assert original.recipient_staff_user_id == original_recipient and original.resolved_at == original_resolved_at
    assert original.reversed_at is not None and original.reversal_reason == payload["reason"]
    assert len(list((await session.scalars(select(Payment))).all())) == 1
    history = await cash_workspace(client)
    assert {item["kind"] for item in history["items"]} >= {"handover", "handover_reversal"}


@pytest.mark.parametrize("kind", ["payouts", "offsets"])
async def test_failure_before_durable_settlement_rolls_back_pay_and_cash_together(pay_db, kind):
    session, client = pay_db
    assignment, _, _ = await receive(client, "1000.00")
    profile, row, _, _ = await agree(client, assignment_id=assignment)
    await accrue(client, profile, row["id"])
    view = await pay_workspace(client, profile)
    engine = session.bind.sync_engine

    def fail_command(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith("insert into worker_money_command"):
            raise RuntimeError("injected failure before durable settlement")

    event.listen(engine, "before_cursor_execute", fail_command)
    try:
        async with AsyncClient(transport=ASGITransport(app=client._transport.app, raise_app_exceptions=False), base_url="http://test") as failing:
            response = await failing.post(f"/api/manager/worker-pay/{profile}/{kind}", headers=headers(), json=cash(view["version"], "200.00"))
        assert response.status_code == 500, response.text
    finally:
        event.remove(engine, "before_cursor_execute", fail_command)
        await session.rollback()
    assert await session.scalar(select(WorkerPayPayout.id)) is None
    assert await session.scalar(select(WorkerPayPayoutAllocation.payout_id)) is None
    assert await session.scalar(select(WorkerPayOffsetCashAllocation.payout_id)) is None
    assert pay_balance(await pay_workspace(client))["owed"] == "200.00"
    assert cash_balance(await cash_workspace(client))["held"] == "1000.00"


@pytest.mark.parametrize("change", ["closed", "revoked"])
async def test_own_pay_history_survives_work_access_loss_and_hides_commercial_data(pay_db, change):
    session, client = pay_db
    profile, row, payload, _ = await agree(client)
    await accrue(client, profile, row["id"])
    await settle(client, profile, "50.25")
    if change == "closed":
        (await session.get(Order, 100)).status = "closed"
    else:
        (await session.get(OrderWorkAssignment, payload["assignment_id"])).revoked_at = datetime.now()
    await session.commit()
    response = await client.get("/api/installer/pay", headers=worker_headers())
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    view = response.json()
    assert pay_balance(view)["owed"] == "149.75" and len(view["agreements"]) == 1
    assert "PRIVATE" not in response.text
    for key in ("cost_byn_amount", "cost", "margin", "payments", "customer_phone", "financial_fingerprint", "suppliers", "comment"):
        assert f'"{key}"' not in response.text
    assert (await client.get(f"/api/installer/works/{payload['assignment_id']}", headers=worker_headers())).status_code == 404
    other = await pay_workspace(client, actor=worker_headers(staff_id=20))
    assert other["agreements"] == [] and other["items"] == []
    foreign = await pay_workspace(client, actor=worker_headers(site="second"))
    assert foreign["agreements"] == [] and foreign["items"] == []
    session.add(TenantMembership(tenant_id=2, staff_user_id=22, role="installer"))
    await session.commit()
    tenant = await pay_workspace(client, actor=worker_headers(tenant=2))
    assert tenant["agreements"] == [] and tenant["items"] == []
    assert (await client.get(f"/api/manager/worker-pay/{profile}", headers={**headers(), "X-MVN-Manager-Storefront": "second"})).status_code == 404


@pytest.mark.parametrize("disabled", ["staff", "membership", "profile"])
async def test_company_can_settle_debt_after_worker_disabled(pay_db, disabled):
    session, client = pay_db
    profile, row, _, _ = await agree(client)
    await accrue(client, profile, row["id"])
    if disabled == "staff":
        (await session.get(StaffUser, 22)).status = "inactive"
    elif disabled == "profile":
        (await session.get(TenantWorkerProfile, profile)).status = "disabled"
    else:
        member = await session.scalar(select(TenantMembership).where(TenantMembership.tenant_id == 1, TenantMembership.staff_user_id == 22))
        member.status = "disabled"
    await session.commit()
    await settle(client, profile)
    assert pay_balance(await pay_workspace(client, profile))["owed"] == "0.00"
    own = await client.get("/api/installer/pay", headers=worker_headers())
    if disabled == "profile":
        # Suspending work access preserves safe personal financial history while
        # active staff identity and real membership still authorize the read.
        assert own.status_code == 200 and pay_balance(own.json())["owed"] == "0.00"
    else:
        assert own.status_code in (401, 403)


async def test_pay_reads_are_read_only_and_bound_page_size(pay_db):
    session, client = pay_db
    statements = []

    def inspect(state):
        statements.append(state.statement)

    event.listen(session.sync_session, "do_orm_execute", inspect)
    try:
        own = await client.get("/api/installer/pay", headers=worker_headers())
        company = await client.get("/api/manager/worker-pay", headers=headers())
        order = await client.get("/api/manager/orders/100/worker-pay", headers=headers())
    finally:
        event.remove(session.sync_session, "do_orm_execute", inspect)
    assert own.status_code == company.status_code == order.status_code == 200
    assert own.json()["items"] == own.json()["agreements"] == company.json()["items"] == []
    assert await session.scalar(select(WorkerCashAccount.id)) is None
    assert all(getattr(statement, "_for_update_arg", None) is None and not getattr(statement, "is_dml", False) for statement in statements)
    for path in ("/api/installer/pay?limit=101", "/api/manager/worker-pay?limit=101"):
        assert (await client.get(path, headers=worker_headers() if "/installer/" in path else headers())).status_code == 422


@pytest.mark.parametrize("grant", ["worker.pay.manage", "worker.money.manage"])
async def test_offset_requires_both_actual_financial_grants(pay_db, grant):
    session, client = pay_db
    assignment, _, _ = await receive(client, "1000.00")
    profile, row, _, _ = await agree(client, assignment_id=assignment)
    await accrue(client, profile, row["id"])
    view = await pay_workspace(client, profile)
    member = await session.get(TenantMembership, 10)
    member.permissions = [grant]
    await session.commit()
    response = await client.post(f"/api/manager/worker-pay/{profile}/offsets", headers=headers(), json=cash(view["version"], "200.00"))
    assert response.status_code == 403, response.text
    assert await session.scalar(select(WorkerPayPayout.id)) is None
    assert cash_balance(await cash_workspace(client))["held"] == "1000.00"


async def test_committed_payout_replay_rechecks_current_actor_grant(pay_db):
    session, client = pay_db
    profile, row, _, _ = await agree(client)
    await accrue(client, profile, row["id"])
    payload, _ = await settle(client, profile)
    member = await session.get(TenantMembership, 10)
    member.permissions = ["worker.money.manage"]
    await session.commit()
    response = await client.post(f"/api/manager/worker-pay/{profile}/payouts", headers=headers(), json=payload)
    assert response.status_code == 403, response.text
    assert len(list((await session.scalars(select(WorkerPayPayout))).all())) == 1


async def test_platform_support_reads_foreign_pay_but_cannot_be_financial_actor(pay_db):
    session, client = pay_db
    profile = TenantWorkerProfile(tenant_id=2, staff_user_id=25)
    session.add(profile)
    await session.flush()
    account = WorkerCashAccount(tenant_id=2, storefront_id=2, worker_profile_id=profile.id, version=2)
    session.add(account)
    await session.flush()
    agreement = WorkerPayAgreement(account_id=account.id, tenant_id=2, storefront_id=2, order_id=200, assignment_reference=999, work_key="order", title="Монтаж", amount=Decimal("100.00"), currency="BYN", cost_byn_amount=Decimal("100.00"), status="accrued", version=1)
    session.add(agreement)
    await session.commit()
    actor = headers(4, 2)
    response = await client.get(f"/api/manager/worker-pay/{profile.id}", headers=actor)
    assert response.status_code == 200, response.text
    assert response.json()["can_manage"] is False and pay_balance(response.json())["owed"] == "100.00"
    for path, body in [
        (f"/api/manager/worker-pay/{profile.id}/payouts", cash(2, "100.00")),
        (f"/api/manager/worker-pay/{profile.id}/agreements/{agreement.id}/cancel", command(2, expected_agreement_version=1, reason="Недопустимое действие поддержки")),
    ]:
        response = await client.post(path, headers=actor, json=body)
        assert response.status_code == 403, response.text
    assert await session.scalar(select(WorkerPayPayout.id)) is None
    assert (await client.get("/api/installer/pay", headers=actor)).status_code == 403
