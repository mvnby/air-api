"""Real scoped HTTP/PostgreSQL evidence for explicit factual-act preparation."""
import asyncio
from copy import deepcopy
from io import BytesIO
from uuid import uuid4

import pytest
from docx import Document
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func

from core.config import settings
from models import (DocumentLegalEntity, MaintenanceContinuation, MaintenanceActPreparation, MaintenanceActSource,
                    Order, OrderDocument, OrderProposal, OrderInstaller, OrderWorkStage, Customer, CustomerBranch,
                    Storefront, Tenant, EquipmentServiceHistory)
from models.tenancy import TenantScope
from api_contracts.maintenance_observations import PrepareMaintenanceDefectAct, UpdateMaintenanceObservation
from modules.documents.application.maintenance_act_preparation import MaintenanceActPreparationService as Service
from modules.documents.application.lifecycle_service import ManagedDocumentService
from modules.documents.application.artifact_helpers import build_render_inputs
from modules.documents.infrastructure.renderers import NativeDocxRenderer
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from services.maintenance_observation_service import MaintenanceObservationService, ObservationConflict
from tests.integration.test_maintenance_observations_api import context, payload, login, image_bytes
from tests.integration.test_managed_document_lifecycle import FakePdfConverter
from models import OrderStatus, DocumentTemplateVersion, DocumentTemplate


async def seed(client, db, tmp_path, monkeypatch, status=OrderStatus.EXECUTION):
    monkeypatch.setattr(settings, 'SERVICE_ATTACHMENT_LOCAL_DIR', str(tmp_path))
    headers = await login(client)
    order, equipment, event = await context(db, status)
    issuer = DocumentLegalEntity(tenant_id=1, slug='maintenance-act', display_name='Сервис тестового исполнителя', legal_name='ООО «Сервис»', unp='100000001', is_default=True, requisites={})
    db.add(issuer); await db.commit()
    observations = []
    for desc, equip in [('Наружный блок у входа', equipment.id), ('Неизвестный блок на крыше', None)]:
        response = await client.post(f'/api/manager/orders/{order.id}/maintenance-observations', headers=headers,
                                     json=payload(equipment_id=equip, equipment_description=desc))
        assert response.status_code == 201, response.text
        observations.append(response.json())
    return headers, order, equipment, event, issuer, observations


def act_payload(issuer, observations, **changes):
    return {'command_key': str(uuid4()), 'issue_date': '2026-10-08', 'legal_entity_id': issuer.id,
            'observations': [{'observation_id': o['id'], 'expected_version': o['version']} for o in observations], **changes}


def url(order):
    return f'/api/manager/orders/{order.id}/maintenance-defect-acts'


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [OrderStatus.EXECUTION, OrderStatus.CLOSED])
async def test_prepare_replay_snapshot_and_native_lifecycle_preserve_to(async_client, db, tmp_path, monkeypatch, status):
    headers, order, equipment, event, issuer, observations = await seed(async_client, db, tmp_path, monkeypatch, status)
    old = OrderDocument(order_id=order.id, doc_type='act', number='historical-act', google_file_id='test-only')
    db.add(old); await db.commit()
    before_order, before_event, before_doc = order.model_dump(), event.model_dump(), old.model_dump()
    before_equipment = equipment.model_dump()
    uploaded = await async_client.post(f"/api/manager/maintenance-observations/{observations[0]['id']}/photos",
        headers=headers, data={'command_key': str(uuid4())}, files={'file': ('insulation.png', image_bytes(), 'image/png')})
    assert uploaded.status_code == 201, uploaded.text
    catalog = await async_client.get('/api/manager/document-system/placeholder-catalog?doc_type=maintenance_defect_act', headers=headers)
    assert catalog.status_code == 200 and [table['name'] for table in catalog.json()['tables']] == ['observations']
    command = act_payload(issuer, observations)
    prepared = await async_client.post(url(order), headers=headers, json=command)
    assert prepared.status_code == 201, prepared.text
    result = prepared.json(); assert result['status'] == 'draft'
    assert result['source_order_id'] == order.id and result['continuation_order_id'] != order.id
    continuation = await db.get(Order, result['continuation_order_id'])
    assert continuation.status == OrderStatus.NEGOTIATION and continuation.installation_date is None
    assert continuation.customer_id == order.customer_id and continuation.customer_branch_id == order.customer_branch_id
    assert await db.scalar(select(func.count()).select_from(OrderProposal)) == 0
    assert await db.scalar(select(func.count()).select_from(OrderInstaller)) == 0
    assert await db.scalar(select(func.count()).select_from(OrderWorkStage)) == 0
    draft = await db.get(OrderDocument, result['document_id'])
    snapshot = deepcopy(draft.render_snapshot)
    assert draft.official_number is None and draft.sent_at is None and draft.issued_at is None
    assert [s['version'] for s in snapshot['meta']['maintenance']['sources']] == [1, 1]
    assert len(snapshot['table_rows']['observations']) == 2
    assert snapshot['meta']['maintenance']['sources'][0]['photos'][0]['attachment_id'] == uploaded.json()['id']
    assert snapshot['meta']['maintenance']['sources'][1]['photos'] == []
    for text in ('потеря мощности', 'запрет эксплуатации', 'измерено', 'ущерб', 'проведена диагностика'):
        assert text not in str(snapshot).lower()
    storage = PrivateTemplateSourceStorage(LocalPrivateAttachmentStorage(tmp_path))
    artifacts = PrivateDocumentArtifactStorage(LocalPrivateAttachmentStorage(tmp_path))
    version = await db.get(DocumentTemplateVersion, draft.template_version_id)
    template = await db.get(DocumentTemplate, draft.document_template_id)
    source = await storage.read_persisted(tenant_id=1, template_id=template.id, version=version.version,
        storage_key=version.source_storage_key, filename=version.source_filename, checksum_sha256=version.checksum_sha256)
    rt, rc = build_render_inputs(template=template, version=version, source=source, snapshot=snapshot)
    generated = NativeDocxRenderer().render(rt, rc).content
    rendered = Document(BytesIO(generated))
    assert len(rendered.tables[0].rows) == 2
    assert 'Видимое повреждение' in rendered.tables[0].cell(0, 0).text
    assert 'Неизвестный блок' in rendered.tables[0].cell(1, 0).text
    assert 'Рекомендация (предстоящие действия)' in rendered.tables[0].cell(0, 0).text
    # This validates lifecycle persistence only; visual conversion is checked separately with real LibreOffice.
    issued = await ManagedDocumentService.issue(db, tenant_scope=TenantScope(1, 1), document_id=draft.id,
        template_storage=storage, artifact_storage=artifacts, pdf_converter=FakePdfConverter())
    assert issued.document.status == 'issued' and issued.document.sent_at is None
    assert issued.document.official_number == '001'
    frozen = deepcopy(issued.document.render_snapshot)
    obs = observations[0]
    corrected = await async_client.patch(f"/api/manager/maintenance-observations/{obs['id']}", headers=headers,
        json={**{k: obs[k] for k in ('equipment_id', 'equipment_description', 'recommendation')},
              'facts': 'Уточнённые факты следующей версии', 'expected_version': 1})
    assert corrected.status_code == 200, corrected.text
    await db.refresh(draft); assert draft.render_snapshot == frozen
    replay = await async_client.post(url(order), headers=headers, json=command)
    assert replay.status_code == 201 and replay.json()['document_id'] == draft.id
    reordered = await async_client.post(url(order), headers=headers, json={**command, 'observations': list(reversed(command['observations']))})
    assert reordered.status_code == 201 and reordered.json()['document_id'] == draft.id
    collision = await async_client.post(url(order), headers=headers, json={**command, 'issue_date': '2026-10-09'})
    assert collision.status_code == 409
    await db.refresh(order); await db.refresh(draft); await db.refresh(issuer)
    stale = await async_client.post(url(order), headers=headers, json={**command, 'command_key': str(uuid4())})
    assert stale.status_code == 409
    await db.refresh(order); await db.refresh(draft); await db.refresh(issuer); await db.refresh(continuation)
    updated = [corrected.json(), observations[1]]
    replacement = await async_client.post(url(order), headers=headers,
        json=act_payload(issuer, updated, replaces_document_id=draft.id))
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()['continuation_order_id'] == continuation.id
    assert await db.scalar(select(func.count()).select_from(MaintenanceContinuation)) == 1
    assert await db.scalar(select(func.count()).select_from(MaintenanceActPreparation)) == 2
    await db.refresh(order); await db.refresh(old); await db.refresh(event); await db.refresh(equipment)
    assert equipment.model_dump() == before_equipment
    assert order.model_dump() == before_order and old.model_dump() == before_doc and event.model_dump() == before_event
    assert await db.scalar(select(func.count()).select_from(EquipmentServiceHistory)) == 1
    listing = await async_client.get(url(order)+'?limit=1&offset=1', headers=headers)
    assert listing.status_code == 200 and listing.json()['total'] == 2 and len(listing.json()['items']) == 1
    assert (await async_client.get(url(order)+'?limit=101', headers=headers)).status_code == 422
    continuation_id, original_order_id, draft_id, issuer_id = continuation.id, order.id, draft.id, issuer.id
    assert (await async_client.delete(f'/api/manager/orders/{continuation_id}', headers=headers)).status_code == 409
    assert (await async_client.delete(f'/api/manager/orders/{original_order_id}', headers=headers)).status_code == 409
    assert (await async_client.delete(f'/api/manager/document-system/documents/{draft_id}/draft', headers=headers)).status_code == 409
    linked_draft_id = replacement.json()['document_id']
    linked_delete = await async_client.delete(f'/api/manager/document-system/documents/{linked_draft_id}/draft', headers=headers)
    assert linked_delete.status_code == 409 and 'замечаниями ТО' in linked_delete.text
    generic = await async_client.post(f'/api/manager/document-system/orders/{original_order_id}/documents/drafts', headers=headers,
        json={'document_type': 'maintenance_defect_act', 'legal_entity_id': issuer_id, 'issue_date': '2026-10-08'})
    assert generic.status_code in (400, 409)


@pytest.mark.asyncio
async def test_scope_failures_and_missing_context_leave_no_container(async_client, db, tmp_path, monkeypatch):
    headers, order, equipment, event, issuer, observations = await seed(async_client, db, tmp_path, monkeypatch)
    other_order, _, _ = await context(db)
    other_obs = await async_client.post(f'/api/manager/orders/{other_order.id}/maintenance-observations', headers=headers, json=payload())
    assert other_obs.status_code == 201
    mixed = act_payload(issuer, [observations[0], other_obs.json()])
    response = await async_client.post(url(order), headers=headers, json=mixed)
    assert response.status_code == 400
    await db.refresh(order); await db.refresh(issuer)
    assert await db.scalar(select(func.count()).select_from(MaintenanceContinuation)) == 0
    command = act_payload(issuer, observations)
    async_client.cookies.clear()
    assert (await async_client.post(url(order), json=command)).status_code in (401, 403)
    # A role scoped to the source cannot select a foreign tenant/storefront source or issuer.
    from core.security import AuthenticatedUser, get_current_auth_context
    from main import app
    foreign_tenant = Tenant(slug='act-foreign', display_name='Foreign')
    db.add(foreign_tenant); await db.flush()
    foreign_store = Storefront(tenant_id=foreign_tenant.id, slug='foreign', display_name='Foreign', status='active')
    db.add(foreign_store); await db.flush()
    foreign_customer = Customer(tenant_id=foreign_tenant.id, name='Foreign customer', phone='111')
    db.add(foreign_customer); await db.flush()
    foreign_order = Order(tenant_id=foreign_tenant.id, storefront_id=foreign_store.id, customer_id=foreign_customer.id, workflow_type='maintenance')
    db.add(foreign_order); await db.commit()
    # Non-system scope still uses the real HTTP dependency chain after its auth-context boundary.
    foreign_storefront_id = foreign_store.id
    auth = AuthenticatedUser(username='manager', auth_source='jwt', tenant_id=1, storefront_id=1, role='manager', is_system_tenant=True)
    app.dependency_overrides[get_current_auth_context] = lambda: auth
    try:
        assert (await async_client.post(url(foreign_order), headers=headers, json=command)).status_code == 404
        from dataclasses import replace
        auth = replace(auth, storefront_id=foreign_storefront_id)
        await db.refresh(order)
        assert (await async_client.post(url(order), headers=headers, json=command)).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_auth_context, None)
    await db.refresh(order); await db.refresh(other_order)
    # Saved observation context cannot silently adopt a source order's newly selected customer/site.
    order.customer_id = other_order.customer_id; order.customer_branch_id = other_order.customer_branch_id
    db.add(order); await db.commit()
    response = await async_client.post(url(order), headers=headers, json=command)
    assert response.status_code == 400
    await db.refresh(order)
    order.customer_id = observations[0]['customer_id']; order.customer_branch_id = observations[0]['customer_branch_id']; db.add(order)
    branch = await db.get(CustomerBranch, order.customer_branch_id); branch.delivery_address = ''; db.add(branch); await db.commit()
    response = await async_client.post(url(order), headers=headers, json=command)
    assert response.status_code == 400 and 'Адрес объекта' in response.text
    assert await db.scalar(select(func.count()).select_from(MaintenanceContinuation)) == 0
    assert await db.scalar(select(func.count()).select_from(MaintenanceActPreparation)) == 0


@pytest.mark.asyncio
async def test_concurrent_same_and_different_keys_reuse_continuation(async_client, db, db_engine, tmp_path, monkeypatch):
    order, issuer, observations = await concurrent_seed(db_engine, tmp_path, monkeypatch)
    order_id = order.id; command = PrepareMaintenanceDefectAct(**act_payload(issuer, observations))
    storage = PrivateTemplateSourceStorage(LocalPrivateAttachmentStorage(tmp_path))
    async def prepare(payload):
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            return await Service.prepare(session, source_order_id=order_id, payload=payload, actor='manager', scope=TenantScope(1, 1), storage=storage)
    results = await asyncio.gather(prepare(command), prepare(command))
    assert results[0]['document_id'] == results[1]['document_id']
    following = await asyncio.gather(prepare(command.model_copy(update={'command_key': uuid4()})), prepare(command.model_copy(update={'command_key': uuid4()})))
    assert following[0]['continuation_order_id'] == following[1]['continuation_order_id'] == results[0]['continuation_order_id']
    assert await db.scalar(select(func.count()).select_from(MaintenanceContinuation)) == 1
    assert await db.scalar(select(func.count()).select_from(MaintenanceActPreparation)) == 3
    assert await db.scalar(select(func.count()).select_from(MaintenanceActSource)) == 6


@pytest.mark.asyncio
async def test_prepare_serializes_with_correction(async_client, db, db_engine, tmp_path, monkeypatch):
    order, issuer, observations = await concurrent_seed(db_engine, tmp_path, monkeypatch)
    order_id = order.id; obs = observations[0]
    command = PrepareMaintenanceDefectAct(**act_payload(issuer, [obs]))
    storage = PrivateTemplateSourceStorage(LocalPrivateAttachmentStorage(tmp_path))
    async with AsyncSession(db_engine, expire_on_commit=False) as editing:
        finding = await MaintenanceObservationService.get(editing, obs['id'], TenantScope(1, 1), lock=True)
        async def preparing():
            async with AsyncSession(db_engine, expire_on_commit=False) as session:
                with pytest.raises(ObservationConflict, match='изменено'):
                    await Service.prepare(session, source_order_id=order_id, payload=command, actor='manager', scope=TenantScope(1, 1), storage=storage)
        pending = asyncio.create_task(preparing())
        await asyncio.sleep(.1)
        assert not pending.done()
        edit = UpdateMaintenanceObservation(**{k: obs[k] for k in ('equipment_id', 'equipment_description', 'facts', 'recommendation')}, expected_version=1)
        await MaintenanceObservationService.update(editing, observation_id=finding.id, payload=edit, actor='manager', scope=TenantScope(1, 1))
        await pending
    assert await db.scalar(select(func.count()).select_from(MaintenanceContinuation)) == 0


async def concurrent_seed(engine, tmp_path, monkeypatch):
    from api_contracts.maintenance_observations import CreateMaintenanceObservation
    monkeypatch.setattr(settings, 'SERVICE_ATTACHMENT_LOCAL_DIR', str(tmp_path))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        order, _, _ = await context(session)
        issuer = DocumentLegalEntity(tenant_id=1, slug='concurrent-act', display_name='Сервис', requisites={})
        session.add(issuer); await session.commit()
        observations = []
        for description in ('Первый блок', 'Второй блок'):
            result = await MaintenanceObservationService.create(session, order_id=order.id, scope=TenantScope(1, 1), actor='manager',
                payload=CreateMaintenanceObservation(**payload(equipment_description=description)))
            observations.append(result.model_dump())
        return order, issuer, observations


@pytest.mark.asyncio
async def test_live_foreign_membership_private_photos_and_document_access(async_client, db, tmp_path, monkeypatch):
    from core.security import create_access_token
    from models import StaffUser, TenantMembership, CustomerEquipment
    headers, order, equipment, _, issuer, observations = await seed(async_client, db, tmp_path, monkeypatch)
    source_url = url(order)
    tenant = Tenant(slug='foreign-act-live', display_name='Foreign')
    db.add(tenant); await db.flush()
    store = Storefront(tenant_id=tenant.id, slug='main', display_name='Foreign', is_default=True, status='active')
    customer = Customer(tenant_id=tenant.id, name='Foreign customer', phone='foreign-test')
    foreign_issuer = DocumentLegalEntity(tenant_id=tenant.id, slug='issuer', display_name='Foreign service', requisites={})
    user = StaffUser(username='act-foreign-manager', display_name='Foreign Manager', status='active', roles=['manager'], primary_role='manager')
    db.add_all([store, customer, foreign_issuer, user]); await db.flush()
    branch = CustomerBranch(customer_id=customer.id, name='Foreign site', delivery_address='Foreign address')
    membership = TenantMembership(tenant_id=tenant.id, staff_user_id=user.id, role='manager', status='active')
    db.add_all([branch, membership]); await db.flush()
    foreign = Order(tenant_id=tenant.id, storefront_id=store.id, customer_id=customer.id, customer_branch_id=branch.id, workflow_type='maintenance', status=OrderStatus.CLOSED)
    db.add(foreign); await db.commit()
    token = create_access_token({'sub': user.username, 'staff_user_id': user.id, 'auth_source': 'staff_password', 'auth_version': user.auth_version})
    foreign_headers = {'Authorization': f'Bearer {token}'}
    foreign_url = url(foreign); foreign_issuer_id = foreign_issuer.id
    created = await async_client.post(f'/api/manager/orders/{foreign.id}/maintenance-observations', headers=foreign_headers, json=payload())
    assert created.status_code == 201, created.text
    foreign_observation = created.json()
    photo = await async_client.post(f"/api/manager/maintenance-observations/{foreign_observation['id']}/photos", headers=foreign_headers,
        data={'command_key': str(uuid4())}, files={'file': ('private.png', image_bytes(), 'image/png')})
    assert photo.status_code == 201, photo.text
    attachment_id = photo.json()['id']
    foreign_command = {'command_key': str(uuid4()), 'issue_date': '2026-10-08', 'legal_entity_id': foreign_issuer_id,
                       'observations': [{'observation_id': foreign_observation['id'], 'expected_version': 1}]}
    prepared = await async_client.post(foreign_url, headers=foreign_headers, json=foreign_command)
    assert prepared.status_code == 201, prepared.text
    doc_id = prepared.json()['document_id']; continuation_id = prepared.json()['continuation_order_id']
    own_command = act_payload(issuer, observations)
    for target, command in [(source_url, {**own_command, 'legal_entity_id': foreign_issuer_id}),
                             (source_url, {**own_command, 'observations': foreign_command['observations']}),
                             (foreign_url, foreign_command)]:
        response = await async_client.post(target, headers=headers, json=command)
        assert response.status_code == 404, response.text
    for target in [foreign_url, f'/api/manager/service-attachments/{attachment_id}/access',
                   f'/api/manager/document-system/orders/{continuation_id}/documents',
                   f'/api/manager/document-system/documents/{doc_id}/preview',
                   f'/api/manager/document-system/documents/{doc_id}/artifacts']:
        assert (await async_client.get(target, headers=headers)).status_code == 404
    # Archived and relocated equipment remain historical source context, safely scoped.
    await db.refresh(equipment); equipment.is_archived = True; db.add(equipment); await db.commit()
    own = await async_client.post(source_url, headers=headers, json=own_command)
    assert own.status_code == 201, own.text
    own_doc = await db.get(OrderDocument, own.json()['document_id'])
    assert own_doc.render_snapshot['meta']['maintenance']['sources'][0]['content']['equipment_id'] == equipment.id
    # An unrelated site change is rejected before any continuation mutation or cleanup.
    other_site = CustomerBranch(customer_id=observations[0]['customer_id'], name='Another site', delivery_address='Another site address')
    db.add(other_site); await db.commit()
    change = await async_client.patch(f"/api/manager/orders/{own.json()['continuation_order_id']}", headers=headers, json={'customer_branch_id': other_site.id})
    assert change.status_code == 400, change.text
    await db.refresh(membership); membership.status = 'disabled'; db.add(membership); await db.commit()
    assert (await async_client.get(foreign_url, headers=foreign_headers)).status_code == 403
