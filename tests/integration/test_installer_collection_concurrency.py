"""Real PostgreSQL collection fences use committed seeds and independent sessions."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from api_contracts.installer_workspace import (
    ManagerCollectionUpdate,
    WorkerAssignmentCreate,
)
from models import Order, OrderServiceLink, Payment
from models.installer_publication import InstallerCollectionInstruction
from services.installer_collection_service import (
    InstallerCollectionService as Collection,
    InstallerWorkspaceError,
)
from services.installer_workspace_service import InstallerWorkspaceService as Workspace
from services.worker_assignment_service import WorkerAssignmentService as Assignments
from tests.integration.test_order_responsibility import seed


async def setup_collection(factory):
    actor, order_id, candidates = await seed(factory)
    async with factory() as session:
        session.add(OrderServiceLink(order_id=order_id, price=1000, cost=700))
        assignment = await Assignments.create(
            session,
            actor,
            order_id,
            WorkerAssignmentCreate(staff_user_id=candidates[0]),
        )
        await session.commit()
        workspace = await Workspace.manager_view(session, actor, order_id)
        return actor, order_id, assignment.id, workspace


def instruction(workspace, assignment_id):
    return ManagerCollectionUpdate(
        expected_version=workspace.collection.version,
        assignment_id=assignment_id,
        amount="100.00",
        currency="BYN",
        financial_fingerprint=workspace.financial_fingerprint,
    )


async def test_concurrent_collection_first_publish_has_one_winner(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor, order_id, assignment_id, workspace = await setup_collection(factory)
    barrier = asyncio.Barrier(2)

    async def publish():
        async with factory() as session:
            await barrier.wait()
            try:
                await Collection.update(
                    session,
                    auth=actor,
                    order_id=order_id,
                    payload=instruction(workspace, assignment_id),
                )
                await session.commit()
                return "published"
            except InstallerWorkspaceError as error:
                await session.rollback()
                return error.code

    results = await asyncio.wait_for(asyncio.gather(publish(), publish()), 15)
    assert sorted(results) == ["collection_changed", "published"]
    async with factory() as session:
        rows = list(
            (
                await session.scalars(
                    select(InstallerCollectionInstruction).where(
                        InstallerCollectionInstruction.order_id == order_id
                    )
                )
            ).all()
        )
        assert len(rows) == 1 and rows[0].version == 1
        assert not list(
            (
                await session.scalars(
                    select(Payment).where(Payment.order_id == order_id)
                )
            ).all()
        )


async def test_waiting_collection_rechecks_committed_payment(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor, order_id, assignment_id, workspace = await setup_collection(factory)
    async with factory() as payment_writer, factory() as manager:
        await payment_writer.execute(
            select(Order).where(Order.id == order_id).with_for_update()
        )
        payment_writer.add(Payment(order_id=order_id, amount=50, currency="BYN"))
        await payment_writer.flush()
        task = asyncio.create_task(
            Collection.update(
                manager,
                auth=actor,
                order_id=order_id,
                payload=instruction(workspace, assignment_id),
            )
        )
        try:
            await asyncio.sleep(0.1)
            assert not task.done()
            await payment_writer.commit()
            with pytest.raises(InstallerWorkspaceError) as caught:
                await asyncio.wait_for(task, 15)
            assert caught.value.code == "financials_changed"
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await manager.rollback()
    async with factory() as session:
        assert (
            await session.scalar(
                select(InstallerCollectionInstruction.id).where(
                    InstallerCollectionInstruction.order_id == order_id
                )
            )
            is None
        )


async def test_real_publication_migration_scope_and_cascades_preserve_sources(
    db_engine,
):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    spec = importlib.util.spec_from_file_location(
        "installer_publication_migration",
        Path("alembic/versions/t1167worker02_installer_publications.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    async with db_engine.begin() as connection:
        await connection.execute(text("CREATE SCHEMA installer_publication_test"))
        await connection.execute(
            text("SET LOCAL search_path TO installer_publication_test")
        )
        for ddl in [
            'CREATE TABLE "order" (id integer PRIMARY KEY, tenant_id integer, storefront_id integer, UNIQUE(id,tenant_id,storefront_id))',
            "CREATE TABLE order_work_assignment (id integer PRIMARY KEY, tenant_id integer, storefront_id integer, order_id integer, UNIQUE(id,tenant_id,storefront_id,order_id))",
            "CREATE TABLE order_attachment_link (id integer PRIMARY KEY, order_id integer)",
        ]:
            await connection.execute(text(ddl))
        await connection.execute(text('INSERT INTO "order" VALUES (1,1,1),(2,2,2)'))
        await connection.execute(
            text("INSERT INTO order_work_assignment VALUES (1,1,1,1)")
        )
        await connection.execute(
            text("INSERT INTO order_attachment_link VALUES (1,1),(2,2)")
        )

        def migrate(sync, method):
            module.op = Operations(MigrationContext.configure(sync))
            getattr(module, method)()

        await connection.run_sync(migrate, "upgrade")
        assert (
            await connection.scalar(
                text("SELECT count(*) FROM installer_collection_instruction")
            )
            == 0
        )
        assert (
            await connection.scalar(
                text("SELECT count(*) FROM installer_material_publication")
            )
            == 0
        )
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "INSERT INTO installer_material_publication (tenant_id,storefront_id,order_id,assignment_id,order_attachment_link_id,created_at) VALUES (2,2,2,1,2,now())"
                    )
                )
        await connection.execute(
            text(
                "INSERT INTO installer_material_publication (tenant_id,storefront_id,order_id,assignment_id,order_attachment_link_id,created_at) VALUES (1,1,1,1,1,now())"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO installer_collection_instruction (tenant_id,storefront_id,order_id,assignment_id,amount,currency,financial_fingerprint,version,updated_at) VALUES (1,1,1,1,0,'BYN','reviewed',1,now())"
            )
        )
        await connection.execute(text("DELETE FROM order_work_assignment WHERE id=1"))
        assert (
            await connection.scalar(
                text("SELECT count(*) FROM installer_collection_instruction")
            )
            == 0
        )
        assert (
            await connection.scalar(
                text("SELECT count(*) FROM installer_material_publication")
            )
            == 0
        )
        assert (
            await connection.scalar(text("SELECT count(*) FROM order_attachment_link"))
            == 2
        )
        await connection.run_sync(migrate, "downgrade")
        assert (
            await connection.scalar(text("SELECT count(*) FROM order_attachment_link"))
            == 2
        )
        await connection.execute(text("SET LOCAL search_path TO public"))
        await connection.execute(text("DROP SCHEMA installer_publication_test CASCADE"))
