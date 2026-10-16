"""Physical PostgreSQL fences: committed seed, independent sessions, bounded waits."""
import asyncio
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from api_contracts.installer_workspace import WorkerAssignmentCreate
from models import LegacyOwnerAuthState, OrderWorkAssignment, StaffUser, Tenant, TenantMembership
from services.worker_assignment_service import WorkerAssignmentService as Service, WorkerAssignmentError
from services.worker_assignment_access_service import WorkerAssignmentAccessService as Access
from tests.integration.test_order_responsibility import seed


async def test_concurrent_explicit_assignment_is_single_grant(db_engine):
    factory=async_sessionmaker(db_engine,expire_on_commit=False)
    actor,order_id,candidates=await seed(factory)
    barrier=asyncio.Barrier(2)
    async def assign():
        async with factory() as session:
            await barrier.wait()
            row=await Service.create(session,actor,order_id,WorkerAssignmentCreate(staff_user_id=candidates[0]))
            result=row.id
            await session.commit()
            return result
    ids=await asyncio.wait_for(asyncio.gather(assign(),assign()),15)
    assert ids[0]==ids[1]
    async with factory() as session:
        assert len(list((await session.scalars(select(OrderWorkAssignment).where(OrderWorkAssignment.order_id==order_id))).all()))==1


@pytest.mark.parametrize('revocation',['actor','candidate'])
async def test_waiting_create_rechecks_live_actor_and_membership(db_engine,revocation):
    factory=async_sessionmaker(db_engine,expire_on_commit=False)
    actor,order_id,candidates=await seed(factory)
    async with factory() as admin, factory() as writer:
        await admin.execute(select(LegacyOwnerAuthState).with_for_update())
        await admin.execute(select(Tenant).where(Tenant.id==1).with_for_update())
        staff_id=actor.staff_user_id if revocation=='actor' else candidates[0]
        user=await admin.get(StaffUser,staff_id,with_for_update=True)
        if revocation=='actor': user.auth_version+=1
        else:
            member=await admin.scalar(select(TenantMembership).where(TenantMembership.tenant_id==1,TenantMembership.staff_user_id==staff_id).with_for_update())
            member.status='disabled'
        await admin.flush()
        operation=asyncio.create_task(Service.create(writer,actor,order_id,WorkerAssignmentCreate(staff_user_id=candidates[0])))
        try:
            await asyncio.sleep(.1)
            assert not operation.done()
            await admin.commit()
            with pytest.raises(WorkerAssignmentError) as caught: await asyncio.wait_for(operation,15)
            assert caught.value.code==('staff_access_changed' if revocation=='actor' else 'worker_unavailable')
        finally:
            if not operation.done():
                operation.cancel();await asyncio.gather(operation,return_exceptions=True)
            await writer.rollback()


async def test_bot_first_work_lock_waits_for_revocation_without_parent_fk_cycle(db_engine):
    from dataclasses import replace
    factory=async_sessionmaker(db_engine,expire_on_commit=False)
    actor,order_id,candidates=await seed(factory)
    async with factory() as setup:
        row=await Service.create(setup,actor,order_id,WorkerAssignmentCreate(staff_user_id=candidates[0]))
        assignment_id=row.id
        user=await setup.get(StaffUser,candidates[0])
        worker=replace(actor,staff_user_id=user.id,username=user.username)
        await setup.commit()
    async with factory() as admin, factory() as bot:
        await admin.execute(select(LegacyOwnerAuthState).with_for_update())
        await admin.execute(select(Tenant).where(Tenant.id==1).with_for_update())
        user=await admin.get(StaffUser,worker.staff_user_id,with_for_update=True)
        user.auth_version+=1
        await admin.flush()
        task=asyncio.create_task(Access.get_for_actor(bot,worker,assignment_id,for_update=True))
        try:
            await asyncio.sleep(.1)
            assert not task.done()
            await admin.commit()
            with pytest.raises(WorkerAssignmentError): await asyncio.wait_for(task,15)
        finally:
            if not task.done(): task.cancel();await asyncio.gather(task,return_exceptions=True)
            await bot.rollback()


async def test_actual_migration_is_ddl_only_and_downgrade_preserves_payroll(db_engine):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    spec=importlib.util.spec_from_file_location('worker_migration',Path('alembic/versions/t1167worker01_installer_workspace.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    async with db_engine.begin() as connection:
        await connection.execute(text('CREATE SCHEMA worker_migration_test'))
        await connection.execute(text('SET LOCAL search_path TO worker_migration_test'))
        for ddl in ['CREATE TABLE tenant (id integer PRIMARY KEY)', 'CREATE TABLE staff_users (id integer PRIMARY KEY)',
                    'CREATE TABLE installers (id integer PRIMARY KEY)',
                    'CREATE TABLE tenant_membership (tenant_id integer,staff_user_id integer,UNIQUE(tenant_id,staff_user_id))',
                    'CREATE TABLE "order" (id integer PRIMARY KEY, tenant_id integer, storefront_id integer, UNIQUE(id,tenant_id,storefront_id))',
                    'CREATE TABLE order_work_stage(id integer PRIMARY KEY, order_id integer)',
                    "CREATE TABLE staff_invitation (role text, CONSTRAINT ck_staff_invitation_role CHECK(role IN ('owner','admin','manager','catalog_editor')))",
                    'CREATE TABLE order_installers(order_id integer, installer_id integer, agreed_pay integer)']:
            await connection.execute(text(ddl))
        await connection.execute(text('INSERT INTO order_installers VALUES (1,1,777)'))
        def migrate(sync,method):
            module.op=Operations(MigrationContext.configure(sync));getattr(module,method)()
        await connection.run_sync(migrate,'upgrade')
        assert await connection.scalar(text('SELECT count(*) FROM order_work_assignment'))==0
        assert await connection.scalar(text('SELECT count(*) FROM tenant_worker_profile'))==0
        await connection.execute(text("INSERT INTO staff_invitation VALUES ('installer')"))
        with pytest.raises(RuntimeError,match='installer invitations'):
            await connection.run_sync(migrate,'downgrade')
        await connection.execute(text('DELETE FROM staff_invitation'))
        await connection.run_sync(migrate,'downgrade')
        assert (await connection.execute(text('SELECT * FROM order_installers'))).all()==[(1,1,777)]
        await connection.execute(text('SET LOCAL search_path TO public'))
        await connection.execute(text('DROP SCHEMA worker_migration_test CASCADE'))


async def test_manager_stage_delete_waits_for_order_before_locking_stage(db_engine):
    from models import Order, OrderWorkStage
    from services.order_work_stage_command_service import OrderWorkStageCommandService
    factory=async_sessionmaker(db_engine,expire_on_commit=False)
    actor,order_id,_=await seed(factory)
    async with factory() as setup:
        stage=OrderWorkStage(order_id=order_id,name='Lock ordering')
        setup.add(stage);await setup.commit();stage_id=stage.id
    async with factory() as blocker, factory() as manager, factory() as probe:
        await blocker.execute(select(Order).where(Order.id==order_id).with_for_update())
        task=asyncio.create_task(OrderWorkStageCommandService.delete_order_stage_direct(
            manager,stage_id,tenant_scope=actor.tenant_scope()))
        try:
            await asyncio.sleep(.1)
            assert not task.done()
            # A Stage-first joined lock would already hold this row while waiting
            # for Order, deadlocking a Bot writer which owns Order then requests Stage.
            await probe.execute(select(OrderWorkStage).where(OrderWorkStage.id==stage_id).with_for_update(nowait=True))
            await probe.commit()
            await blocker.commit()
            assert await asyncio.wait_for(task,15)=={'ok':True,'id':stage_id}
        finally:
            if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
            await manager.rollback()
