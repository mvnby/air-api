from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError

from api_contracts.installer_workspace import WorkerAssignmentCreate
from models import (Installer, Order, OrderInstaller, OrderWorkAssignment, OrderWorkStage,
                    StaffUser, TenantAuditEvent, TenantMembership, TenantWorkerProfile)
from services.worker_assignment_service import WorkerAssignmentService as Service, WorkerAssignmentError
from services.worker_assignment_access_service import WorkerAssignmentAccessService as Access
from services.worker_assignment_legacy_sync import WorkerAssignmentLegacySync as Sync
from tests.unit.test_order_responsibility import responsibility_db, auth
from tests.unit.test_manager_multicompany import multi_db


def worker(staff_id=22, **kwargs):
    return auth(staff_id=staff_id, **kwargs)


async def create(session, staff_id=22, order_id=100, stage_id=None):
    return await Service.create(session, auth(), order_id, WorkerAssignmentCreate(staff_user_id=staff_id, work_stage_id=stage_id))


async def test_explicit_create_revoke_no_secret_commit_and_payroll_untouched(responsibility_db):
    session = responsibility_db
    session.add(Installer(id=1, name='Old payroll'))
    session.add(OrderInstaller(order_id=100, installer_id=1, agreed_pay=777, is_paid_to_installer=True))
    await session.commit()
    assert await Access.list_for_actor(session, worker()) == ([], 0)
    row = await create(session)
    assert row.title == 'Монтаж' and row.instructions == '' and row.version == 0
    assert await Access.get_for_actor(session, worker(), row.id) is row
    assert (await Access.list_for_actor(session, worker()))[1] == 1
    await session.rollback()
    assert await session.scalar(select(OrderWorkAssignment.id)) is None
    row = await create(session)
    await session.commit()
    same = await create(session)
    assert same.id == row.id and same.version == 0
    await Service.revoke(session, auth(), 100, row.id, 0)
    assert row.version == 1 and await Access.get_for_actor(session, worker(), row.id) is None
    with pytest.raises(WorkerAssignmentError, match='Назначение изменено'):
        await Service.revoke(session, auth(), 100, row.id, 0)
    await session.commit()
    payroll = await session.get(OrderInstaller, (100, 1))
    assert payroll.agreed_pay == 777 and payroll.is_paid_to_installer
    assert len(list((await session.scalars(select(TenantAuditEvent))).all())) == 2


@pytest.mark.parametrize('candidate', [21,23,24,25,26,999])
async def test_reject_ineligible_foreign_alias_disabled(responsibility_db, candidate):
    with pytest.raises(WorkerAssignmentError) as caught:
        await create(responsibility_db, candidate)
    assert caught.value.code == 'worker_unavailable'


async def test_worker_reads_are_lockfree_and_company_site_scoped(responsibility_db):
    session = responsibility_db
    row = await create(session)
    await session.commit()
    statements = []
    def inspect(state): statements.append(state.statement)
    event.listen(session.sync_session, 'do_orm_execute', inspect)
    try:
        assert await Access.get_for_actor(session, worker(), row.id)
        assert (await Service.candidates(session, auth())).total == 4
        assert await Access.get_for_actor(session, replace(worker(), storefront_id=4), row.id) is None
        with pytest.raises(WorkerAssignmentError):
            await Access.get_for_actor(session, worker(tenant_id=2), row.id)
        with pytest.raises(WorkerAssignmentError):
            await Access.get_for_actor(session, auth(4, 2, access_kind='platform_support', is_platform_owner=True), row.id)
    finally:
        event.remove(session.sync_session, 'do_orm_execute', inspect)
    assert all(getattr(stmt, '_for_update_arg', None) is None and not getattr(stmt,'is_dml',False) for stmt in statements)


@pytest.mark.parametrize('change', ['staff', 'member', 'profile', 'auth_version', 'alias', 'closed'])
async def test_live_access_revocation(responsibility_db, change):
    session = responsibility_db
    row = await create(session)
    await session.commit()
    user = await session.get(StaffUser,22)
    if change == 'staff': user.status = 'inactive'
    elif change == 'auth_version': user.auth_version += 1
    elif change == 'alias': user.merged_into_staff_user_id = 20
    elif change == 'member':
        member = await session.scalar(select(TenantMembership).where(TenantMembership.staff_user_id==22))
        member.status='disabled'
    elif change == 'profile': (await session.get(TenantWorkerProfile,row.worker_profile_id)).status='disabled'
    else: (await session.get(Order,100)).status='closed'
    await session.commit()
    try: result = await Access.get_for_actor(session, worker(),row.id)
    except WorkerAssignmentError: result = None
    assert result is None


async def test_visit_only_no_widening_or_internal_comments(responsibility_db):
    session = responsibility_db
    session.add_all([OrderWorkStage(id=11,order_id=100, name='Secret margin',manager_comment='Private'),
                     OrderWorkStage(id=12,order_id=100, name='Other'), OrderWorkStage(id=13,order_id=200,name='Foreign')])
    await session.commit()
    row = await create(session,stage_id=11)
    assert row.instructions == '' and row.title == 'Монтаж'
    assert await Access.get_for_stage(session,worker(),11)
    assert await Access.get_for_stage(session,worker(),12) is None
    with pytest.raises(WorkerAssignmentError): await create(session,stage_id=13)
    (await session.get(OrderWorkStage,11)).status='completed'
    await session.commit()
    assert await Access.get_for_actor(session,worker(),row.id) is None


async def test_legacy_new_assignment_only_and_manual_grant_survives(responsibility_db):
    session=responsibility_db
    session.add(Installer(id=1,name='Legacy'))
    user=await session.get(StaffUser,22);user.legacy_installer_id=1
    session.add(OrderInstaller(order_id=100,installer_id=1,agreed_pay=555))
    await session.commit()
    scope=replace(auth().tenant_scope(),is_system=True,is_canonical_storefront=True)
    profiles=await Sync.prepare(session,scope,[1])
    await Sync.sync(session,scope,100,profiles,previous_ids={1},current_ids={1})
    assert await session.scalar(select(OrderWorkAssignment.id)) is None
    await Sync.sync(session,scope,100,profiles,previous_ids=set(),current_ids={1})
    row=await session.scalar(select(OrderWorkAssignment))
    assert row.source=='legacy_order' and await Access.get_for_actor(session,worker(),row.id)
    same=await create(session)
    assert same.id==row.id and same.source=='manual' and same.version==1
    await Sync.sync(session,scope,100,profiles,previous_ids={1},current_ids=set())
    assert row.revoked_at is None


async def test_profile_and_assignment_database_scope_constraints(responsibility_db):
    session=responsibility_db
    await session.commit()
    await session.execute(text('PRAGMA foreign_keys=ON'))
    session.add(TenantWorkerProfile(tenant_id=2,staff_user_id=22))
    with pytest.raises(IntegrityError): await session.flush()
    await session.rollback()
    # Seed has one unrelated intentionally historical invalid FK; new writes are strict.
    row=await create(session)
    await session.commit()
    session.add(OrderWorkAssignment(tenant_id=2,storefront_id=2,order_id=200,worker_profile_id=row.worker_profile_id))
    with pytest.raises(IntegrityError): await session.flush()
    await session.rollback()


async def test_bot_existing_completed_action_is_explicit_and_never_widens_web(responsibility_db):
    session=responsibility_db
    session.add(OrderWorkStage(id=50,order_id=100,name="Visit"))
    await session.commit()
    row=await create(session,stage_id=50)
    (await session.get(OrderWorkStage,50)).status='completed'
    await session.commit()
    assert await Access.get_for_stage(session,worker(),50) is None
    assert await Access.get_for_actor(session,worker(),row.id) is None
    assert await Access.get_for_stage(session,worker(),50,for_update=True,existing_action=True)
    (await session.get(OrderWorkStage,50)).status='canceled'
    await session.commit()
    assert await Access.get_for_stage(session,worker(),50,existing_action=True) is None


async def test_actual_stage_commands_sync_only_new_assignments_and_revoke_replacement(responsibility_db, monkeypatch):
    from unittest.mock import AsyncMock
    from schemas import OrderWorkStageCreatePayload, OrderWorkStageUpdatePayload
    from services.order_work_stage_command_service import OrderWorkStageCommandService as Commands
    from services.staff_task_notification_event_service import StaffTaskNotificationEventService
    session=responsibility_db
    session.add(Installer(id=1,name='Legacy'))
    user=await session.get(StaffUser,22)
    user.legacy_installer_id=1;user.roles=['installer'];user.primary_role='installer'
    await session.commit()
    scope=replace(auth().tenant_scope(),is_system=True,is_canonical_storefront=True)
    monkeypatch.setattr(Commands,'_project_committed_order',AsyncMock(return_value={}))
    monkeypatch.setattr(StaffTaskNotificationEventService,'enqueue_assigned',AsyncMock())
    monkeypatch.setattr(StaffTaskNotificationEventService,'enqueue_rescheduled',AsyncMock())
    await Commands.add_order_stage(session,100,OrderWorkStageCreatePayload(name='Internal name',installer_id=1,manager_comment='Private'),tenant_scope=scope)
    row=await session.scalar(select(OrderWorkAssignment))
    assert row.source=='legacy_stage' and row.instructions=='' and row.title=='Монтаж'
    assert await Access.get_for_stage(session,worker(),row.work_stage_id)
    await session.commit()
    await Commands.update_order_stage(session,100,row.work_stage_id,OrderWorkStageUpdatePayload(manager_comment='Still private'),tenant_scope=scope)
    assert len(list((await session.scalars(select(OrderWorkAssignment))).all()))==1
    await session.commit()
    await Commands.update_order_stage(session,100,row.work_stage_id,OrderWorkStageUpdatePayload(installer_id=None),tenant_scope=scope)
    await session.refresh(row)
    assert row.revoked_at is not None and row.version==1
    assert await Access.get_for_stage(session,worker(),row.work_stage_id) is None


async def test_deleted_stage_cannot_become_order_wide_assignment(responsibility_db):
    session=responsibility_db
    session.add(OrderWorkStage(id=71,order_id=100,name='Visit'))
    await session.commit()
    row=await create(session,stage_id=71)
    assignment_id=row.id
    await session.commit()
    await session.execute(text('PRAGMA foreign_keys=ON'))
    await session.delete(await session.get(OrderWorkStage,71))
    await session.commit()
    assert await session.scalar(select(OrderWorkAssignment.id).where(OrderWorkAssignment.id==assignment_id)) is None
    assert (await Access.list_for_actor(session,worker()))[1]==0


@pytest.mark.parametrize("delete_path", ["direct", "order"])
async def test_delete_published_stage_withdraws_collection_without_resetting_version(responsibility_db, monkeypatch, delete_path):
    from decimal import Decimal
    from models import ServiceAttachment, OrderAttachmentLink, InstallerMaterialPublication, InstallerCollectionInstruction
    from services.order_work_stage_command_service import OrderWorkStageCommandService as Commands
    session=responsibility_db
    session.add_all([OrderWorkStage(id=80,order_id=100,name='Published visit'),
                     OrderWorkStage(id=81,order_id=100,name='Other visit')])
    session.add_all([ServiceAttachment(id=90,original_filename='manual.pdf',file_kind='document',mime_type='application/pdf'),
                     ServiceAttachment(id=92,original_filename='other.pdf',file_kind='document',mime_type='application/pdf')])
    await session.flush()
    session.add_all([OrderAttachmentLink(id=91,order_id=100,attachment_id=90,work_stage_id=80),
                     OrderAttachmentLink(id=93,order_id=100,attachment_id=92,work_stage_id=81)])
    await session.commit()
    row=await create(session,stage_id=80)
    assignment_id=row.id
    session.add(InstallerMaterialPublication(tenant_id=1,storefront_id=1,order_id=100,assignment_id=row.id,order_attachment_link_id=91))
    session.add(InstallerCollectionInstruction(tenant_id=1,storefront_id=1,order_id=100,assignment_id=row.id,
        amount=Decimal('100.00'),currency='BYN',financial_fingerprint='a'*64,version=7))
    await session.commit()
    await session.execute(text('PRAGMA foreign_keys=ON'))
    if delete_path == "direct":
        await Commands.delete_order_stage_direct(session,80,tenant_scope=auth().tenant_scope())
    else:
        from unittest.mock import AsyncMock
        monkeypatch.setattr(Commands, '_project_committed_order', AsyncMock(return_value={}))
        await Commands.delete_order_stage(session,100,80,tenant_scope=auth().tenant_scope())
    collection=await session.scalar(select(InstallerCollectionInstruction).where(InstallerCollectionInstruction.order_id==100).execution_options(populate_existing=True))
    assert collection.version==8
    assert collection.assignment_id is None and collection.amount is None and collection.currency is None
    assert collection.financial_fingerprint==''
    assert await session.scalar(select(OrderWorkAssignment.id).where(OrderWorkAssignment.id==assignment_id)) is None
    assert await session.scalar(select(InstallerMaterialPublication.id)) is None
    assert await session.get(ServiceAttachment,90)
    source_link = await session.get(OrderAttachmentLink,91)
    assert source_link is not None and source_link.order_id == 100 and source_link.work_stage_id is None
    assert (await session.get(OrderAttachmentLink,93)).work_stage_id == 81
    assert await session.scalar(select(TenantAuditEvent.id).where(TenantAuditEvent.action=='installer.collection_withdrawn'))


async def test_disabled_workspace_profile_does_not_block_legacy_payroll_sync(responsibility_db):
    session=responsibility_db
    session.add(Installer(id=1,name='Legacy'))
    user=await session.get(StaffUser,22);user.legacy_installer_id=1
    session.add(TenantWorkerProfile(tenant_id=1,staff_user_id=22,status='disabled',canonical_legacy_installer_id=1))
    session.add(OrderInstaller(order_id=100,installer_id=1,agreed_pay=555))
    await session.commit()
    profiles=await Sync.prepare(session,auth().tenant_scope(),[1])
    assert profiles=={}
    await Sync.sync(session,auth().tenant_scope(),100,profiles,previous_ids={1},current_ids={1})
    assert await session.scalar(select(OrderWorkAssignment.id)) is None
    assert (await session.get(OrderInstaller,(100,1))).agreed_pay==555


async def test_manager_authority_and_virtual_support_never_make_fake_worker(responsibility_db):
    session=responsibility_db
    with pytest.raises(WorkerAssignmentError) as denied:
        await Service.create(session,worker(),100,WorkerAssignmentCreate(staff_user_id=22))
    assert denied.value.code=='worker_access_denied'
    owner=auth(4,2,access_kind='platform_support',is_platform_owner=True)
    with pytest.raises(WorkerAssignmentError) as denied:
        await Service.create(session,owner,200,WorkerAssignmentCreate(staff_user_id=4))
    assert denied.value.code=='worker_unavailable'
    row=await Service.create(session,owner,200,WorkerAssignmentCreate(staff_user_id=25))
    profile=await session.get(TenantWorkerProfile,row.worker_profile_id)
    assert profile.tenant_id==2 and profile.staff_user_id==25 and profile.canonical_legacy_installer_id is None
    with pytest.raises(WorkerAssignmentError) as denied:
        await Service.create(session,replace(auth(),staff_user_id=None),100,WorkerAssignmentCreate(staff_user_id=22))
    assert denied.value.code=='staff_account_required'
