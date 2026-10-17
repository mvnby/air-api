"""Worker cash commands through real authentication, routes and database transactions."""

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select

from models import (
    Order,
    OrderWorkAssignment,
    Payment,
    StaffUser,
    Tenant,
    TenantMembership,
)
from tests.unit.test_installer_workspace import (
    assign,
    installer_headers,
    instruction,
    workspace_db as workspace_db,
)
from tests.unit.test_manager_multicompany import multi_db as multi_db
from tests.unit.test_order_responsibility import (
    headers,
    responsibility_db as responsibility_db,
)


@pytest.fixture
async def money_db(workspace_db):  # noqa: F811 - imported shared fixture
    from routers.manager_orders_write import router as order_write_router
    from routers.worker_money import installer_router, manager_router

    session, original = workspace_db
    app = original._transport.app
    app.include_router(installer_router)
    app.include_router(manager_router)
    app.include_router(order_write_router)
    member = await session.get(TenantMembership, 10)
    member.permissions = [*member.permissions, "worker.money.manage"]
    await session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield session, client


def command(version=0, **kwargs):
    return {"idempotency_key": str(uuid4()), "expected_version": version, **kwargs}


def cash(version=0, amount="10.25", currency="BYN", **kwargs):
    return command(version, amount=amount, currency=currency, **kwargs)


def worker_headers(**kwargs):
    return {
        **installer_headers(**kwargs),
        "Origin": "http://test",
        "X-Kitlane-Team": "1",
    }


async def prepare(client, amount="100.00", currency="BYN"):
    view = await assign(client)
    result = await client.put(
        "/api/manager/orders/100/installer-workspace/collection",
        headers=headers(),
        json=instruction(view, amount, currency=currency),
    )
    assert result.status_code == 200, result.text
    data = result.json()
    return data["assignments"][0]["id"], data["collection"]["version"]


async def receive(client, amount="100.00", currency="BYN"):
    assignment_id, version = await prepare(client, amount, currency)
    payload = cash(version, amount, currency)
    response = await client.post(
        f"/api/installer/works/{assignment_id}/collections",
        headers=worker_headers(),
        json=payload,
    )
    assert response.status_code in (200, 201), response.text
    return assignment_id, payload, response.json()


async def workspace(client, **kwargs):
    response = await client.get(
        "/api/installer/money", headers=worker_headers(**kwargs)
    )
    assert response.status_code == 200, response.text
    return response.json()


def balance(data, currency="BYN"):
    return next(row for row in data["balances"] if row["currency"] == currency)


async def handover(client, amount="50.00", recipient=10):
    view = await workspace(client)
    payload = cash(view["version"], amount, recipient_staff_user_id=recipient)
    response = await client.post(
        "/api/installer/money/handovers", headers=worker_headers(), json=payload
    )
    assert response.status_code in (200, 201), response.text
    return payload, response.json()


async def test_received_payment_exact_and_durable_replay_consumes_instruction(money_db):
    session, client = money_db
    assignment_id, payload, result = await receive(client, "10.25")
    payments = list(
        (await session.scalars(select(Payment).where(Payment.order_id == 100))).all()
    )
    assert len(payments) == 1
    assert Decimal(str(payments[0].amount)) == Decimal("10.25")
    assert payments[0].currency == "BYN"
    path = f"/api/installer/works/{assignment_id}/collections"
    replay = await client.post(path, headers=worker_headers(), json=payload)
    assert replay.status_code in (200, 201) and replay.json() == result
    changed = await client.post(
        path, headers=worker_headers(), json={**payload, "amount": "1.00"}
    )
    assert changed.status_code == 409, changed.text
    stale = await client.post(
        path,
        headers=worker_headers(),
        json={**payload, "idempotency_key": str(uuid4())},
    )
    assert stale.status_code == 409, stale.text
    assert len(list((await session.scalars(select(Payment))).all())) == 1
    current = (
        await client.get(
            f"/api/installer/works/{assignment_id}", headers=worker_headers()
        )
    ).json()
    assert current["collection"]["amount"] == "0.00"
    assert current["collection"]["version"] > payload["expected_version"]
    data = await workspace(client)
    assert (
        balance(data)["received"] == "10.25" and balance(data)["available"] == "10.25"
    )


async def test_partial_receipt_refreshes_remaining_snapshot_and_next_version(money_db):
    session, client = money_db
    assignment_id, version = await prepare(client)
    path = f"/api/installer/works/{assignment_id}/collections"
    first = await client.post(
        path, headers=worker_headers(), json=cash(version, "40.25")
    )
    assert first.status_code in (200, 201), first.text
    detail = (
        await client.get(
            f"/api/installer/works/{assignment_id}", headers=worker_headers()
        )
    ).json()
    assert detail["collection"]["amount"] == "59.75"
    assert detail["collection"]["status"] == "ready"
    second = await client.post(
        path,
        headers=worker_headers(),
        json=cash(detail["collection"]["version"], "59.75"),
    )
    assert second.status_code in (200, 201), second.text
    assert sum(
        Decimal(str(p.amount)) for p in (await session.scalars(select(Payment))).all()
    ) == Decimal("100.00")
    assert balance(await workspace(client))["held"] == "100.00"


@pytest.mark.parametrize(
    "amount,currency",
    [("0", "BYN"), ("-1", "BYN"), ("0.001", "BYN"), ("NaN", "BYN"), ("1", "RUB")],
)
async def test_receipt_requires_positive_exact_supported_money(
    money_db, amount, currency
):
    session, client = money_db
    assignment_id, version = await prepare(client)
    response = await client.post(
        f"/api/installer/works/{assignment_id}/collections",
        headers=worker_headers(),
        json=cash(version, amount, currency),
    )
    assert response.status_code == 422, response.text
    assert await session.scalar(select(Payment.id)) is None


@pytest.mark.parametrize(
    "change",
    [
        "over_limit",
        "wrong_currency",
        "new_payment",
        "wrong_collector",
        "revoked",
        "closed",
        "site",
        "tenant",
        "disabled_member",
        "disabled_profile",
        "disabled_staff",
    ],
)
async def test_receipt_fails_closed_without_payment(money_db, change):
    session, client = money_db
    assignment_id, version = await prepare(client)
    payload, actor = cash(version), worker_headers()
    if change == "over_limit":
        payload["amount"] = "100.01"
    elif change == "wrong_currency":
        payload["currency"] = "EUR"
    elif change == "new_payment":
        session.add(Payment(order_id=100, amount=1, currency="BYN"))
    elif change == "wrong_collector":
        await assign(client, 20)
        actor = worker_headers(staff_id=20)
    elif change == "revoked":
        from datetime import datetime

        (
            await session.get(OrderWorkAssignment, assignment_id)
        ).revoked_at = datetime.now()
    elif change == "closed":
        (await session.get(Order, 100)).status = "closed"
    elif change == "site":
        actor = worker_headers(site="second")
    elif change == "disabled_member":
        member = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == 1, TenantMembership.staff_user_id == 22
            )
        )
        member.status = "disabled"
    elif change == "disabled_profile":
        from models import TenantWorkerProfile

        profile = await session.scalar(
            select(TenantWorkerProfile).where(
                TenantWorkerProfile.staff_user_id == 22,
                TenantWorkerProfile.tenant_id == 1,
            )
        )
        profile.status = "disabled"
    elif change == "disabled_staff":
        (await session.get(StaffUser, 22)).status = "inactive"
    else:
        # A genuine active membership in another tenant cannot spend the first tenant's instruction.
        session.add(TenantMembership(tenant_id=2, staff_user_id=22, role="installer"))
        actor = worker_headers(tenant=2)
    await session.commit()
    response = await client.post(
        f"/api/installer/works/{assignment_id}/collections", headers=actor, json=payload
    )
    if change in ("site", "tenant", "wrong_collector"):
        assert response.status_code == 404, response.text
    else:
        assert response.status_code in (400, 401, 403, 404, 409), response.text
    payments = list((await session.scalars(select(Payment))).all())
    assert len(payments) == (1 if change == "new_payment" else 0)


@pytest.mark.parametrize("change", ["revoked", "closed"])
async def test_own_cash_history_survives_work_loss_without_commercial_data(
    money_db, change
):
    session, client = money_db
    assignment_id, _, receipt = await receive(client)
    if change == "closed":
        (await session.get(Order, 100)).status = "closed"
    else:
        from datetime import datetime

        (
            await session.get(OrderWorkAssignment, assignment_id)
        ).revoked_at = datetime.now()
    await session.commit()
    response = await client.get("/api/installer/money", headers=worker_headers())
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert any(
        item["id"] == receipt["id"] and item["kind"] == "client_receipt"
        for item in response.json()["items"]
    )
    assert "PRIVATE" not in response.text
    for field in (
        "margin",
        "cost",
        "payments",
        "customer_phone",
        "financial_fingerprint",
        "comment",
    ):
        assert f'"{field}"' not in response.text
    other = await workspace(client, staff_id=20)
    assert other["items"] == []
    assert (
        await client.get("/api/installer/money?limit=101", headers=worker_headers())
    ).status_code == 422
    assert (
        await client.get("/api/manager/worker-money?limit=101", headers=headers())
    ).status_code == 422
    assert (
        await client.get(
            "/api/installer/money/recipients?limit=101", headers=worker_headers()
        )
    ).status_code == 422


async def test_recipients_follow_live_actual_membership_and_management_permission(
    money_db,
):
    session, client = money_db
    response = await client.get(
        "/api/installer/money/recipients", headers=worker_headers()
    )
    assert response.status_code == 200, response.text
    assert {p["staff_user_id"] for p in response.json()["items"]} == {4, 10}
    member = await session.get(TenantMembership, 10)
    member.permissions = []
    await session.commit()
    result = (
        await client.get("/api/installer/money/recipients", headers=worker_headers())
    ).json()
    assert {p["staff_user_id"] for p in result["items"]} == {4}
    owner = await session.get(StaffUser, 4)
    owner.status = "inactive"
    await session.commit()
    result = (
        await client.get("/api/installer/money/recipients", headers=worker_headers())
    ).json()
    assert result["items"] == []


async def test_pending_handover_reserves_funds_and_confirmation_is_exactly_once(
    money_db,
):
    session, client = money_db
    await receive(client)
    payload, created = await handover(client)
    view = await workspace(client)
    assert balance(view) == {
        "currency": "BYN",
        "received": "100.00",
        "offset": "0.00",
        "handed_over": "0.00",
        "held": "100.00",
        "pending": "50.00",
        "available": "50.00",
    }
    replay = await client.post(
        "/api/installer/money/handovers", headers=worker_headers(), json=payload
    )
    assert replay.status_code in (200, 201) and replay.json() == created
    overdraw = await client.post(
        "/api/installer/money/handovers",
        headers=worker_headers(),
        json=cash(view["version"], "50.01", recipient_staff_user_id=10),
    )
    assert overdraw.status_code in (400, 409), overdraw.text
    path = f"/api/manager/worker-money/{view['worker_profile_id']}/handovers/{created['id']}/confirm"
    action = command(created["version"])
    wrong_recipient = await client.post(path, headers=headers(4), json=action)
    assert wrong_recipient.status_code == 403, wrong_recipient.text
    confirmed = await client.post(path, headers=headers(), json=action)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    assert (
        await client.post(path, headers=headers(), json=action)
    ).json() == confirmed.json()
    final = await workspace(client)
    assert balance(final)["held"] == "50.00" and balance(final)["pending"] == "0.00"
    assert (
        balance(final)["handed_over"] == "50.00"
        and balance(final)["available"] == "50.00"
    )
    assert len(list((await session.scalars(select(Payment))).all())) == 1


@pytest.mark.parametrize("action,actor", [("cancel", "worker"), ("reject", "manager")])
async def test_pending_handover_release_preserves_cash_and_replay(
    money_db, action, actor
):
    _, client = money_db
    await receive(client)
    _, created = await handover(client, "100.00")
    view = await workspace(client)
    path = (
        f"/api/installer/money/handovers/{created['id']}/cancel"
        if actor == "worker"
        else f"/api/manager/worker-money/{view['worker_profile_id']}/handovers/{created['id']}/reject"
    )
    payload = command(created["version"])
    response = await client.post(
        path, headers=worker_headers() if actor == "worker" else headers(), json=payload
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == (
        "cancelled" if action == "cancel" else "rejected"
    )
    assert (
        await client.post(
            path,
            headers=worker_headers() if actor == "worker" else headers(),
            json=payload,
        )
    ).json() == response.json()
    final = await workspace(client)
    assert (
        balance(final)["available"] == "100.00" and balance(final)["pending"] == "0.00"
    )
    assert (
        balance(final)["held"] == "100.00" and balance(final)["handed_over"] == "0.00"
    )


async def test_manager_correction_refuses_reserved_money_then_immutable_negative_payment(
    money_db,
):
    session, client = money_db
    _, _, receipt = await receive(client)
    _, pending = await handover(client, "10.00")
    view = await workspace(client)
    path = f"/api/manager/worker-money/{view['worker_profile_id']}/receipts/{receipt['id']}/reverse"
    denied = await client.post(
        path,
        headers=headers(),
        json=command(view["version"], reason="Ошибка получения"),
    )
    assert denied.status_code == 409, denied.text
    cancelled = await client.post(
        f"/api/installer/money/handovers/{pending['id']}/cancel",
        headers=worker_headers(),
        json=command(pending["version"]),
    )
    assert cancelled.status_code == 200, cancelled.text
    view = await workspace(client)
    payload = command(view["version"], reason="Ошибка получения")
    response = await client.post(path, headers=headers(), json=payload)
    assert response.status_code in (200, 201), response.text
    assert response.json()["kind"] == "receipt_reversal"
    replay = await client.post(path, headers=headers(), json=payload)
    assert replay.status_code in (200, 201) and replay.json() == response.json()
    payments = list((await session.scalars(select(Payment).order_by(Payment.id))).all())
    assert [Decimal(str(row.amount)) for row in payments] == [
        Decimal("100.00"),
        Decimal("-100.00"),
    ]
    final = await workspace(client)
    assert sum((Decimal(row["held"]) for row in final["balances"]), Decimal(0)) == 0
    for payment in payments:
        removed = await client.delete(
            f"/api/manager/orders/100/payments/{payment.id}", headers=headers()
        )
        assert removed.status_code in (400, 409), removed.text
    assert len(list((await session.scalars(select(Payment))).all())) == 2


async def test_mutation_live_acl_demo_and_stale_auth(money_db):
    session, client = money_db
    assignment_id, version = await prepare(client)
    path = f"/api/installer/works/{assignment_id}/collections"
    tenant = await session.get(Tenant, 1)
    tenant.demo_read_only = True
    await session.commit()
    response = await client.post(path, headers=worker_headers(), json=cash(version))
    assert response.status_code == 403, response.text
    tenant.demo_read_only = False
    (await session.get(StaffUser, 22)).auth_version += 1
    await session.commit()
    response = await client.post(path, headers=worker_headers(), json=cash(version))
    assert response.status_code == 401, response.text
    assert await session.scalar(select(Payment.id)) is None


async def test_foreign_money_ids_hidden_and_permission_revocation_blocks_actions(
    money_db,
):
    session, client = money_db
    await receive(client)
    _, pending = await handover(client)
    view = await workspace(client)
    profile = view["worker_profile_id"]
    path = f"/api/manager/worker-money/{profile}/handovers/{pending['id']}/confirm"
    member = await session.get(TenantMembership, 10)
    member.permissions = []
    await session.commit()
    denied = await client.post(
        path, headers=headers(), json=command(pending["version"])
    )
    assert denied.status_code == 403, denied.text
    assert (
        await client.get(
            f"/api/manager/worker-money/{profile + 9999}", headers=headers(4)
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/manager/worker-money/{profile}",
            headers={**headers(4), "X-MVN-Manager-Storefront": "second"},
        )
    ).status_code == 404
    other_cancel = await client.post(
        f"/api/installer/money/handovers/{pending['id']}/cancel",
        headers=worker_headers(staff_id=20),
        json=command(pending["version"]),
    )
    assert other_cancel.status_code == 404, other_cancel.text
    assert balance(await workspace(client))["pending"] == "50.00"


async def test_money_reads_do_not_create_accounts_or_lock_rows(money_db):
    session, client = money_db
    statements = []

    def inspect(state):
        statements.append(state.statement)

    event.listen(session.sync_session, "do_orm_execute", inspect)
    try:
        own = await client.get("/api/installer/money", headers=worker_headers())
        overview = await client.get("/api/manager/worker-money", headers=headers())
        recipients = await client.get(
            "/api/installer/money/recipients", headers=worker_headers()
        )
    finally:
        event.remove(session.sync_session, "do_orm_execute", inspect)
    assert own.status_code == overview.status_code == recipients.status_code == 200
    assert own.json()["items"] == [] and own.json()["worker_profile_id"] is None
    assert overview.json()["items"] == []
    assert all(
        getattr(statement, "_for_update_arg", None) is None
        and not getattr(statement, "is_dml", False)
        for statement in statements
    )


async def test_receipt_failure_rolls_back_payment_instruction_and_cash_together(
    money_db,
):
    from models.installer_publication import InstallerCollectionInstruction
    from models.worker_money import (
        WorkerCashAccount,
        WorkerCashReceipt,
        WorkerMoneyCommand,
    )

    session, client = money_db
    assignment_id, version = await prepare(client)
    engine = session.bind.sync_engine

    def fail_command(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith("insert into worker_money_command"):
            raise RuntimeError("injected failure before durable receipt")

    event.listen(engine, "before_cursor_execute", fail_command)
    try:
        async with AsyncClient(
            transport=ASGITransport(
                app=client._transport.app, raise_app_exceptions=False
            ),
            base_url="http://test",
        ) as failing_client:
            result = await failing_client.post(
                f"/api/installer/works/{assignment_id}/collections",
                headers=worker_headers(),
                json=cash(version),
            )
        assert result.status_code == 500, result.text
    finally:
        event.remove(engine, "before_cursor_execute", fail_command)
        await session.rollback()
    assert await session.scalar(select(Payment.id)) is None
    assert await session.scalar(select(WorkerCashReceipt.id)) is None
    assert await session.scalar(select(WorkerMoneyCommand.id)) is None
    assert await session.scalar(select(WorkerCashAccount.id)) is None
    collection = await session.scalar(
        select(InstallerCollectionInstruction).where(
            InstallerCollectionInstruction.order_id == 100
        )
    )
    assert collection.version == version and collection.amount == Decimal("100.00")


async def test_cash_currencies_never_convert_or_cover_each_others_reserve(money_db):
    _, client = money_db
    await receive(client, "20.25", "EUR")
    view = await workspace(client)
    wrong = await client.post(
        "/api/installer/money/handovers",
        headers=worker_headers(),
        json=cash(view["version"], "1.00", "BYN", recipient_staff_user_id=10),
    )
    assert wrong.status_code in (400, 409), wrong.text
    response = await client.post(
        "/api/installer/money/handovers",
        headers=worker_headers(),
        json=cash(view["version"], "20.25", "EUR", recipient_staff_user_id=10),
    )
    assert response.status_code in (200, 201), response.text
    final = await workspace(client)
    assert balance(final, "EUR")["pending"] == "20.25"
    assert balance(final, "EUR")["available"] == "0.00"


@pytest.mark.parametrize("revocation", ["staff", "membership", "profile"])
async def test_committed_receipt_replay_still_requires_current_authority(
    money_db, revocation
):
    from models import TenantWorkerProfile

    session, client = money_db
    assignment_id, payload, _ = await receive(client)
    if revocation == "staff":
        (await session.get(StaffUser, 22)).status = "inactive"
    elif revocation == "membership":
        member = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == 1, TenantMembership.staff_user_id == 22
            )
        )
        member.status = "disabled"
    else:
        profile = await session.scalar(
            select(TenantWorkerProfile).where(
                TenantWorkerProfile.tenant_id == 1,
                TenantWorkerProfile.staff_user_id == 22,
            )
        )
        profile.status = "disabled"
    await session.commit()
    replay = await client.post(
        f"/api/installer/works/{assignment_id}/collections",
        headers=worker_headers(),
        json=payload,
    )
    assert replay.status_code in (401, 403), replay.text
    assert len(list((await session.scalars(select(Payment))).all())) == 1


async def test_confirmation_replay_does_not_bypass_revoked_finance_permission(money_db):
    session, client = money_db
    await receive(client)
    _, pending = await handover(client)
    view = await workspace(client)
    path = f"/api/manager/worker-money/{view['worker_profile_id']}/handovers/{pending['id']}/confirm"
    payload = command(pending["version"])
    confirmed = await client.post(path, headers=headers(), json=payload)
    assert confirmed.status_code == 200, confirmed.text
    (await session.get(TenantMembership, 10)).permissions = []
    await session.commit()
    replay = await client.post(path, headers=headers(), json=payload)
    assert replay.status_code == 403, replay.text
    assert balance(await workspace(client))["handed_over"] == "50.00"


async def test_pending_cash_allocations_block_whole_receipt_reversal_until_released(
    money_db,
):
    from models.worker_money import WorkerCashHandoverAllocation

    session, client = money_db
    _, _, first = await receive(client, "40.00")
    _, _, second = await receive(client, "60.00")
    _, pending = await handover(client, "80.00")
    view = await workspace(client)
    profile = view["worker_profile_id"]
    allocations = list(
        (
            await session.scalars(
                select(WorkerCashHandoverAllocation).order_by(
                    WorkerCashHandoverAllocation.receipt_id
                )
            )
        ).all()
    )
    assert [(row.receipt_id, row.amount) for row in allocations] == [
        (first["id"], Decimal("40.00")),
        (second["id"], Decimal("40.00")),
    ]
    manager_view = (
        await client.get(f"/api/manager/worker-money/{profile}", headers=headers())
    ).json()
    assert all(
        not entry["can_reverse"]
        for entry in manager_view["items"]
        if entry["kind"] == "client_receipt"
    )
    for receipt in (first, second):
        response = await client.post(
            f"/api/manager/worker-money/{profile}/receipts/{receipt['id']}/reverse",
            headers=headers(),
            json=command(view["version"], reason="Ошибочный приём"),
        )
        assert response.status_code == 409, response.text
    cancelled = await client.post(
        f"/api/installer/money/handovers/{pending['id']}/cancel",
        headers=worker_headers(),
        json=command(pending["version"]),
    )
    assert cancelled.status_code == 200, cancelled.text
    manager_view = (
        await client.get(f"/api/manager/worker-money/{profile}", headers=headers())
    ).json()
    assert all(
        entry["can_reverse"]
        for entry in manager_view["items"]
        if entry["kind"] == "client_receipt"
    )
    assert balance(await workspace(client))["available"] == "100.00"
