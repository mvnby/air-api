"""Real committed PostgreSQL races share a cash/pay account mutex."""

import asyncio
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from core.security import create_access_token
from models import LegacyOwnerAuthState, Payment, Tenant, TenantMembership
from models.worker_money import WorkerCashHandover
from models.worker_pay import WorkerPayAgreement, WorkerPayPayout, WorkerPayPayoutAllocation
from tests.integration.test_worker_money_concurrency import app_seed, amount


async def pay_seed(db_engine, *, received=True):
    from routers.worker_pay import installer_router, manager_router

    factory, app, order_id, assignment_id, version, worker, actor = await app_seed(db_engine)
    app.include_router(installer_router)
    app.include_router(manager_router)
    async with factory() as session:
        member = await session.scalar(select(TenantMembership).where(TenantMembership.tenant_id == 1, TenantMembership.staff_user_id == actor.staff_user_id))
        member.permissions = [*member.permissions, "worker.pay.manage"]
        await session.commit()
    manager = {
        "Authorization": "Bearer " + create_access_token({"sub": actor.username, "staff_user_id": actor.staff_user_id, "auth_version": actor.auth_version}),
        "X-MVN-Manager-Tenant": "1",
        "X-MVN-Manager-Storefront": "main",
        "Origin": "http://test",
        "X-Kitlane-Team": "1",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        if received:
            response = await client.post(f"/api/installer/works/{assignment_id}/collections", headers=worker, json=amount(version))
            assert response.status_code in (200, 201), response.text
        view = await client.get(f"/api/manager/orders/{order_id}/worker-pay", headers=manager)
        assert view.status_code == 200, view.text
        candidate = next(row for row in view.json()["candidates"] if row["assignment_id"] == assignment_id)
        response = await client.post(f"/api/manager/orders/{order_id}/worker-pay/agreements", headers=manager, json=amount(candidate["account_version"], assignment_id=assignment_id))
        assert response.status_code in (200, 201), response.text
        profile, agreement = candidate["worker_profile_id"], response.json()
        response = await client.post(f"/api/manager/worker-pay/{profile}/agreements/{agreement['id']}/accrue", headers=manager, json={"idempotency_key": amount(0)["idempotency_key"], "expected_version": agreement["account_version"], "expected_agreement_version": agreement["version"]})
        assert response.status_code in (200, 201), response.text
        version = response.json()["account_version"]
    return factory, app, order_id, profile, version, worker, manager, actor


async def race(client, requests):
    barrier = asyncio.Barrier(len(requests))

    async def post(path, headers, payload):
        await barrier.wait()
        return await client.post(path, headers=headers, json=payload)

    return await asyncio.wait_for(asyncio.gather(*(post(*request) for request in requests)), 20)


def assert_one_command(results, *, replay=False):
    successful = [response for response in results if response.status_code in (200, 201)]
    assert len(successful) == (2 if replay else 1), [(response.status_code, response.text) for response in results]
    if replay:
        assert results[0].json() == results[1].json()
    else:
        assert next(response for response in results if response not in successful).status_code == 409


@pytest.mark.parametrize("kind", ["payouts", "offsets"])
@pytest.mark.parametrize("same_key", [True, False])
async def test_concurrent_pay_command_is_exactly_once_and_never_overpays(db_engine, kind, same_key):
    factory, app, order_id, profile, version, worker, manager, _ = await pay_seed(db_engine)
    payload = amount(version)
    other = payload if same_key else amount(version)
    path = f"/api/manager/worker-pay/{profile}/{kind}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        results = await race(client, [(path, manager, payload), (path, manager, other)])
        assert_one_command(results, replay=same_key)
        pay = (await client.get("/api/installer/pay", headers=worker)).json()
        cash = (await client.get("/api/installer/money", headers=worker)).json()
        assert pay["balances"][0]["owed"] == "0.00"
        assert cash["balances"][0]["held"] == ("0.00" if kind == "offsets" else "100.00")
    async with factory() as session:
        rows = list((await session.scalars(select(WorkerPayPayout))).all())
        assert len(rows) == 1 and rows[0].amount == Decimal("100.00")
        allocations = list((await session.scalars(select(WorkerPayPayoutAllocation))).all())
        assert len(allocations) == 1 and allocations[0].amount == Decimal("100.00")
        assert len(list((await session.scalars(select(Payment).where(Payment.order_id == order_id))).all())) == 1


@pytest.mark.parametrize("competitor", ["handover", "payout"])
async def test_offset_serializes_with_cash_handover_and_company_payout(db_engine, competitor):
    factory, app, _, profile, version, worker, manager, actor = await pay_seed(db_engine)
    offset_path = f"/api/manager/worker-pay/{profile}/offsets"
    other = (
        ("/api/installer/money/handovers", worker, amount(version, recipient_staff_user_id=actor.staff_user_id))
        if competitor == "handover"
        else (f"/api/manager/worker-pay/{profile}/payouts", manager, amount(version))
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        results = await race(client, [(offset_path, manager, amount(version)), other])
        assert_one_command(results)
        pay = (await client.get("/api/installer/pay", headers=worker)).json()["balances"][0]
        cash = (await client.get("/api/installer/money", headers=worker)).json()["balances"][0]
        offset_won = results[0].status_code in (200, 201)
        assert pay["owed"] == ("100.00" if competitor == "handover" and not offset_won else "0.00")
        assert cash["held"] == ("0.00" if offset_won else "100.00")
        assert cash["pending"] == ("100.00" if competitor == "handover" and not offset_won else "0.00")
    async with factory() as session:
        payouts = list((await session.scalars(select(WorkerPayPayout))).all())
        handovers = list((await session.scalars(select(WorkerCashHandover))).all())
        assert len(payouts) + len(handovers) == 1


async def test_waiting_payout_rechecks_revoked_financial_grant(db_engine):
    factory, app, _, profile, version, _, manager, actor = await pay_seed(db_engine)
    async with factory() as admin, AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await admin.execute(select(LegacyOwnerAuthState).with_for_update())
        await admin.execute(select(Tenant).where(Tenant.id == 1).with_for_update())
        member = await admin.scalar(select(TenantMembership).where(TenantMembership.tenant_id == 1, TenantMembership.staff_user_id == actor.staff_user_id).with_for_update())
        member.permissions = []
        await admin.flush()
        task = asyncio.create_task(client.post(f"/api/manager/worker-pay/{profile}/payouts", headers=manager, json=amount(version)))
        try:
            await asyncio.sleep(0.1)
            assert not task.done()
            await admin.commit()
            denied = await asyncio.wait_for(task, 15)
            assert denied.status_code == 403, denied.text
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with factory() as session:
        assert await session.scalar(select(WorkerPayPayout.id)) is None
        assert (await session.scalar(select(WorkerPayAgreement))).status == "accrued"


async def test_actual_pay_migration_preserves_cash_and_rejects_cross_account_allocations(db_engine):
    """Run predecessor and new upgrade DDL in an isolated transactional schema."""
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    def module(name, filename):
        spec = importlib.util.spec_from_file_location(name, Path("alembic/versions") / filename)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        return migration

    cash = module("cash_before_pay", "w20261017cash01_worker_cash.py")
    pay = module("pay_migration", "w20261017pay02_worker_pay.py")
    async with db_engine.begin() as connection:
        await connection.execute(text("CREATE SCHEMA worker_pay_migration_test"))
        await connection.execute(text("SET LOCAL search_path TO worker_pay_migration_test"))
        for ddl in [
            "CREATE TABLE tenant_worker_profile (id integer PRIMARY KEY,tenant_id integer NOT NULL,UNIQUE(id,tenant_id))",
            "CREATE TABLE storefront (id integer PRIMARY KEY,tenant_id integer NOT NULL,UNIQUE(id,tenant_id))",
            'CREATE TABLE "order" (id integer PRIMARY KEY,tenant_id integer NOT NULL,storefront_id integer NOT NULL,UNIQUE(id,tenant_id,storefront_id))',
            "CREATE TABLE payment (id integer PRIMARY KEY,order_id integer NOT NULL)",
            "CREATE TABLE tenant_membership (tenant_id integer NOT NULL,staff_user_id integer NOT NULL,PRIMARY KEY(tenant_id,staff_user_id))",
            "CREATE TABLE staff_users (id integer PRIMARY KEY)",
        ]:
            await connection.execute(text(ddl))
        for statement in [
            "INSERT INTO tenant_worker_profile VALUES (10,1),(20,2)",
            "INSERT INTO storefront VALUES (1,1),(2,2),(4,1)",
            'INSERT INTO "order" VALUES (100,1,1),(200,2,2),(400,1,4)',
            "INSERT INTO payment VALUES (1000,100),(2000,200)",
            "INSERT INTO tenant_membership VALUES (1,4)",
            "INSERT INTO staff_users VALUES (4)",
        ]:
            await connection.execute(text(statement))

        def upgrade(sync, migration):
            migration.op = Operations(MigrationContext.configure(sync))
            migration.upgrade()

        await connection.run_sync(upgrade, cash)
        for statement in [
            "INSERT INTO worker_cash_account (id,tenant_id,storefront_id,worker_profile_id,version) VALUES (1,1,1,10,3),(2,2,2,20,0),(3,1,4,10,0)",
            "INSERT INTO worker_cash_receipt (id,account_id,tenant_id,storefront_id,order_id,assignment_reference,collection_version,amount,currency,title,payment_id,created_at) VALUES (1,1,1,1,100,7,1,100,'BYN','Original client receipt',1000,now()),(2,2,2,2,200,8,1,200,'BYN','Foreign client receipt',2000,now())",
            "INSERT INTO worker_cash_handover (id,account_id,tenant_id,storefront_id,recipient_staff_user_id,recipient_name,amount,currency,status,version,created_at,resolved_at) VALUES (1,1,1,1,4,'Original recipient',20,'BYN','confirmed',1,now(),now())",
            "INSERT INTO worker_cash_handover_allocation (handover_id,receipt_id,account_id,amount) VALUES (1,1,1,20)",
            "INSERT INTO worker_money_command (id,account_id,actor_staff_user_id,idempotency_key,request_hash,result,created_at) VALUES (1,1,4,'00000000-0000-0000-0000-000000000001',repeat('a',64),json_build_object('id',1),now())",
        ]:
            await connection.execute(text(statement))
        snapshots = {}
        for table, columns in {
            "worker_cash_account": "*",
            "worker_cash_receipt": "*",
            "worker_cash_handover": "id,account_id,tenant_id,storefront_id,recipient_staff_user_id,recipient_name,amount,currency,status,version,created_at,resolved_at",
            "worker_cash_handover_allocation": "*",
            "worker_money_command": "id,account_id,actor_staff_user_id,idempotency_key,request_hash,result::text,created_at",
            "payment": "*",
        }.items():
            snapshots[table] = (columns, (await connection.execute(text(f"SELECT {columns} FROM {table} ORDER BY 1"))).all())
        await connection.run_sync(upgrade, pay)
        for table, (columns, before) in snapshots.items():
            assert (await connection.execute(text(f"SELECT {columns} FROM {table} ORDER BY 1"))).all() == before
        assert (await connection.execute(text('SELECT id,worker_pay_cost_byn FROM "order" ORDER BY id'))).all() == [(100, Decimal("0.00")), (200, Decimal("0.00")), (400, Decimal("0.00"))]
        assert await connection.scalar(text("SELECT count(*) FROM worker_pay_agreement")) == 0
        assert await connection.scalar(text("SELECT count(*) FROM worker_pay_payout")) == 0

        await connection.execute(text("INSERT INTO worker_pay_agreement (id,account_id,tenant_id,storefront_id,order_id,assignment_reference,work_key,title,amount,currency,cost_byn_amount,status,version,created_at) VALUES (1,1,1,1,100,7,'order','Own work',50,'BYN',50,'accrued',1,now()),(2,2,2,2,200,8,'order','Foreign work',50,'BYN',50,'accrued',1,now())"))
        await connection.execute(text("INSERT INTO worker_pay_payout (id,account_id,tenant_id,storefront_id,amount,currency,method,version,created_at) VALUES (1,1,1,1,10,'BYN','offset',0,now()),(2,2,2,2,10,'BYN','bank',0,now())"))
        invalid = [
            "INSERT INTO worker_pay_payout_allocation VALUES (1,2,1,10)",
            "INSERT INTO worker_pay_payout_allocation VALUES (2,1,1,10)",
            "INSERT INTO worker_pay_offset_cash_allocation VALUES (1,2,1,10)",
            "INSERT INTO worker_pay_offset_cash_allocation VALUES (2,1,1,10)",
            "INSERT INTO worker_pay_agreement (id,account_id,tenant_id,storefront_id,order_id,assignment_reference,work_key,title,amount,currency,cost_byn_amount,status,version,created_at) VALUES (3,1,2,2,200,9,'stage:1','Cross account',5,'BYN',5,'agreed',0,now())",
            "INSERT INTO worker_pay_agreement (id,account_id,tenant_id,storefront_id,order_id,assignment_reference,work_key,title,amount,currency,cost_byn_amount,status,version,created_at) VALUES (3,1,1,1,100,9,'order','Duplicate work',5,'BYN',5,'agreed',0,now())",
        ]
        for statement in invalid:
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(text(statement))
        await connection.execute(text("INSERT INTO worker_pay_payout_allocation VALUES (1,1,1,10)"))
        await connection.execute(text("INSERT INTO worker_pay_offset_cash_allocation VALUES (1,1,1,10)"))
        with pytest.raises(RuntimeError, match="financial history"):
            pay.downgrade()
        assert await connection.scalar(text("SELECT count(*) FROM worker_cash_receipt")) == 2
        assert await connection.scalar(text("SELECT count(*) FROM payment")) == 2
        await connection.execute(text("SET LOCAL search_path TO public"))
        await connection.execute(text("DROP SCHEMA worker_pay_migration_test CASCADE"))
