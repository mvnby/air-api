"""The finding is evidence, never executed work or a commercial decision."""
import asyncio
import io
from datetime import datetime
from uuid import uuid4

from PIL import Image
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from core.config import settings
from core.security import AuthenticatedUser, get_current_auth_context, create_access_token
from main import app
from models import (
    Customer, CustomerBranch, CustomerEquipment, EquipmentServiceHistory, EquipmentServiceEventType,
    Order, OrderDocument, OrderProposal, OrderStatus, Tenant, Storefront, ServiceAttachment,
    MaintenanceObservation, MaintenanceObservationRevision, MaintenanceObservationPhoto, StaffUser, TenantMembership,
)
from models.tenancy import TenantScope
from api_contracts.maintenance_observations import CreateMaintenanceObservation, UpdateMaintenanceObservation
from services.maintenance_observation_service import MaintenanceObservationService as Service, ObservationConflict
from services.document_service import DocumentService, OrderDocumentsLockedError
from services.equipment_maintenance_plan_service import EquipmentMaintenancePlanService


async def login(client):
    response = await client.post('/login/access-token', data={'username': settings.ADMIN_USERNAME, 'password': settings.ADMIN_PASSWORD})
    assert response.status_code == 200
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


async def context(db, status=OrderStatus.EXECUTION):
    customer = Customer(tenant_id=1, name='Maintenance owner', phone='+375291085001')
    db.add(customer); await db.flush()
    branch = CustomerBranch(customer_id=customer.id, name='Server room', delivery_address='Minsk, Local test')
    db.add(branch); await db.flush()
    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, customer_branch_id=branch.id,
                  workflow_type='maintenance', status=status, technical_meta={'source': 'preserve'}, repair_meta={},
                  installation_date=datetime(2026, 1, 31, 10))
    equipment = CustomerEquipment(customer_id=customer.id, customer_branch_id=branch.id, display_name='Outside block',
                                  maintenance_enabled=True, maintenance_interval_months=12, installed_at=datetime(2025, 1, 31))
    db.add_all([order, equipment]); await db.flush()
    event = EquipmentServiceHistory(equipment_id=equipment.id, order_id=order.id, event_type=EquipmentServiceEventType.MAINTENANCE,
                                    event_date=datetime(2026, 1, 31), maintenance_provider='mvn')
    db.add(event); await db.commit()
    return order, equipment, event


def payload(**changes):
    return {'command_key': str(uuid4()), 'observed_at': '2026-10-07T14:00:00+03:00',
            'original_comment': 'У наружного блока повреждена теплоизоляция.',
            'equipment_description': 'Наружный блок у входа', 'equipment_id': None,
            'facts': 'Видимое повреждение теплоизоляции трубопровода.',
            'recommendation': 'Восстановить теплоизоляцию после уточнения объёма.', **changes}


def image_bytes(color='red'):
    output = io.BytesIO(); Image.new('RGB', (12, 12), color).save(output, 'PNG'); return output.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [OrderStatus.EXECUTION, OrderStatus.CLOSED])
async def test_save_replay_correct_and_photos_preserve_maintenance(async_client, db, status, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'SERVICE_ATTACHMENT_LOCAL_DIR', str(tmp_path))
    headers = await login(async_client)
    order, equipment, event = await context(db, status)
    document = OrderDocument(order_id=order.id, tenant_id=1, doc_type='act', number='1085-legacy', google_file_id='issued-test-evidence')
    db.add(document); await db.commit()
    order_id, equipment_id = order.id, equipment.id
    order_before = order.model_dump(); event_before = event.model_dump(); document_before = document.model_dump()
    plan_before = await EquipmentMaintenancePlanService.calendar_events(db, start_date=datetime(2027, 1, 1), end_date=datetime(2027, 2, 1), tenant_scope=TenantScope(1, 1), now=datetime(2026, 10, 7))
    command = payload()
    url = f'/api/manager/orders/{order.id}/maintenance-observations'
    created = await async_client.post(url, headers=headers, json=command)
    assert created.status_code == 201, created.text
    finding = created.json(); finding_id = finding['id']
    assert finding['customer_id'] == order.customer_id and finding['customer_branch_id'] == order.customer_branch_id
    assert finding['equipment_id'] is None and finding['origin'] == 'manager_maintenance'
    assert finding['created_by'] == settings.ADMIN_USERNAME
    assert finding['observed_at'] == '2026-10-07T11:00:00'
    assert finding['facts'] == command['facts'] and finding['recommendation'] == command['recommendation']
    assert finding['revisions'][0]['snapshot']['facts'] == command['facts']
    replay = await async_client.post(url, headers=headers, json=command)
    assert replay.status_code == 201 and replay.json()['id'] == finding_id
    mismatch = await async_client.post(url, headers=headers, json={**command, 'facts': 'Other block'})
    assert mismatch.status_code == 409
    second = await async_client.post(url, headers=headers, json=payload(equipment_description='Другой блок'))
    assert second.status_code == 201 and second.json()['id'] != finding_id
    edit_url = f'/api/manager/maintenance-observations/{finding_id}'
    edit = {k: finding[k] for k in ('equipment_description', 'facts', 'recommendation')}
    edit.update(equipment_id=equipment_id, expected_version=1, facts='Уточнено: повреждена изоляция на изгибе.')
    updated = await async_client.patch(edit_url, headers=headers, json=edit)
    assert updated.status_code == 200, updated.text
    assert updated.json()['version'] == 2 and updated.json()['original_comment'] == command['original_comment']
    assert [r['version'] for r in updated.json()['revisions']] == [1, 2]
    stale = await async_client.patch(edit_url, headers=headers, json={**edit, 'facts': 'Stale overwrite'})
    assert stale.status_code == 409
    replay_after_edit = await async_client.post(url, headers=headers, json=command)
    assert replay_after_edit.status_code == 201 and replay_after_edit.json()['version'] == 2
    photo_key = str(uuid4()); content = image_bytes()
    async def upload(data=content, key=photo_key, filename='block.png', mime='image/png'):
        return await async_client.post(edit_url+'/photos', headers=headers, data={'command_key': key}, files={'file': (filename, data, mime)})
    uploaded = await upload(); assert uploaded.status_code == 201, uploaded.text
    attachment_id = uploaded.json()['id']; assert uploaded.json()['preview_available']
    repeat = await upload(); assert repeat.status_code == 201 and repeat.json()['id'] == attachment_id
    collision = await upload(image_bytes('blue')); assert collision.status_code == 409
    invalid = await upload(b'not a photo', str(uuid4()), 'file.txt', 'text/plain'); assert invalid.status_code == 400
    empty = await upload(b'', str(uuid4())); assert empty.status_code == 400
    read = await async_client.get(edit_url, headers=headers); assert [p['id'] for p in read.json()['photos']] == [attachment_id]
    other = await async_client.get(f"/api/manager/maintenance-observations/{second.json()['id']}", headers=headers)
    assert other.json()['photos'] == []
    for variant in ('original', 'preview'):
        access = await async_client.get(f'/api/manager/service-attachments/{attachment_id}/access?variant={variant}', headers=headers)
        assert access.status_code == 200
        downloaded = await async_client.get(access.json()['url'])
        assert downloaded.status_code == 200 and downloaded.headers['cache-control'] == 'private, no-store'
        assert downloaded.content == content if variant == 'original' else downloaded.headers['content-type'].startswith('image/webp')
    equipment_findings = await async_client.get(f'/api/manager/equipment/{equipment_id}/maintenance-observations', headers=headers)
    assert equipment_findings.status_code == 200 and [r['id'] for r in equipment_findings.json()['items']] == [finding_id]
    limited = await async_client.get(url+'?limit=1&offset=1', headers=headers)
    assert limited.json()['total'] == 2 and len(limited.json()['items']) == 1
    assert (await async_client.get(url+'?limit=101', headers=headers)).status_code == 422
    await db.refresh(order); await db.refresh(event); await db.refresh(document)
    if status == OrderStatus.CLOSED:
        with pytest.raises(OrderDocumentsLockedError):
            await DocumentService.ensure_order_documents_mutable(db, order_id)
    assert order.model_dump() == order_before and event.model_dump() == event_before and document.model_dump() == document_before
    assert await db.scalar(select(func.count()).select_from(Order)) == 1
    assert await db.scalar(select(func.count()).select_from(OrderProposal)) == 0
    assert await db.scalar(select(func.count()).select_from(EquipmentServiceHistory)) == 1
    assert await db.scalar(select(func.count()).select_from(MaintenanceObservationPhoto)) == 1
    assert await EquipmentMaintenancePlanService.calendar_events(db, start_date=datetime(2027, 1, 1), end_date=datetime(2027, 2, 1), tenant_scope=TenantScope(1, 1), now=datetime(2026, 10, 7)) == plan_before


@pytest.mark.asyncio
async def test_tenant_storefront_role_and_entity_links(async_client, db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'SERVICE_ATTACHMENT_LOCAL_DIR', str(tmp_path))
    headers = await login(async_client)
    order, equipment, _ = await context(db)
    tenant = Tenant(slug='foreign-observations', display_name='Foreign owner')
    db.add(tenant); await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug='foreign', display_name='Foreign store', is_default=True, status='active')
    foreign = Customer(tenant_id=tenant.id, name='Foreign client', phone='+375291085002')
    db.add_all([storefront, foreign]); await db.flush()
    foreign_equipment = CustomerEquipment(customer_id=foreign.id, display_name='Foreign block')
    other_branch = CustomerBranch(customer_id=order.customer_id, name='Other object', delivery_address='Other')
    alien_branch = CustomerBranch(customer_id=foreign.id, name='Alien object', delivery_address='Alien')
    db.add_all([foreign_equipment, other_branch, alien_branch]); await db.flush()
    other_equipment = CustomerEquipment(customer_id=order.customer_id, customer_branch_id=other_branch.id)
    other_customer = Customer(tenant_id=1, name='Other client', phone='+375291085003')
    db.add_all([other_equipment, other_customer]); await db.flush()
    other_client_equipment = CustomerEquipment(customer_id=other_customer.id)
    other_storefront = Storefront(tenant_id=1, slug='other1085', display_name='Other storefront', status='active')
    db.add_all([other_client_equipment, other_storefront]); await db.flush()
    foreign_order = Order(tenant_id=tenant.id, storefront_id=storefront.id, customer_id=foreign.id, workflow_type='maintenance')
    sibling_order = Order(tenant_id=1, storefront_id=other_storefront.id, customer_id=order.customer_id, workflow_type='maintenance')
    bad_branch_order = Order(tenant_id=1, storefront_id=1, customer_id=order.customer_id, customer_branch_id=alien_branch.id, workflow_type='maintenance')
    db.add_all([foreign_order, sibling_order, bad_branch_order]); await db.commit()
    url = f'/api/manager/orders/{order.id}/maintenance-observations'
    invalid_equipment_ids = (foreign_equipment.id, other_equipment.id, other_client_equipment.id, 987654321)
    invalid_order_ids = (foreign_order.id, sibling_order.id)
    bad_branch_order_id, foreign_tenant_id, foreign_storefront_id = bad_branch_order.id, tenant.id, storefront.id
    for equipment_id in invalid_equipment_ids:
        response = await async_client.post(url, headers=headers, json=payload(equipment_id=equipment_id))
        assert response.status_code == 400, response.text
    for bad_order_id in invalid_order_ids:
        assert (await async_client.post(f'/api/manager/orders/{bad_order_id}/maintenance-observations', headers=headers, json=payload())).status_code == 404
        assert (await async_client.get(f'/api/manager/orders/{bad_order_id}/maintenance-observations', headers=headers)).status_code == 404
    assert (await async_client.post(f'/api/manager/orders/{bad_branch_order_id}/maintenance-observations', headers=headers, json=payload())).status_code == 400
    await db.refresh(order)
    order.workflow_type = 'repair'; db.add(order); await db.commit()
    assert (await async_client.post(url, headers=headers, json=payload())).status_code == 400
    await db.refresh(order)
    order.workflow_type = 'maintenance'; db.add(order); await db.commit()
    finding = (await async_client.post(url, headers=headers, json=payload())).json()
    detail_url = f"/api/manager/maintenance-observations/{finding['id']}"
    photo = await async_client.post(detail_url+'/photos', headers=headers, data={'command_key': str(uuid4())}, files={'file': ('private.png', image_bytes(), 'image/png')})
    assert photo.status_code == 201
    attachment_id = photo.json()['id']
    user = StaffUser(username='observation-tenant-manager', display_name='Local manager', status='active', roles=['manager'], primary_role='manager')
    db.add(user); await db.flush()
    membership = TenantMembership(tenant_id=foreign_tenant_id, staff_user_id=user.id, role='manager', status='active')
    db.add(membership); await db.commit()
    token = create_access_token({'sub': user.username, 'staff_user_id': user.id, 'auth_source': 'staff_password', 'auth_version': user.auth_version})
    foreign_headers = {'Authorization': f'Bearer {token}'}
    own_url = f'/api/manager/orders/{invalid_order_ids[0]}/maintenance-observations'
    own = await async_client.post(own_url, headers=foreign_headers, json=payload(equipment_id=invalid_equipment_ids[0]))
    assert own.status_code == 201, own.text
    assert (await async_client.get(detail_url, headers=foreign_headers)).status_code == 404
    assert (await async_client.get(f'/api/manager/service-attachments/{attachment_id}/access', headers=foreign_headers)).status_code == 404
    assert (await async_client.patch(f'/api/manager/service-attachments/{attachment_id}', headers=foreign_headers, json={'order_id': finding['source_order_id'], 'equipment_id': None})).status_code == 404
    assert (await async_client.get(f'/api/manager/equipment/{invalid_equipment_ids[0]}/maintenance-observations', headers=headers)).status_code == 404
    assert (await async_client.patch(detail_url, headers=foreign_headers, json={**{k: finding[k] for k in ('equipment_id', 'equipment_description', 'facts', 'recommendation')}, 'expected_version': 1})).status_code == 404
    assert (await async_client.post(detail_url+'/photos', headers=foreign_headers, data={'command_key': str(uuid4())}, files={'file': ('x.png', image_bytes(), 'image/png')})).status_code == 404
    async def staff_auth():
        return AuthenticatedUser(username='staff', auth_source='user', role='installer', tenant_id=1, storefront_id=1)
    app.dependency_overrides[get_current_auth_context] = staff_auth
    assert (await async_client.get(url)).status_code == 403
    assert (await async_client.post(url, json=payload())).status_code == 403
    app.dependency_overrides.pop(get_current_auth_context)
    await db.refresh(membership)
    membership.status = 'disabled'; db.add(membership); await db.commit()
    assert (await async_client.get(own_url, headers=foreign_headers)).status_code == 403
    async_client.cookies.clear()
    assert (await async_client.get(url)).status_code == 401


@pytest.mark.asyncio
async def test_simultaneous_create_update_and_photo_commands(db_engine, tmp_path, monkeypatch):
    """Use independent transactions on this process's physical test database."""
    monkeypatch.setattr(settings, 'SERVICE_ATTACHMENT_LOCAL_DIR', str(tmp_path))
    scope = TenantScope(tenant_id=1, storefront_id=1)
    async with AsyncSession(db_engine, expire_on_commit=False) as seed:
        order, _, _ = await context(seed, OrderStatus.CLOSED)
        order_id = order.id
    create_payload = CreateMaintenanceObservation.model_validate(payload())
    async def create():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            return await Service.create(session, order_id=order_id, payload=create_payload, actor='manager-one', scope=scope)
    a, b = await asyncio.gather(create(), create())
    assert a.id == b.id
    async def update(facts):
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            try:
                return await Service.update(session, observation_id=a.id, payload=UpdateMaintenanceObservation(
                    equipment_description=a.equipment_description, facts=facts, recommendation=a.recommendation,
                    expected_version=1), actor=facts, scope=scope)
            except ObservationConflict:
                await session.rollback()
                return 'conflict'
    updates = await asyncio.gather(update('First correction'), update('Second correction'))
    assert sum(result == 'conflict' for result in updates) == 1
    winner = next(result for result in updates if result != 'conflict')
    assert winner.version == 2
    key = uuid4(); content = image_bytes()
    async def upload():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            return await Service.upload_photo(session, observation_id=a.id, key=key, content=content,
                                              filename='concurrent.png', mime_type='image/png', actor='manager', scope=scope)
    photos = await asyncio.gather(upload(), upload())
    photo_ids = [p['id'] if isinstance(p, dict) else p.id for p in photos]
    assert photo_ids[0] == photo_ids[1]
    async with AsyncSession(db_engine) as session:
        assert await session.scalar(select(func.count()).select_from(MaintenanceObservation)) == 1
        assert await session.scalar(select(func.count()).select_from(MaintenanceObservationRevision)) == 2
        assert await session.scalar(select(func.count()).select_from(MaintenanceObservationPhoto)) == 1
        assert await session.scalar(select(func.count()).select_from(ServiceAttachment)) == 1
        current = await Service.get(session, a.id, scope)
        assert current.facts == winner.facts
        assert (await session.get(Order, order_id)).status == OrderStatus.CLOSED


@pytest.mark.asyncio
@pytest.mark.parametrize('with_documents', [False, True])
async def test_source_order_delete_conflict_before_cleanup(async_client, db, with_documents):
    from models import IntegrationOutboxEvent
    headers = await login(async_client)
    order, _, event = await context(db)
    order_id, customer_id = order.id, order.customer_id
    await db.delete(event); await db.commit()
    finding = (await async_client.post(f'/api/manager/orders/{order_id}/maintenance-observations', headers=headers, json=payload())).json()
    if with_documents:
        db.add(OrderDocument(order_id=order_id, tenant_id=1, doc_type='act', number='KEEP-1108', google_file_id='keep-1108'))
        await db.commit()
    order_before = order.model_dump()
    before = [(row.id, row.model_dump()) for row in (await db.execute(select(OrderDocument))).scalars()]
    response = await async_client.delete(f'/api/manager/orders/{order_id}', headers=headers)
    assert response.status_code == 409, response.text
    assert 'замечания ТО' in response.json()['detail']['message']
    await db.refresh(order)
    assert order.model_dump() == order_before
    assert await db.get(MaintenanceObservation, finding['id']) is not None
    assert [(row.id, row.model_dump()) for row in (await db.execute(select(OrderDocument))).scalars()] == before
    assert await db.scalar(select(func.count()).select_from(IntegrationOutboxEvent)) == 0
    clean = Order(tenant_id=1, storefront_id=1, customer_id=customer_id, workflow_type='maintenance')
    db.add(clean); await db.commit(); clean_id = clean.id
    deleted = await async_client.delete(f'/api/manager/orders/{clean_id}', headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert await db.get(Order, clean_id) is None


@pytest.mark.asyncio
async def test_relocated_and_archived_equipment_keeps_historical_observation(async_client, db):
    headers = await login(async_client)
    order, equipment, _ = await context(db)
    order_id, equipment_id, original_branch, customer_id = order.id, equipment.id, order.customer_branch_id, order.customer_id
    site = CustomerBranch(customer_id=customer_id, name='New site', delivery_address='Local second site')
    replacement = CustomerEquipment(customer_id=customer_id, customer_branch_id=original_branch, display_name='Replacement')
    db.add_all([site,replacement]); await db.commit(); site_id, replacement_id = site.id, replacement.id
    source_url=f'/api/manager/orders/{order_id}/maintenance-observations'
    created = await async_client.post(source_url, headers=headers, json=payload(equipment_id=equipment_id))
    assert created.status_code == 201
    finding=created.json(); detail_url=f"/api/manager/maintenance-observations/{finding['id']}"
    moved=await async_client.patch(f'/api/manager/equipment/{equipment_id}', headers=headers, json={'customer_branch_id':site_id})
    assert moved.status_code == 200, moved.text
    assert (await async_client.get(source_url,headers=headers)).json()['total'] == 1
    detail=await async_client.get(detail_url,headers=headers)
    assert detail.status_code == 200 and detail.json()['equipment_link_state'] == 'moved'
    assert detail.json()['customer_branch_id'] == original_branch
    edit={k:finding[k] for k in ('equipment_id','equipment_description','facts','recommendation')}
    preserved=await async_client.patch(detail_url,headers=headers,json={**edit,'expected_version':1,'facts':'Уточнение на исходном объекте.'})
    assert preserved.status_code == 200, preserved.text
    archived=await async_client.patch(f'/api/manager/equipment/{equipment_id}',headers=headers,json={'is_archived':True})
    assert archived.status_code == 200, archived.text
    assert (await async_client.get(detail_url,headers=headers)).json()['equipment_link_state'] == 'archived'
    kept=await async_client.patch(detail_url,headers=headers,json={**edit,'expected_version':2})
    assert kept.status_code == 200
    cleared=await async_client.patch(detail_url,headers=headers,json={**edit,'equipment_id':None,'expected_version':3})
    assert cleared.status_code == 200 and cleared.json()['equipment_link_state'] == 'unlinked'
    # A new link still requires an active equipment on the immutable source site.
    bad=await async_client.patch(detail_url,headers=headers,json={**edit,'expected_version':4})
    assert bad.status_code == 400
    rebound=await async_client.patch(detail_url,headers=headers,json={**edit,'equipment_id':replacement_id,'expected_version':4})
    assert rebound.status_code == 200 and rebound.json()['equipment_link_state'] == 'current'
    async def foreign_scope():
        return AuthenticatedUser(username='other',auth_source='user',role='manager',tenant_id=999,storefront_id=999)
    app.dependency_overrides[get_current_auth_context]=foreign_scope
    try:
        assert (await async_client.get(detail_url)).status_code == 404
        assert (await async_client.get(source_url)).status_code == 404
        assert (await async_client.patch(detail_url,json={**edit,'equipment_id':None,'expected_version':5})).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_auth_context)
    other_store = Storefront(tenant_id=1, slug='history-other-store', display_name='Other storefront', status='active')
    db.add(other_store); await db.commit(); other_store_id=other_store.id
    async def wrong_storefront():
        return AuthenticatedUser(username='other',auth_source='user',role='manager',tenant_id=1,storefront_id=other_store_id)
    app.dependency_overrides[get_current_auth_context]=wrong_storefront
    try:
        assert (await async_client.get(detail_url)).status_code == 404
        assert (await async_client.get(source_url)).status_code == 404
        assert (await async_client.patch(detail_url,json={**edit,'equipment_id':None,'expected_version':5})).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_auth_context)


@pytest.mark.asyncio
async def test_observation_photo_rejects_generic_link_but_ordinary_photo_retains_editor(async_client, db, tmp_path, monkeypatch):
    from models import EquipmentAttachmentLink, OrderAttachmentLink
    monkeypatch.setattr(settings,'SERVICE_ATTACHMENT_LOCAL_DIR',str(tmp_path))
    headers=await login(async_client)
    order,equipment,_=await context(db)
    order_id,equipment_id,customer_id,branch_id=order.id,equipment.id,order.customer_id,order.customer_branch_id
    other=CustomerEquipment(customer_id=customer_id,customer_branch_id=branch_id,display_name='Other block')
    db.add(other); await db.commit(); other_id=other.id
    finding=(await async_client.post(f'/api/manager/orders/{order_id}/maintenance-observations',headers=headers,json=payload(equipment_id=equipment_id))).json()
    detail_url=f"/api/manager/maintenance-observations/{finding['id']}"
    photo=await async_client.post(detail_url+'/photos',headers=headers,data={'command_key':str(uuid4())},files={'file':('private.png',image_bytes(),'image/png')})
    assert photo.status_code == 201; photo_id=photo.json()['id']
    photo_url=f'/api/manager/service-attachments/{photo_id}'
    for change in ({'equipment_id':equipment_id},{'equipment_id':None},{'component_id':None},{'service_history_id':None}):
        denied=await async_client.patch(photo_url,headers=headers,json={'order_id':order_id,'caption':'must not apply',**change})
        assert denied.status_code == 400, denied.text
    caption=await async_client.patch(photo_url,headers=headers,json={'order_id':order_id,'caption':'Описание фото'})
    assert caption.status_code == 200
    # Simulate an independent link written by the already released editor.
    order_link=await db.scalar(select(OrderAttachmentLink).where(OrderAttachmentLink.attachment_id==photo_id))
    stale_link=EquipmentAttachmentLink(equipment_id=equipment_id,attachment_id=photo_id,order_attachment_link_id=order_link.id)
    db.add(stale_link); await db.commit(); stale_id=stale_link.id
    stale_list=await async_client.get(f'/api/manager/equipment/{equipment_id}/attachments',headers=headers)
    assert photo_id not in [item['id'] for item in stale_list.json()['items']]
    moved=await async_client.patch(detail_url,headers=headers,json={**{k:finding[k] for k in ('equipment_description','facts','recommendation')},'equipment_id':other_id,'expected_version':1})
    assert moved.status_code == 200
    await db.refresh(stale_link); assert stale_link.archived_at is not None
    assert [photo['id'] for photo in moved.json()['photos']] == [photo_id]
    assert await db.scalar(select(func.count()).select_from(EquipmentAttachmentLink).where(EquipmentAttachmentLink.attachment_id==photo_id,EquipmentAttachmentLink.archived_at.is_(None))) == 0
    for target in (equipment_id,other_id):
        listed=await async_client.get(f'/api/manager/equipment/{target}/attachments',headers=headers)
        assert listed.status_code == 200
        assert photo_id not in [item['id'] for item in listed.json()['items']]
    ordinary=await async_client.post(f'/api/manager/orders/{order_id}/attachments',headers=headers,files={'file':('ordinary.png',image_bytes(),'image/png')})
    assert ordinary.status_code == 201; ordinary_id=ordinary.json()['id']
    linked=await async_client.patch(f'/api/manager/service-attachments/{ordinary_id}',headers=headers,json={'order_id':order_id,'equipment_id':equipment_id})
    assert linked.status_code == 200 and linked.json()['equipment_id']==equipment_id
    relinked=await async_client.patch(f'/api/manager/service-attachments/{ordinary_id}',headers=headers,json={'order_id':order_id,'equipment_id':other_id})
    assert relinked.status_code == 200 and relinked.json()['equipment_id']==other_id
    cleared=await async_client.patch(f'/api/manager/service-attachments/{ordinary_id}',headers=headers,json={'order_id':order_id,'equipment_id':None})
    assert cleared.status_code == 200 and cleared.json()['equipment_id'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('first', ['create','delete'])
async def test_create_observation_and_delete_serialize_on_source_order(db_engine, first):
    from sqlalchemy.orm import sessionmaker
    from services.order_delete_command_service import OrderDeleteCommandService, OrderHasMaintenanceObservations
    from services.tenant_entity_access_service import TenantEntityAccessService
    factory=sessionmaker(db_engine,class_=AsyncSession,expire_on_commit=False)
    scope=TenantScope(1,1)
    async with factory() as seed:
        customer=Customer(tenant_id=1,name='Concurrent delete owner',phone='+375291108111')
        seed.add(customer); await seed.flush()
        order=Order(tenant_id=1,storefront_id=1,customer_id=customer.id,workflow_type='maintenance')
        seed.add(order); await seed.commit(); order_id=order.id
    async with factory() as owner:
        await TenantEntityAccessService.get_order(owner,order_id,tenant_scope=scope,for_update=True)
        async def competing():
            async with factory() as session:
                try:
                    if first=='create':
                        await OrderDeleteCommandService.delete_order(session,order_id,tenant_scope=scope)
                        return 'deleted'
                    await Service.create(session,order_id=order_id,payload=CreateMaintenanceObservation(**payload()),actor='test',scope=scope)
                    return 'created'
                except OrderHasMaintenanceObservations:
                    return 'conflict'
                except Exception as exc:
                    from services.maintenance_observation_service import ObservationNotFound
                    if isinstance(exc,ObservationNotFound): return 'not_found'
                    raise
        waiting=asyncio.create_task(competing())
        await asyncio.sleep(0.1)
        assert not waiting.done(), 'competitor must wait for source order lock'
        if first=='create':
            await Service.create(owner,order_id=order_id,payload=CreateMaintenanceObservation(**payload()),actor='test',scope=scope)
        else:
            await OrderDeleteCommandService.delete_order(owner,order_id,tenant_scope=scope)
        assert await asyncio.wait_for(waiting,5) == ('conflict' if first=='create' else 'not_found')
    async with factory() as check:
        assert (await check.get(Order,order_id) is not None) == (first=='create')
        assert await check.scalar(select(func.count()).select_from(MaintenanceObservation).where(MaintenanceObservation.source_order_id==order_id)) == (1 if first=='create' else 0)
