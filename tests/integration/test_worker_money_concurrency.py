"""Cash races use committed seeds and independent physical PostgreSQL sessions."""

import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from core.database import get_session
from core.security import create_access_token
from models import (
    OrderWorkAssignment,
    Payment,
    StaffUser,
    TenantMembership,
    TenantWorkerProfile,
)
from models.worker_money import WorkerCashHandover, WorkerCashReceipt
from services.installer_collection_service import (
    InstallerCollectionService as Collection,
)
from tests.integration.test_installer_collection_concurrency import (
    setup_collection,
    instruction,
)


async def app_seed(db_engine):
    from routers.worker_money import installer_router, manager_router

    assert db_engine.dialect.name == "postgresql"
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor, order_id, assignment_id, workspace = await setup_collection(factory)
    async with factory() as session:
        await Collection.update(
            session,
            auth=actor,
            order_id=order_id,
            payload=instruction(workspace, assignment_id),
        )
        member = await session.scalar(
            select(TenantMembership).where(
                TenantMembership.staff_user_id == actor.staff_user_id,
                TenantMembership.tenant_id == 1,
            )
        )
        member.permissions = ["worker.money.manage"]
        person = await session.scalar(
            select(StaffUser)
            .join(
                TenantWorkerProfile, TenantWorkerProfile.staff_user_id == StaffUser.id
            )
            .join(
                OrderWorkAssignment,
                OrderWorkAssignment.worker_profile_id == TenantWorkerProfile.id,
            )
            .where(OrderWorkAssignment.id == assignment_id)
        )
        installer = {
            "Authorization": "Bearer "
            + create_access_token(
                {
                    "sub": person.username,
                    "staff_user_id": person.id,
                    "auth_version": person.auth_version,
                }
            ),
            "X-MVN-Manager-Tenant": "1",
            "X-MVN-Manager-Storefront": "main",
            "Origin": "http://test",
            "X-Kitlane-Team": "1",
        }
        await session.commit()
    app = FastAPI()
    app.include_router(installer_router)
    app.include_router(manager_router)

    async def session_dependency():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_dependency
    return (
        factory,
        app,
        order_id,
        assignment_id,
        workspace.collection.version + 1,
        installer,
        actor,
    )


def amount(version, value="100.00", **kwargs):
    return {
        "idempotency_key": str(uuid4()),
        "expected_version": version,
        "amount": value,
        "currency": "BYN",
        **kwargs,
    }


@pytest.mark.parametrize("same_key", [True, False])
async def test_concurrent_receipt_is_one_payment_and_one_cash_record(
    db_engine, same_key
):
    factory, app, order_id, assignment_id, version, worker, _ = await app_seed(
        db_engine
    )
    payload = amount(version)
    other = payload if same_key else {**payload, "idempotency_key": str(uuid4())}
    barrier = asyncio.Barrier(2)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def collect(body):
            await barrier.wait()
            return await client.post(
                f"/api/installer/works/{assignment_id}/collections",
                headers=worker,
                json=body,
            )

        results = await asyncio.wait_for(
            asyncio.gather(collect(payload), collect(other)), 20
        )
        successful = [result for result in results if result.status_code in (200, 201)]
        assert len(successful) == (2 if same_key else 1), [
            (r.status_code, r.text) for r in results
        ]
        if same_key:
            assert results[0].json() == results[1].json()
        else:
            assert next(r for r in results if r not in successful).status_code == 409
    async with factory() as session:
        assert (
            len(
                list(
                    (
                        await session.scalars(
                            select(Payment).where(Payment.order_id == order_id)
                        )
                    ).all()
                )
            )
            == 1
        )
        assert (
            len(
                list(
                    (
                        await session.scalars(
                            select(WorkerCashReceipt).where(
                                WorkerCashReceipt.order_id == order_id
                            )
                        )
                    ).all()
                )
            )
            == 1
        )


@pytest.mark.parametrize("same_key", [True, False])
async def test_concurrent_handover_reserves_at_most_available_cash(db_engine, same_key):
    factory, app, _, assignment_id, version, worker, manager = await app_seed(db_engine)
    barrier = asyncio.Barrier(2)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        received = await client.post(
            f"/api/installer/works/{assignment_id}/collections",
            headers=worker,
            json=amount(version),
        )
        assert received.status_code in (200, 201), received.text
        view = (await client.get("/api/installer/money", headers=worker)).json()
        payload = amount(view["version"], recipient_staff_user_id=manager.staff_user_id)
        other = payload if same_key else {**payload, "idempotency_key": str(uuid4())}

        async def handover(body):
            await barrier.wait()
            return await client.post(
                "/api/installer/money/handovers", headers=worker, json=body
            )

        results = await asyncio.wait_for(
            asyncio.gather(handover(payload), handover(other)), 20
        )
        successful = [result for result in results if result.status_code in (200, 201)]
        assert len(successful) == (2 if same_key else 1), [
            (r.status_code, r.text) for r in results
        ]
        if same_key:
            assert results[0].json() == results[1].json()
        else:
            assert next(r for r in results if r not in successful).status_code == 409
        final = (await client.get("/api/installer/money", headers=worker)).json()
        assert final["balances"][0]["pending"] == "100.00"
        assert final["balances"][0]["available"] == "0.00"
    async with factory() as session:
        rows = list((await session.scalars(select(WorkerCashHandover))).all())
        assert len(rows) == 1 and rows[0].status == "pending"


async def test_actual_cash_migration_enforces_scopes_and_preserves_financial_sources(
    db_engine,
):
    """Exercise upgrade DDL rather than relying on metadata-created test tables."""
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    spec = importlib.util.spec_from_file_location(
        "worker_cash_migration", Path("alembic/versions/w20261017cash01_worker_cash.py")
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    async with db_engine.begin() as connection:
        await connection.execute(text("CREATE SCHEMA worker_cash_migration_test"))
        await connection.execute(
            text("SET LOCAL search_path TO worker_cash_migration_test")
        )
        for ddl in [
            "CREATE TABLE tenant_worker_profile (id integer PRIMARY KEY,tenant_id integer NOT NULL,UNIQUE(id,tenant_id))",
            "CREATE TABLE storefront (id integer PRIMARY KEY,tenant_id integer NOT NULL,UNIQUE(id,tenant_id))",
            'CREATE TABLE "order" (id integer PRIMARY KEY,tenant_id integer NOT NULL,storefront_id integer NOT NULL,UNIQUE(id,tenant_id,storefront_id))',
            "CREATE TABLE payment (id integer PRIMARY KEY,order_id integer NOT NULL)",
            "CREATE TABLE tenant_membership (tenant_id integer NOT NULL,staff_user_id integer NOT NULL,PRIMARY KEY(tenant_id,staff_user_id))",
            "CREATE TABLE staff_users (id integer PRIMARY KEY)",
            "CREATE TABLE order_work_assignment (id integer PRIMARY KEY)",
        ]:
            await connection.execute(text(ddl))
        for seed_sql in [
            "INSERT INTO tenant_worker_profile VALUES (10,1),(20,2)",
            "INSERT INTO storefront VALUES (1,1),(2,2),(4,1)",
            'INSERT INTO "order" VALUES (100,1,1),(200,2,2),(400,1,4)',
            "INSERT INTO payment VALUES (1000,100),(1001,100),(1002,100),(2000,200)",
            "INSERT INTO tenant_membership VALUES (1,4),(2,25)",
            "INSERT INTO staff_users VALUES (4)",
            "INSERT INTO order_work_assignment VALUES (7)",
        ]:
            await connection.execute(text(seed_sql))

        def upgrade(sync):
            migration.op = Operations(MigrationContext.configure(sync))
            migration.upgrade()

        await connection.run_sync(upgrade)
        for table in (
            "worker_cash_account",
            "worker_cash_receipt",
            "worker_cash_handover",
            "worker_cash_handover_allocation",
            "worker_money_command",
        ):
            assert await connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        await connection.execute(
            text(
                "INSERT INTO worker_cash_account (id,tenant_id,storefront_id,worker_profile_id,version) VALUES (1,1,1,10,1),(2,2,2,20,0),(3,1,4,10,0)"
            )
        )
        receipt_columns = "id,account_id,tenant_id,storefront_id,order_id,assignment_reference,collection_version,amount,currency,title,payment_id,created_at"
        await connection.execute(
            text(
                f"INSERT INTO worker_cash_receipt ({receipt_columns}) VALUES (1,1,1,1,100,7,1,100.00,'BYN','Монтаж',1000,now())"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO worker_cash_handover (id,account_id,tenant_id,storefront_id,recipient_staff_user_id,recipient_name,amount,currency,status,version,created_at) VALUES (1,1,1,1,4,'Получатель',10.00,'BYN','pending',0,now())"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO worker_cash_handover_allocation (handover_id,receipt_id,account_id,amount) VALUES (1,1,1,10.00)"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO worker_money_command (id,account_id,actor_staff_user_id,idempotency_key,request_hash,result,created_at) VALUES (1,1,4,:key,:hash,'{}',now())"
            ),
            {"key": str(uuid4()), "hash": "a" * 64},
        )

        invalid_writes = [
            # A profile from tenant 1 cannot own tenant 2's money account.
            "INSERT INTO worker_cash_account (id,tenant_id,storefront_id,worker_profile_id,version) VALUES (4,2,2,10,0)",
            # Matching tenant/profile still cannot use another tenant's storefront.
            "INSERT INTO worker_cash_account (id,tenant_id,storefront_id,worker_profile_id,version) VALUES (4,2,1,20,0)",
            # Receipt/account, receipt/order and Payment/order all carry scope.
            f"INSERT INTO worker_cash_receipt ({receipt_columns}) VALUES (2,2,1,1,100,7,2,10,'BYN','Work',1002,now())",
            f"INSERT INTO worker_cash_receipt ({receipt_columns}) VALUES (2,1,1,1,400,7,2,10,'BYN','Work',1002,now())",
            f"INSERT INTO worker_cash_receipt ({receipt_columns}) VALUES (2,1,1,1,100,7,2,10,'BYN','Work',2000,now())",
            # One consumed instruction may create only one receipt.
            f"INSERT INTO worker_cash_receipt ({receipt_columns}) VALUES (2,1,1,1,100,7,1,10,'BYN','Work',1002,now())",
            # Handover recipient must really belong to that company.
            "UPDATE worker_cash_handover SET recipient_staff_user_id=25 WHERE id=1",
            # Allocation cannot join a receipt and handover from different accounts.
            "UPDATE worker_cash_handover_allocation SET account_id=2 WHERE handover_id=1",
            # A reversal Payment cannot point at another order.
            "UPDATE worker_cash_receipt SET reversal_payment_id=2000,reversed_at=now(),reversal_reason='Error' WHERE id=1",
            # Partial reversal metadata is prohibited.
            "UPDATE worker_cash_receipt SET reversal_payment_id=1001 WHERE id=1",
        ]
        for statement in invalid_writes:
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(text(statement))

        await connection.execute(
            text(
                "UPDATE worker_cash_receipt SET reversal_payment_id=1001,reversed_at=now(),reversal_reason='Error' WHERE id=1"
            )
        )
        # Deleting an expired assignment is safe: immutable financial references
        # preserve history independently of a work-access grant.
        await connection.execute(text("DELETE FROM order_work_assignment WHERE id=7"))
        for statement in [
            "DELETE FROM payment WHERE id=1000",
            "DELETE FROM payment WHERE id=1001",
            'DELETE FROM "order" WHERE id=100',
            "DELETE FROM worker_cash_account WHERE id=1",
            "DELETE FROM tenant_worker_profile WHERE id=10",
            "DELETE FROM tenant_membership WHERE tenant_id=1 AND staff_user_id=4",
            "DELETE FROM worker_cash_receipt WHERE id=1",
            "DELETE FROM worker_cash_handover WHERE id=1",
            "DELETE FROM staff_users WHERE id=4",
        ]:
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(text(statement))
        with pytest.raises(RuntimeError, match="financial history"):
            migration.downgrade()
        assert (
            await connection.scalar(text("SELECT count(*) FROM worker_cash_receipt"))
            == 1
        )
        assert (
            await connection.scalar(text("SELECT count(*) FROM worker_cash_handover"))
            == 1
        )
        assert await connection.scalar(text("SELECT count(*) FROM payment")) == 4
        await connection.execute(text("SET LOCAL search_path TO public"))
        await connection.execute(text("DROP SCHEMA worker_cash_migration_test CASCADE"))


async def test_concurrent_recipient_confirmation_and_worker_cancel_have_one_winner(
    db_engine,
):
    factory, app, order_id, assignment_id, version, worker, manager = await app_seed(
        db_engine
    )
    manager_headers = {
        **worker,
        "Authorization": "Bearer "
        + create_access_token(
            {
                "sub": manager.username,
                "staff_user_id": manager.staff_user_id,
                "auth_version": manager.auth_version,
            }
        ),
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        received = await client.post(
            f"/api/installer/works/{assignment_id}/collections",
            headers=worker,
            json=amount(version),
        )
        assert received.status_code == 200, received.text
        view = (await client.get("/api/installer/money", headers=worker)).json()
        created = await client.post(
            "/api/installer/money/handovers",
            headers=worker,
            json=amount(view["version"], recipient_staff_user_id=manager.staff_user_id),
        )
        assert created.status_code == 200, created.text
        handover = created.json()
        barrier = asyncio.Barrier(2)

        async def resolve(path, actor):
            await barrier.wait()
            return await client.post(
                path,
                headers=actor,
                json={
                    "idempotency_key": str(uuid4()),
                    "expected_version": handover["version"],
                },
            )

        responses = await asyncio.wait_for(
            asyncio.gather(
                resolve(
                    f"/api/manager/worker-money/{view['worker_profile_id']}/handovers/{handover['id']}/confirm",
                    manager_headers,
                ),
                resolve(
                    f"/api/installer/money/handovers/{handover['id']}/cancel", worker
                ),
            ),
            20,
        )
        assert sorted(response.status_code for response in responses) == [200, 409], [
            (r.status_code, r.text) for r in responses
        ]
        final = (await client.get("/api/installer/money", headers=worker)).json()
        balance = final["balances"][0]
        assert balance["pending"] == "0.00"
    async with factory() as session:
        row = await session.get(WorkerCashHandover, handover["id"])
        assert row.version == 1 and row.status in ("confirmed", "cancelled")
        assert balance["held"] == ("0.00" if row.status == "confirmed" else "100.00")
        assert balance["handed_over"] == (
            "100.00" if row.status == "confirmed" else "0.00"
        )
        assert (
            len(
                list(
                    (
                        await session.scalars(
                            select(Payment).where(Payment.order_id == order_id)
                        )
                    ).all()
                )
            )
            == 1
        )
