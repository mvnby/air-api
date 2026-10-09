"""Physical PostgreSQL tests for consent distinct from documents, execution and resolution."""
import asyncio
from copy import deepcopy
from uuid import uuid4
import pytest
from sqlmodel import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from models import (Order, OrderStatus, OrderProposal, OrderServiceLink, MaintenanceOffer, MaintenanceOfferEvent,
    MaintenanceResolution, MaintenanceContinuation, EquipmentServiceHistory, OrderInstaller, OrderWorkStage)
from models.tenancy import TenantScope
from api_contracts.maintenance_offers import MaintenanceOfferCommand, PrepareMaintenanceOffer
from services.maintenance_offer_service import MaintenanceOfferService as Service
from services.maintenance_observation_service import ObservationConflict
from tests.integration.test_maintenance_defect_acts_api import seed


async def setup(client, db, tmp_path, monkeypatch):
    headers, source, equipment, old_event, issuer, observations = await seed(client, db, tmp_path, monkeypatch, OrderStatus.CLOSED)
    response = await client.post(f'/api/manager/orders/{source.id}/maintenance-workspace', headers=headers)
    assert response.status_code == 200, response.text
    order_id = response.json()['continuation_order_id']
    proposal = OrderProposal(order_id=order_id, name='Диагностика и ремонт', is_selected=True)
    db.add(proposal); await db.flush()
    lines = [OrderServiceLink(order_id=order_id, proposal_id=proposal.id, title='Ремонт изоляции', quantity=2, price='120.25'),
             OrderServiceLink(order_id=order_id, proposal_id=proposal.id, title='Диагностика блока', quantity=1, price='35.50')]
    db.add_all(lines); await db.commit()
    payload = dict(command_key=str(uuid4()), proposal_id=proposal.id, lines=[dict(kind='service', line_id=l.id,
        observation_id=o['id'], expected_version=o['version'], purpose='repair' if n == 0 else 'diagnosis') for n, (l, o) in enumerate(zip(lines, observations))])
    response = await client.post(f'/api/manager/orders/{source.id}/maintenance-offers', json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return headers, source, order_id, proposal, lines, observations, response.json(), payload, old_event


def action(offer, kind, **changes):
    return {**dict(command_key=str(uuid4()), expected_version=offer['version'], action=kind, source='Письмо клиента',
                comment='Подтверждение выбранного состава', occurred_at='2026-10-09T10:00:00+03:00', accepted_lines=[]), **changes}


async def command(client, headers, source, offer, kind, **changes):
    result = await client.post(f"/api/manager/orders/{source.id}/maintenance-offers/{offer['id']}/commands", headers=headers, json=action(offer, kind, **changes))
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.asyncio
async def test_partial_consent_same_card_resolution_separate_and_history(async_client, db, tmp_path, monkeypatch):
    headers, source, order_id, proposal, lines, observations, offer, payload, old_event = await setup(async_client, db, tmp_path, monkeypatch)
    frozen = deepcopy(offer['snapshot'])
    original = source.model_dump(); history_before = await db.scalar(select(func.count()).select_from(EquipmentServiceHistory))
    from services.equipment_maintenance_plan_service import EquipmentMaintenancePlanService
    before_plan = await EquipmentMaintenancePlanService.latest_maintenance_by_equipment(db, [old_event.equipment_id])
    old_event_before = old_event.model_dump()
    replay = await async_client.post(f'/api/manager/orders/{source.id}/maintenance-offers', headers=headers, json=payload)
    assert replay.json()['id'] == offer['id']
    offer = await command(async_client, headers, source, offer, 'issue')
    offer = await command(async_client, headers, source, offer, 'send')
    offer = await command(async_client, headers, source, offer, 'accept', accepted_lines=[f'service:{lines[0].id}'])
    repair = await db.get(Order, order_id)
    assert repair.status == OrderStatus.NEGOTIATION
    assert await db.scalar(select(func.count()).select_from(MaintenanceResolution)) == 0
    assert await db.scalar(select(func.count()).select_from(EquipmentServiceHistory)) == history_before
    offer = await command(async_client, headers, source, offer, 'continue')
    repair = await db.get(Order, order_id)
    await db.refresh(repair)
    approved = await db.scalar(select(OrderProposal).where(OrderProposal.order_id == order_id, OrderProposal.is_selected.is_(True)))
    approved_lines = (await db.execute(select(OrderServiceLink).where(OrderServiceLink.proposal_id == approved.id))).scalars().all()
    assert repair.status == OrderStatus.EXECUTION
    assert [(l.title, l.quantity, str(l.price)) for l in approved_lines] == [('Ремонт изоляции', 2, '120.25')]
    assert repair.installation_date is None and repair.customer_contract_id is None
    assert await db.scalar(select(func.count()).select_from(OrderInstaller)) == 0
    assert await db.scalar(select(func.count()).select_from(OrderWorkStage)) == 0
    assert await db.scalar(select(func.count()).select_from(MaintenanceContinuation)) == 1
    await db.refresh(proposal)
    assert proposal.is_selected is False
    assert (await db.get(Order, source.id)).model_dump() == original
    assert offer['snapshot'] == frozen
    # Native/legacy ordinary document selection sees only the approved subset.
    from services.document_service import DocumentService
    from services import document_service
    import googleapiclient.discovery
    tables = []
    class FakeGoogle:
        creds = object()
        def copy_template(self, *args): return {'file_id': 'maintenance-consent-invoice', 'edit_url': 'https://example.invalid/test-only'}
        def replace_placeholders(self, *args): pass
        def _fill_table(self, docs_service, file_id, table_data, has_footer): tables.append(table_data)
        def delete_file(self, *args): pass
    monkeypatch.setattr(document_service, 'get_google_service', lambda: FakeGoogle())
    monkeypatch.setattr(googleapiclient.discovery, 'build', lambda *a, **k: object())
    document = await DocumentService._create_new_document(db, order_id=order_id, doc_type='invoice')
    assert document.proposal_id == approved.id
    assert 'Ремонт изоляции' in str(tables) and 'Диагностика блока' not in str(tables)

    resolution = dict(command_key=str(uuid4()), expected_version=1, offer_id=offer['id'], evidence='Изоляция заменена, проверено на месте, фото в замечании', resolved_at='2026-10-09T12:00:00+03:00')
    response = await async_client.post(f"/api/manager/maintenance-observations/{observations[1]['id']}/resolution", headers=headers, json=resolution)
    assert response.status_code == 409
    response = await async_client.post(f"/api/manager/maintenance-observations/{observations[0]['id']}/resolution", headers=headers, json=resolution)
    assert response.status_code == 200, response.text
    same = await async_client.post(f"/api/manager/maintenance-observations/{observations[0]['id']}/resolution", headers=headers, json=resolution)
    assert same.json()['id'] == response.json()['id']
    assert await db.scalar(select(func.count()).select_from(EquipmentServiceHistory)) == history_before + 1
    assert await db.scalar(select(func.count()).select_from(MaintenanceResolution)) == 1
    await db.refresh(old_event)
    assert await EquipmentMaintenancePlanService.latest_maintenance_by_equipment(db, [old_event.equipment_id]) == before_plan
    assert old_event.model_dump() == old_event_before
    created_history = await db.get(EquipmentServiceHistory, response.json()['history_id'])
    assert created_history.event_type == 'repair' and created_history.order_id == order_id
    assert created_history.event_date.isoformat() == '2026-10-09T09:00:00'


@pytest.mark.asyncio
async def test_stale_composition_version_and_rejected_deferred_do_not_resolve(async_client, db, tmp_path, monkeypatch):
    headers, source, order_id, proposal, lines, observations, offer, payload, _ = await setup(async_client, db, tmp_path, monkeypatch)
    offer = await command(async_client, headers, source, offer, 'issue')
    offer = await command(async_client, headers, source, offer, 'send')
    offer = await command(async_client, headers, source, offer, 'reject')
    offer = await command(async_client, headers, source, offer, 'defer')
    assert await db.scalar(select(func.count()).select_from(MaintenanceResolution)) == 0
    assert (await db.get(Order, order_id)).status == OrderStatus.NEGOTIATION
    lines[0].price = '999'; db.add(lines[0]); await db.commit()
    bad = action(offer, 'accept', accepted_lines=[f'service:{lines[0].id}'])
    response = await async_client.post(f"/api/manager/orders/{source.id}/maintenance-offers/{offer['id']}/commands", headers=headers, json=bad)
    assert response.status_code == 409
    assert await db.scalar(select(func.count()).select_from(MaintenanceOfferEvent)) == 4
    assert await db.scalar(select(func.count()).select_from(OrderProposal)) == 1
    assert Service.public_snapshot((await db.get(MaintenanceOffer, offer['id'])).snapshot) == offer['snapshot']


@pytest.mark.asyncio
async def test_concurrent_replay_and_stale_version_are_serialized(db, db_engine, tmp_path, monkeypatch):
    from tests.integration.test_maintenance_defect_acts_api import concurrent_seed
    source, _, observations = await concurrent_seed(db_engine, tmp_path, monkeypatch)
    source_id = source.id
    scope = TenantScope(1, 1)
    async with AsyncSession(db_engine, expire_on_commit=False) as own:
        workspace = await Service.workspace(own, source_order_id=source_id, scope=scope, actor='manager')
        proposal = OrderProposal(order_id=workspace['continuation_order_id'], name='Ремонт', is_selected=True)
        own.add(proposal); await own.flush()
        line = OrderServiceLink(order_id=proposal.order_id, proposal_id=proposal.id, title='Ремонт', quantity=1, price=100)
        own.add(line); await own.commit()
        offer = await Service.prepare(own, source_order_id=source_id, scope=scope, actor='manager', payload=PrepareMaintenanceOffer(
            command_key=uuid4(), proposal_id=proposal.id, lines=[dict(kind='service', line_id=line.id, observation_id=observations[0]['id'], expected_version=1, purpose='repair')]))
    request = MaintenanceOfferCommand(**action(offer, 'issue'))
    async def issue():
        async with AsyncSession(db_engine, expire_on_commit=False) as own:
            return await Service.command(own, source_order_id=source_id, offer_id=offer['id'], payload=request, scope=scope, actor='test')
    results = await asyncio.gather(issue(), issue())
    assert [x['version'] for x in results] == [1, 1]
    assert await db.scalar(select(func.count()).select_from(MaintenanceOfferEvent)) == 1
    async with AsyncSession(db_engine, expire_on_commit=False) as own:
        sent = await Service.command(own, source_order_id=source_id, offer_id=offer['id'], payload=MaintenanceOfferCommand(**action(results[0], 'send')), scope=scope, actor='test')
        accepted = await Service.command(own, source_order_id=source_id, offer_id=offer['id'], payload=MaintenanceOfferCommand(**action(sent, 'accept', accepted_lines=[f'service:{line.id}'])), scope=scope, actor='test')
    continuation_request = MaintenanceOfferCommand(**action(accepted, 'continue'))
    async def continuing():
        async with AsyncSession(db_engine, expire_on_commit=False) as own:
            return await Service.command(own, source_order_id=source_id, offer_id=offer['id'], payload=continuation_request, scope=scope, actor='test')
    continued = await asyncio.gather(continuing(), continuing())
    assert continued[0]['events'][-1]['details']['approved_proposal_id'] == continued[1]['events'][-1]['details']['approved_proposal_id']
    assert await db.scalar(select(func.count()).select_from(OrderProposal)) == 2
    assert await db.scalar(select(func.count()).select_from(MaintenanceOfferEvent)) == 4
    async with AsyncSession(db_engine, expire_on_commit=False) as own:
        with pytest.raises(ObservationConflict):
            await Service.command(own, source_order_id=source_id, offer_id=offer['id'], payload=MaintenanceOfferCommand(**action(offer, 'send')), scope=scope, actor='test')
        with pytest.raises(ObservationConflict):
            await Service.command(own, source_order_id=source_id, offer_id=offer['id'], payload=request.model_copy(update={'comment': 'Different'}), scope=scope, actor='test')


@pytest.mark.asyncio
async def test_generic_commands_cannot_bypass_consent_or_replace_approved_lines(async_client, db, tmp_path, monkeypatch):
    from services.order_update.command import OrderUpdateCommandService
    from services.order_proposal_command_service import OrderProposalCommandService
    from schemas import ManagerOrderUpdatePayload, OrderProposalUpdatePayload
    headers, source, order_id, proposal, lines, observations, offer, payload, _ = await setup(async_client, db, tmp_path, monkeypatch)
    from types import SimpleNamespace
    proposal_id = proposal.id
    line_id = lines[0].id
    source = SimpleNamespace(id=source.id)
    scope = TenantScope(tenant_id=1, storefront_id=1)
    with pytest.raises(ValueError, match='согласие'):
        await OrderUpdateCommandService.update_order_for_manager(db, order_id, ManagerOrderUpdatePayload(status='execution'), tenant_scope=scope)
    with pytest.raises(ValueError, match='согласием'):
        await OrderProposalCommandService.update_order_proposal(db, order_id, proposal_id, OrderProposalUpdatePayload(status='approved'), tenant_scope=scope)
    for kind in ['issue', 'send']:
        offer = await command(async_client, headers, source, offer, kind)
    offer = await command(async_client, headers, source, offer, 'accept', accepted_lines=[f'service:{line_id}'])
    offer = await command(async_client, headers, source, offer, 'continue')
    approved_id = offer['events'][-1]['details']['approved_proposal_id']
    with pytest.raises(ValueError, match='согласием'):
        await OrderProposalCommandService.update_order_proposal(db, order_id, approved_id, OrderProposalUpdatePayload(status='draft'), tenant_scope=scope)
    with pytest.raises(ValueError, match='согласием'):
        await OrderProposalCommandService.select_order_proposal(db, order_id, proposal_id, tenant_scope=scope)


@pytest.mark.asyncio
async def test_diagnosis_then_known_repair_reuses_card_and_preserves_history(async_client, db, tmp_path, monkeypatch):
    headers, source, order_id, proposal, lines, observations, offer, payload, _ = await setup(async_client, db, tmp_path, monkeypatch)
    for kind in ['issue', 'send']:
        offer = await command(async_client, headers, source, offer, kind)
    offer = await command(async_client, headers, source, offer, 'accept', accepted_lines=[f'service:{lines[1].id}'])
    offer = await command(async_client, headers, source, offer, 'continue')
    first_approved = offer['events'][-1]['details']['approved_proposal_id']
    from schemas import OrderProposalCreatePayload, ManagerOrderUpdatePayload
    from services.order_proposal_command_service import OrderProposalCommandService
    from services.order_update.command import OrderUpdateCommandService
    scope = TenantScope(1, 1)
    detail = await OrderProposalCommandService.create_order_proposal(db, order_id,
        OrderProposalCreatePayload(name='Ремонт после диагностики', duplicate_from_proposal_id=first_approved), tenant_scope=scope)
    second = next(p for p in detail['proposals'] if p['name'] == 'Ремонт после диагностики')
    assert not second['is_selected']
    assert next(p for p in detail['proposals'] if p['is_selected'])['id'] == first_approved
    detail = await OrderUpdateCommandService.update_order_for_manager(db, order_id,
        ManagerOrderUpdatePayload(line_proposal_id=second['id'], services=[dict(title='Замена детали по диагностике', quantity=1, price=180.75)]), tenant_scope=scope)
    assert next(p for p in detail['proposals'] if p['is_selected'])['id'] == first_approved
    line = await db.scalar(select(OrderServiceLink).where(OrderServiceLink.proposal_id == second['id']))
    request = dict(command_key=str(uuid4()), proposal_id=second['id'], lines=[dict(kind='service', line_id=line.id,
        observation_id=observations[1]['id'], expected_version=1, purpose='repair')])
    response = await async_client.post(f'/api/manager/orders/{source.id}/maintenance-offers', headers=headers, json=request)
    assert response.status_code == 201, response.text
    repair_offer = response.json()
    for kind in ['issue', 'send']:
        repair_offer = await command(async_client, headers, source, repair_offer, kind)
    repair_offer = await command(async_client, headers, source, repair_offer, 'accept', accepted_lines=[f'service:{line.id}'])
    repair_offer = await command(async_client, headers, source, repair_offer, 'continue')
    assert repair_offer['continuation_order_id'] == order_id
    assert await db.scalar(select(func.count()).select_from(MaintenanceContinuation)) == 1
    assert await db.scalar(select(func.count()).select_from(MaintenanceResolution)) == 0
    historical = await db.get(OrderProposal, first_approved)
    await db.refresh(historical)
    assert historical.status == 'approved' and not historical.is_selected
    assert await db.scalar(select(func.count()).select_from(OrderServiceLink).where(OrderServiceLink.proposal_id == first_approved)) == 1
    assert Service.public_snapshot((await db.get(MaintenanceOffer, offer['id'])).snapshot) == offer['snapshot']


@pytest.mark.asyncio
async def test_scope_and_invalid_subset_fail_without_side_effects(async_client, db, tmp_path, monkeypatch):
    from services.maintenance_observation_service import ObservationNotFound
    headers, source, order_id, proposal, lines, observations, offer, payload, _ = await setup(async_client, db, tmp_path, monkeypatch)
    source_id = source.id
    for scope in [TenantScope(999, 1), TenantScope(1, 999)]:
        with pytest.raises(ObservationNotFound):
            await Service.list(db, source_order_id=source_id, scope=scope)
    for kind in ['issue', 'send']:
        offer = await command(async_client, headers, source, offer, kind)
    bad = action(offer, 'accept', accepted_lines=['service:999999'])
    response = await async_client.post(f"/api/manager/orders/{source_id}/maintenance-offers/{offer['id']}/commands", headers=headers, json=bad)
    assert response.status_code == 400, response.text
    assert await db.scalar(select(func.count()).select_from(MaintenanceOfferEvent)) == 2
    assert await db.scalar(select(func.count()).select_from(OrderProposal)) == 1
    assert await db.scalar(select(func.count()).select_from(MaintenanceResolution)) == 0
    customer_id = (await db.get(MaintenanceContinuation, 1)).customer_id
    response = await async_client.get(f'/api/manager/customers/{customer_id}/maintenance-observations', headers=headers)
    assert response.status_code == 200 and response.json()['total'] == 2
    response = await async_client.get(f'/api/manager/customers/{customer_id}/maintenance-observations?branch_id=9999', headers=headers)
    assert response.status_code == 200 and response.json()['total'] == 0


@pytest.mark.asyncio
async def test_observation_revision_drift_and_new_offer_supersede_old_consent(async_client, db, tmp_path, monkeypatch):
    from services.maintenance_observation_service import MaintenanceObservationService
    from api_contracts.maintenance_observations import UpdateMaintenanceObservation
    headers, source, order_id, proposal, lines, observations, offer, payload, _ = await setup(async_client, db, tmp_path, monkeypatch)
    obs = observations[0]
    source_id = source.id
    await MaintenanceObservationService.update(db, observation_id=obs['id'], actor='manager', scope=TenantScope(1,1), payload=UpdateMaintenanceObservation(
        **{k: obs[k] for k in ('equipment_id','equipment_description','facts','recommendation')}, expected_version=1))
    response = await async_client.post(f"/api/manager/orders/{source_id}/maintenance-offers/{offer['id']}/commands", headers=headers, json=action(offer, 'issue'))
    assert response.status_code == 409
    assert await db.scalar(select(func.count()).select_from(MaintenanceOfferEvent)) == 0
    payload['command_key'] = str(uuid4()); payload['lines'][0]['expected_version'] = 2
    response = await async_client.post(f'/api/manager/orders/{source_id}/maintenance-offers', headers=headers, json=payload)
    assert response.status_code == 201, response.text
    response = await async_client.post(f"/api/manager/orders/{source_id}/maintenance-offers/{offer['id']}/commands", headers=headers, json=action(offer, 'issue'))
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_role_gate_and_fixed_currency_override_are_explicit(async_client, db, tmp_path, monkeypatch):
    from core.security import get_current_auth_context, AuthenticatedUser
    from main import app
    headers, source, order_id, proposal, lines, observations, offer, payload, _ = await setup(async_client, db, tmp_path, monkeypatch)
    source_id = source.id
    repair = await db.get(Order, order_id); repair.target_currency_amount = 99; db.add(repair); await db.commit()
    response = await async_client.post(f'/api/manager/orders/{source_id}/maintenance-offers', headers=headers,
        json={**payload, 'command_key': str(uuid4())})
    assert response.status_code == 400 and 'суммы' in response.json()['detail']
    async def installer():
        return AuthenticatedUser(username='staff', auth_source='user', role='installer', tenant_id=1, storefront_id=1)
    app.dependency_overrides[get_current_auth_context] = installer
    try:
        for suffix, body in [('maintenance-workspace', None), ('maintenance-offers', payload),
                             (f"maintenance-offers/{offer['id']}/commands", action(offer, 'issue'))]:
            response = await async_client.post(f'/api/manager/orders/{source_id}/{suffix}', json=body)
            assert response.status_code == 403, response.text
    finally:
        app.dependency_overrides.pop(get_current_auth_context, None)
