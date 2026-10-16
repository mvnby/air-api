"""Responsibility races use committed seeds and independent PostgreSQL sessions."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from api_contracts.order_responsibility import ManagerOrderResponsibleUpdate
from core.security import AuthenticatedUser
from models import LegacyOwnerAuthState, Order, StaffUser, Tenant, TenantAuditEvent, TenantMembership
from services.order_responsibility_service import OrderResponsibilityService as Service, OrderResponsibilityError


async def seed(factory):
    async with factory() as session:
        users = [StaffUser(display_name=f"Responsible {index}", username=f"responsible-{index}") for index in range(3)]
        session.add_all(users)
        await session.flush()
        session.add_all([TenantMembership(tenant_id=1, staff_user_id=user.id, role="manager") for user in users])
        await session.flush()
        order = Order(tenant_id=1, storefront_id=1)
        session.add(order)
        await session.commit()
        return (AuthenticatedUser(username=users[0].username, auth_source="staff_password",
            staff_user_id=users[0].id, auth_version=users[0].auth_version, role="manager",
            tenant_id=1, storefront_id=1), order.id, [user.id for user in users[1:]])


def update(candidate, version=0):
    return ManagerOrderResponsibleUpdate(responsible_staff_user_id=candidate, expected_version=version)


async def test_concurrent_responsibility_assignments_have_one_winner(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor, order_id, candidates = await seed(factory)
    barrier = asyncio.Barrier(2)

    async def assign(candidate):
        async with factory() as session:
            await barrier.wait()
            try:
                await Service.assign(session, order_id=order_id, payload=update(candidate), auth=actor)
                return "changed"
            except OrderResponsibilityError as error:
                await session.rollback()
                return error.code

    results = await asyncio.wait_for(asyncio.gather(*(assign(candidate) for candidate in candidates)), 15)
    assert sorted(results) == ["changed", "responsible_changed"]
    async with factory() as session:
        order = await session.get(Order, order_id)
        assert order.responsible_version == 1 and order.responsible_staff_user_id in candidates
        audits = list((await session.scalars(select(TenantAuditEvent).where(TenantAuditEvent.action == "order.responsible_changed"))).all())
        assert len(audits) == 1 and audits[0].change_set["responsible_staff_user_id"]["after"] == order.responsible_staff_user_id


@pytest.mark.parametrize("revocation", ["actor", "candidate"])
async def test_waiting_assignment_rechecks_actor_and_candidate_after_admin_commit(db_engine, revocation):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor, order_id, candidates = await seed(factory)
    async with factory() as admin, factory() as writer:
        # Same state→Tenant→Staff hierarchy as actual staff administration.
        await admin.execute(select(LegacyOwnerAuthState).with_for_update())
        await admin.execute(select(Tenant).where(Tenant.id == 1).with_for_update())
        staff_id = actor.staff_user_id if revocation == "actor" else candidates[0]
        staff = await admin.get(StaffUser, staff_id, with_for_update=True)
        if revocation == "actor":
            staff.auth_version += 1
        else:
            member = await admin.scalar(select(TenantMembership).where(TenantMembership.tenant_id == 1, TenantMembership.staff_user_id == staff_id).with_for_update())
            member.status = "disabled"
            admin.add(member)
        admin.add(staff)
        await admin.flush()
        operation = asyncio.create_task(Service.assign(writer, order_id=order_id, payload=update(candidates[0]), auth=actor))
        try:
            await asyncio.sleep(0.1)
            assert not operation.done()
            await admin.commit()
            with pytest.raises(OrderResponsibilityError) as caught:
                await asyncio.wait_for(operation, 15)
            assert caught.value.code == ("staff_access_changed" if revocation == "actor" else "responsible_unavailable")
        finally:
            if not operation.done():
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
            await writer.rollback()
    async with factory() as verify:
        order = await verify.get(Order, order_id)
        assert order.responsible_staff_user_id is None and order.responsible_version == 0
        assert not list((await verify.scalars(select(TenantAuditEvent))).all())


async def test_postgres_fk_does_not_allow_staff_without_company_membership(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    _, order_id, _ = await seed(factory)
    async with factory() as session:
        outsider = StaffUser(display_name="Outside", username="outside-responsibility")
        session.add(outsider)
        await session.commit()
        order = await session.get(Order, order_id)
        order.responsible_staff_user_id = outsider.id
        session.add(order)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_migration_preserves_legacy_nulls_and_enforces_membership(db_engine):
    """Run the actual upgrade/downgrade in an isolated transactional test schema."""
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text

    path = Path("alembic/versions/t1166respons01_order_responsibility.py")
    spec = importlib.util.spec_from_file_location("order_responsibility_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    async with db_engine.begin() as connection:
        await connection.execute(text("CREATE SCHEMA responsibility_migration_test"))
        await connection.execute(text("SET LOCAL search_path TO responsibility_migration_test"))
        await connection.execute(text("CREATE TABLE staff_users (id integer PRIMARY KEY)"))
        await connection.execute(text("CREATE TABLE tenant_membership (tenant_id integer, staff_user_id integer, UNIQUE (tenant_id, staff_user_id))"))
        await connection.execute(text('CREATE TABLE "order" (id integer PRIMARY KEY, tenant_id integer)'))
        await connection.execute(text("INSERT INTO staff_users VALUES (1), (2)"))
        await connection.execute(text("INSERT INTO tenant_membership VALUES (1, 1), (2, 2)"))
        await connection.execute(text('INSERT INTO "order" VALUES (1, 1), (2, NULL)'))
        def migrate(sync, direction):
            module.op = Operations(MigrationContext.configure(sync))
            getattr(module, direction)()
        await connection.run_sync(migrate, "upgrade")
        rows = (await connection.execute(text('SELECT id, responsible_staff_user_id, responsible_version FROM "order" ORDER BY id'))).all()
        assert rows == [(1, None, 0), (2, None, 0)]
        await connection.execute(text('UPDATE "order" SET responsible_staff_user_id = 1 WHERE id = 1'))
        for sql in (
            'UPDATE "order" SET responsible_staff_user_id = 2 WHERE id = 1',
            'UPDATE "order" SET responsible_staff_user_id = 1 WHERE id = 2',
            'UPDATE "order" SET responsible_version = -1 WHERE id = 1',
        ):
            async with connection.begin_nested() as savepoint:
                with pytest.raises(IntegrityError):
                    await connection.execute(text(sql))
                await savepoint.rollback()
        await connection.run_sync(migrate, "downgrade")
        assert (await connection.execute(text('SELECT id, tenant_id FROM "order" ORDER BY id'))).all() == [(1, 1), (2, None)]
        await connection.execute(text("SET LOCAL search_path TO public"))
        await connection.execute(text("DROP SCHEMA responsibility_migration_test CASCADE"))


async def test_initial_creator_fence_precedes_child_fk_and_rechecks_membership(db_engine):
    from models.tenancy import TenantScope

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor, _, _ = await seed(factory)
    scope = TenantScope(tenant_id=1, storefront_id=1)
    started = asyncio.Event()
    async with factory() as admin:
        await admin.execute(select(LegacyOwnerAuthState).with_for_update())
        async def create():
            async with factory() as creator:
                started.set()
                responsible = await Service.initial_responsible(creator, scope, actor.staff_user_id)
                order = Order(tenant_id=1, storefront_id=1, responsible_staff_user_id=responsible)
                creator.add(order)
                await creator.commit()
                return order.id, responsible
        operation = asyncio.create_task(create())
        try:
            await started.wait()
            await asyncio.sleep(0.1)
            assert not operation.done()
            # The creator must not yet own a Tenant child FK lock.
            await asyncio.wait_for(admin.execute(select(Tenant).where(Tenant.id == 1).with_for_update()), 5)
            await admin.get(StaffUser, actor.staff_user_id, with_for_update=True)
            membership = await admin.scalar(select(TenantMembership).where(TenantMembership.tenant_id == 1, TenantMembership.staff_user_id == actor.staff_user_id).with_for_update())
            membership.status = "disabled"
            admin.add(membership)
            await admin.commit()
            order_id, responsible = await asyncio.wait_for(operation, 15)
            assert responsible is None
        finally:
            if not operation.done():
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
    async with factory() as verify:
        assert (await verify.get(Order, order_id)).responsible_staff_user_id is None
