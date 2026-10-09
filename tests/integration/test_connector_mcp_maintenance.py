"""Real OAuth/MCP/PostgreSQL maintenance adapters, never a client photo-pilot claim."""
import asyncio
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

import aiohttp
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select
from starlette.applications import Starlette
from starlette.routing import Route

from core.config import settings
from core.security import AuthenticatedUser
from models import (CommandAuditEvent, Customer, CustomerEquipment, DocumentLegalEntity, EquipmentServiceHistory,
    MaintenanceObservation, MaintenanceObservationPhoto, MaintenanceOffer, MaintenanceOfferEvent, MaintenanceResolution,
    Order, OrderProposal, OrderServiceLink, OrderStatus, PublicWriteIdempotency, ServiceAttachment, StaffUser,
    Storefront, Tenant, TenantMembership)
from models.connector_auth import ConnectorGrant
from models.tenancy import TenantScope
from schemas_connector_maintenance import FindingCreateInput
from services.connector_auth_policy import CLIENT_ID, pkce, resource
from services.connector_auth_service import ConnectorAuthService
from services.connector_file_service import ConnectorFileService
from services.connector_maintenance_service import ConnectorMaintenanceService
from services.connector_mcp import ConnectorMCPApplication
from tests.integration.test_maintenance_observations_api import context, image_bytes, payload


@pytest.fixture
async def maintenance_db(db_engine):
    # Real committed setup and independent physical connections are essential
    # for concurrency and lost-commit-ack evidence. The ordinary db fixture
    # deliberately shares a savepoint connection and cannot prove those cases.
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        yield session


async def grant(db, *, scopes='kitlane:read kitlane:maintenance:write', tenant_id=1, storefront_id=1):
    user = StaffUser(display_name='Maintenance connector', username=f'connector-{tenant_id}', primary_role='admin', roles=['admin'])
    db.add(user); await db.flush()
    membership = TenantMembership(tenant_id=tenant_id, staff_user_id=user.id, role='admin')
    db.add(membership); await db.commit()
    auth = AuthenticatedUser(username=user.username, auth_source='staff', staff_user_id=user.id,
        role='admin', tenant_id=tenant_id, storefront_id=storefront_id, tenant_membership_id=membership.id,
        is_system_tenant=tenant_id == 1, auth_version=user.auth_version)
    verifier = 'f' * 64; redirect = 'https://chatgpt.com/connector_platform_oauth_redirect'
    pending, nonce = await ConnectorAuthService.start_consent(db, auth, 'maintenance-session', client_id=CLIENT_ID,
        redirect_uri=redirect, requested_resource=resource(), scope=scopes, state='maintenance',
        code_challenge=pkce(verifier), code_challenge_method='S256', response_type='code')
    callback = await ConnectorAuthService.finish_consent(db, auth, 'maintenance-session', consent_id=pending.id, nonce=nonce, allow=True)
    token = await ConnectorAuthService.exchange_code(db, code=parse_qs(urlsplit(callback).query)['code'][0], client_id=CLIENT_ID,
        redirect_uri=redirect, requested_resource=resource(), code_verifier=verifier)
    return token, user, membership, auth


@asynccontextmanager
async def client_for(db, token):
    @asynccontextmanager
    async def sessions():
        async with AsyncSession(bind=db.bind, expire_on_commit=False) as session:
            yield session
    adapter = ConnectorMCPApplication(session_factory=sessions)
    app = Starlette(routes=[Route('/api/connector/mcp', adapter, methods=['GET', 'POST', 'DELETE'])])
    async with adapter.lifespan():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='https://api.mvn.by', headers={
            'Authorization': f'Bearer {token.access_token}', 'Accept': 'application/json, text/event-stream'}) as client:
            yield client


async def call(client, name, arguments):
    response = await client.post('/api/connector/mcp', json={'jsonrpc': '2.0', 'id': 1,
        'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}})
    assert response.status_code == 200, response.text
    return response.json()['result']


def finding_args(order_id, **changes):
    content = payload(**changes); content.pop('command_key')
    return dict(order_id=order_id, idempotency_key='maintenance-finding-create-0001', payload=content)


def success(response):
    assert not response['isError'], response
    return response['structuredContent']


@pytest.mark.asyncio
async def test_maintenance_flow_real_saved_prices_drafts_and_no_executed_repair(maintenance_db, tmp_path, monkeypatch):
    db = maintenance_db
    monkeypatch.setattr(settings, 'SERVICE_ATTACHMENT_LOCAL_DIR', str(tmp_path))
    source, equipment, old_event = await context(db, OrderStatus.CLOSED)
    source_before, event_before = source.model_dump(), old_event.model_dump()
    issuer = DocumentLegalEntity(tenant_id=1, slug='connector-issuer', display_name='Test issuer', legal_name='ООО Сервис', unp='100000001')
    db.add(issuer); await db.commit()
    token, user, _, _ = await grant(db)
    async with client_for(db, token) as client:
        register = success(await call(client, 'list_equipment', {'customer_id': source.customer_id}))
        assert [item['id'] for item in register['items']] == [equipment.id]
        success(await call(client, 'get_equipment', {'equipment_id': equipment.id}))
        history = success(await call(client, 'list_equipment_history', {'equipment_id': equipment.id}))
        assert history['items'][0]['id'] == old_event.id
        args = finding_args(source.id, equipment_id=equipment.id)
        finding = success(await call(client, 'create_maintenance_finding', args))['result']
        assert finding['created_by'] == user.username and finding['origin'] == 'chatgpt_maintenance'
        assert finding['manager_url'].endswith(f'orderId={source.id}')
        replay = success(await call(client, 'create_maintenance_finding', args))
        assert replay['replayed'] and replay['result'] == finding
        changed = await call(client, 'create_maintenance_finding', {**args, 'payload': {**args['payload'], 'facts': 'Changed'}})
        assert changed['structuredContent']['error']['status'] == 409
        details = success(await call(client, 'get_maintenance_finding', {'observation_id': finding['id']}))
        assert details['revisions'][0]['version'] == 1
        edits = dict(observation_id=finding['id'], idempotency_key='maintenance-finding-update-0001', payload={
            **{key: finding[key] for key in ('equipment_id', 'equipment_description', 'facts', 'recommendation')},
            'expected_version': 1, 'facts': 'Уточнено после осмотра'})
        updated = success(await call(client, 'update_maintenance_finding', edits))['result']
        assert updated['version'] == 2 and updated['original_comment'] == finding['original_comment']
        assert success(await call(client, 'update_maintenance_finding', edits))['replayed']
        stale = await call(client, 'update_maintenance_finding', {**edits, 'idempotency_key': 'maintenance-finding-update-stale'})
        assert stale['structuredContent']['error']['status'] == 409
        act_args = dict(order_id=source.id, idempotency_key='maintenance-act-prepare-0001', payload={
            'observations': [{'observation_id': finding['id'], 'expected_version': 2}],
            'legal_entity_id': issuer.id, 'issue_date': '2026-10-09'})
        act = success(await call(client, 'prepare_maintenance_defect_act', act_args))['result']
        assert act['status'] == 'draft'
        assert success(await call(client, 'prepare_maintenance_defect_act', act_args))['replayed']
        acts = success(await call(client, 'list_maintenance_defect_acts', {'order_id': source.id}))
        assert acts['items'][0]['document_id'] == act['document_id']
        continuation = await db.get(Order, act['continuation_order_id'])
        assert continuation.status == OrderStatus.NEGOTIATION and continuation.installation_date is None
        empty = success(await call(client, 'list_maintenance_offers', {'order_id': source.id}))
        assert empty['available_proposals'] == []
        proposal = OrderProposal(order_id=continuation.id, name='Saved prices')
        db.add(proposal); await db.flush()
        line = OrderServiceLink(order_id=continuation.id, proposal_id=proposal.id, title='Ремонт изоляции', quantity=2, price='120.25', cost='90.11')
        db.add(line); await db.commit()
        available = success(await call(client, 'list_maintenance_offers', {'order_id': source.id}))['available_proposals'][0]
        assert available['proposal_id'] == proposal.id
        assert str(available['lines'][0]['data']['price']) == '120.25'
        assert 'cost' not in available['lines'][0]['data']
        offer_args = dict(order_id=source.id, idempotency_key='maintenance-offer-prepare-0001', payload={
            'proposal_id': proposal.id, 'lines': [{'kind': 'service', 'line_id': line.id, 'observation_id': finding['id'], 'expected_version': 2, 'purpose': 'repair'}]})
        offer = success(await call(client, 'prepare_maintenance_offer', offer_args))['result']
        assert offer['state'] == 'draft' and offer['version'] == 0
        assert success(await call(client, 'prepare_maintenance_offer', offer_args))['replayed']
        listed = success(await call(client, 'list_maintenance_findings', {'order_id': source.id}))
        assert listed['items'][0]['version'] == 2
    await db.refresh(source); await db.refresh(old_event); await db.refresh(continuation)
    assert source.model_dump() == source_before and old_event.model_dump() == event_before
    assert continuation.status == OrderStatus.NEGOTIATION
    assert await db.scalar(select(func.count()).select_from(MaintenanceOffer)) == 1
    assert await db.scalar(select(func.count()).select_from(MaintenanceOfferEvent)) == 0
    assert await db.scalar(select(func.count()).select_from(MaintenanceResolution)) == 0
    assert await db.scalar(select(func.count()).select_from(EquipmentServiceHistory)) == 1
    audits = (await db.execute(select(CommandAuditEvent).where(CommandAuditEvent.channel == 'chatgpt'))).scalars().all()
    assert {a.operation for a in audits} == {'maintenance.finding.create', 'maintenance.finding.update', 'maintenance.act.prepare', 'maintenance.offer.prepare'}
    assert all(a.staff_user_id == user.id for a in audits) and len(audits) == 4


@pytest.mark.asyncio
async def test_live_scope_role_revoke_and_foreign_ids_before_write_or_receipt(maintenance_db):
    db = maintenance_db
    source, equipment, _ = await context(db)
    tenant = Tenant(slug='foreign-connector', display_name='Foreign tenant')
    db.add(tenant); await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug='foreign', display_name='Foreign storefront', status='active', is_default=True)
    foreign_customer = Customer(tenant_id=tenant.id, name='Foreign customer', phone='+375291234567')
    db.add_all([storefront, foreign_customer]); await db.flush()
    foreign_equipment = CustomerEquipment(customer_id=foreign_customer.id)
    foreign_order = Order(tenant_id=tenant.id, storefront_id=storefront.id, customer_id=foreign_customer.id, workflow_type='maintenance')
    sibling = Storefront(tenant_id=1, slug='connector-sibling', display_name='Sibling', status='active')
    db.add_all([foreign_equipment, foreign_order, sibling]); await db.flush()
    sibling_order = Order(tenant_id=1, storefront_id=sibling.id, customer_id=source.customer_id, workflow_type='maintenance')
    db.add(sibling_order); await db.commit()
    token, _, membership, auth = await grant(db)
    async with client_for(db, token) as client:
        for name, arguments in [('get_equipment', {'equipment_id': foreign_equipment.id}),
                ('list_equipment_history', {'equipment_id': foreign_equipment.id}),
                ('list_equipment', {'customer_id': foreign_customer.id}),
                ('create_maintenance_finding', finding_args(foreign_order.id)),
                ('list_maintenance_findings', {'order_id': sibling_order.id}),
                ('list_maintenance_offers', {'order_id': foreign_order.id})]:
            denied = await call(client, name, arguments)
            assert denied['structuredContent']['error']['status'] == 404, denied
        created = success(await call(client, 'create_maintenance_finding', finding_args(source.id)))['result']
        # A previously committed receipt does not expose a source whose current scope moved.
        source.storefront_id = sibling.id; db.add(source); await db.commit()
        denied_replay = await call(client, 'create_maintenance_finding', finding_args(source.id))
        assert denied_replay['structuredContent']['error']['status'] == 404
        source.storefront_id = 1; db.add(source); await db.commit()
        grants = (await db.execute(select(ConnectorGrant).where(ConnectorGrant.staff_user_id == auth.staff_user_id))).scalars().all()
        current = grants[-1]; current.scopes = ['kitlane:read']; db.add(current); await db.commit()
        denied_scope = await call(client, 'create_maintenance_finding', finding_args(source.id))
        assert denied_scope['structuredContent']['error']['code'] == 'insufficient_scope'
        success(await call(client, 'get_maintenance_finding', {'observation_id': created['id']}))
        membership.role = 'manager'; db.add(membership); await db.commit()
        downgraded = await client.post('/api/connector/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        assert downgraded.status_code == 401
        membership.role = 'admin'; db.add(membership); await db.commit()
        await ConnectorAuthService.revoke_token(db, token=token.access_token, client_id=CLIENT_ID)
        revoked = await client.post('/api/connector/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        assert revoked.status_code == 401
    assert await db.scalar(select(func.count()).select_from(MaintenanceObservation)) == 1


@pytest.mark.asyncio
async def test_concurrent_repeat_commit_ack_loss_and_atomic_failed_receipt(maintenance_db, monkeypatch):
    db = maintenance_db
    source, _, _ = await context(db)
    token, user, _, _ = await grant(db)
    args = finding_args(source.id)
    async with client_for(db, token) as client:
        results = await asyncio.gather(call(client, 'create_maintenance_finding', args), call(client, 'create_maintenance_finding', args))
        values = [success(row) for row in results]
        assert len({row['result']['id'] for row in values}) == 1
        assert sorted(row['replayed'] for row in values) == [False, True]
    class AckLost(AsyncSession):
        async def commit(self):
            await super().commit()
            if self.info.pop('lose_ack', False):
                raise ConnectionError('test commit acknowledgement lost')
    timeout_args = FindingCreateInput.model_validate({**args, 'idempotency_key': 'maintenance-create-timeout-0001'})
    async with AckLost(bind=db.bind, expire_on_commit=False) as session:
        actor = await ConnectorAuthService.resolve_actor(session, token.access_token, 'kitlane:maintenance:write')
        session.info['lose_ack'] = True
        with pytest.raises(ConnectionError, match='acknowledgement'):
            await ConnectorMaintenanceService.write(session, actor, 'create_maintenance_finding', timeout_args)
    async with AsyncSession(bind=db.bind, expire_on_commit=False) as session:
        actor = await ConnectorAuthService.resolve_actor(session, token.access_token, 'kitlane:maintenance:write')
        retried = await ConnectorMaintenanceService.write(session, actor, 'create_maintenance_finding', timeout_args)
        assert retried.replayed
    from services.public_write_idempotency_service import PublicWriteIdempotencyService
    def reject_receipt(*args):
        raise ValueError('test failed receipt')
    with monkeypatch.context() as scoped:
        scoped.setattr(PublicWriteIdempotencyService, '_complete_receipt', reject_receipt)
        async with AsyncSession(bind=db.bind, expire_on_commit=False) as session:
            actor = await ConnectorAuthService.resolve_actor(session, token.access_token, 'kitlane:maintenance:write')
            bad = FindingCreateInput.model_validate({**args, 'idempotency_key': 'maintenance-receipt-failure-0001'})
            with pytest.raises(ValueError, match='failed receipt'):
                await ConnectorMaintenanceService.write(session, actor, 'create_maintenance_finding', bad)
    assert await db.scalar(select(func.count()).select_from(MaintenanceObservation)) == 2
    assert await db.scalar(select(func.count()).select_from(CommandAuditEvent).where(CommandAuditEvent.staff_user_id == user.id)) == 2


@pytest.mark.asyncio
async def test_photo_private_ownership_refreshed_credentials_and_no_url_receipt(maintenance_db, tmp_path, monkeypatch):
    db = maintenance_db
    monkeypatch.setattr(settings, 'SERVICE_ATTACHMENT_LOCAL_DIR', str(tmp_path))
    monkeypatch.setattr(settings, 'CONNECTOR_CHATGPT_FILE_HOSTS', ['delivery.example'])
    source, _, _ = await context(db)
    token, _, _, _ = await grant(db)
    downloads = []
    async def download(file):
        downloads.append(file.file_id)
        return image_bytes(), 'inspection.png', 'image/png'
    monkeypatch.setattr('services.connector_maintenance_service.ConnectorFileService.download', download)
    async with client_for(db, token) as client:
        finding = success(await call(client, 'create_maintenance_finding', finding_args(source.id)))['result']
        other = success(await call(client, 'create_maintenance_finding', {
            **finding_args(source.id), 'idempotency_key': 'maintenance-other-finding-0001'}))['result']
        photo_args = dict(observation_id=finding['id'], idempotency_key='maintenance-photo-upload-0001', file={
            'file_id': 'file-inspection', 'download_url': 'https://delivery.example/photo?signature=private-first',
            'file_name': 'inspection.png', 'mime_type': 'image/png'})
        photo = success(await call(client, 'upload_maintenance_finding_photo', photo_args))['result']
        assert photo['source'] == 'chatgpt_maintenance'
        refreshed = {**photo_args, 'file': {**photo_args['file'], 'download_url': 'https://delivery.example/photo?signature=private-refreshed'}}
        replay = success(await call(client, 'upload_maintenance_finding_photo', refreshed))
        assert replay['replayed'] and replay['result']['id'] == photo['id'] and downloads == ['file-inspection']
        changed = await call(client, 'upload_maintenance_finding_photo', {**refreshed, 'file': {**refreshed['file'], 'file_id': 'file-other'}})
        assert changed['structuredContent']['error']['status'] == 409
        forged_source = await call(client, 'upload_maintenance_finding_photo', {**refreshed, 'file': {**refreshed['file'], 'download_url': 'http://127.0.0.1/private'}})
        assert forged_source['structuredContent']['error']['code'] == 'invalid_file'
        read = await call(client, 'get_maintenance_finding_photo', {'observation_id': finding['id'], 'attachment_id': photo['id']})
        assert not read['isError'] and any(row['type'] == 'image' for row in read['content'])
        assert 'url' not in read['structuredContent'] and read['structuredContent']['variant'] == 'preview'
        denied = await call(client, 'get_maintenance_finding_photo', {'observation_id': other['id'], 'attachment_id': photo['id']})
        assert denied['structuredContent']['error']['status'] == 404
    from models import PublicWriteIdempotency
    receipts = (await db.execute(select(PublicWriteIdempotency))).scalars().all()
    assert all('private-first' not in str(row.response_body) and 'private-refreshed' not in str(row.response_body) for row in receipts)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [429, 503, 'connection'])
async def test_photo_transient_delivery_failure_then_same_key_retry_commits_once(maintenance_db, tmp_path, monkeypatch, caplog, failure):
    db = maintenance_db
    caplog.set_level('INFO')
    monkeypatch.setattr(settings, 'SERVICE_ATTACHMENT_LOCAL_DIR', str(tmp_path))
    monkeypatch.setattr(settings, 'CONNECTOR_CHATGPT_FILE_HOSTS', ['delivery.example'])
    source, _, _ = await context(db)
    token, _, _, _ = await grant(db)
    requests = []
    body = image_bytes()
    async def addresses(host):
        return ['8.8.8.8']
    monkeypatch.setattr(ConnectorFileService, 'public_addresses', addresses)
    class Content:
        async def iter_chunked(self, size):
            yield body
    class Response:
        content = Content()
        content_length = len(body)
        headers = {'Content-Type': 'image/png'}
    class Client:
        def __init__(self, **kwargs):
            self.connector = kwargs['connector']
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            await self.connector.close()
        @asynccontextmanager
        async def get(self, url, **kwargs):
            requests.append(url)
            if len(requests) == 1 and failure == 'connection':
                raise aiohttp.ClientConnectionError(url)
            response = Response()
            response.status = failure if len(requests) == 1 else 200
            yield response
    monkeypatch.setattr('services.connector_file_service.aiohttp.ClientSession', Client)
    receipt_query = select(PublicWriteIdempotency).where(
        PublicWriteIdempotency.command_name == 'authenticated:maintenance.photo.upload')
    audit_query = select(func.count()).select_from(CommandAuditEvent).where(
        CommandAuditEvent.operation == 'maintenance.photo.upload')
    async with client_for(db, token) as client:
        finding = success(await call(client, 'create_maintenance_finding', finding_args(source.id)))['result']
        photo_args = dict(observation_id=finding['id'], idempotency_key='maintenance-photo-transient-0001', file={
            'file_id': 'file-inspection', 'download_url': 'https://delivery.example/photo?signature=private-retry',
            'file_name': 'inspection.png', 'mime_type': 'image/png'})
        failed = await call(client, 'upload_maintenance_finding_photo', photo_args)
        assert failed['isError'] and failed['structuredContent']['error']['code'] == 'retryable'
        assert failed['structuredContent']['error']['status'] == 503
        assert 'private-retry' not in str(failed) and 'delivery.example' not in str(failed)
        assert await db.scalar(select(func.count()).select_from(MaintenanceObservationPhoto)) == 0
        assert await db.scalar(select(func.count()).select_from(ServiceAttachment)) == 0
        assert not (await db.execute(receipt_query)).scalars().all()
        assert await db.scalar(audit_query) == 0
        saved = success(await call(client, 'upload_maintenance_finding_photo', photo_args))
        assert not saved['replayed']
        replay = success(await call(client, 'upload_maintenance_finding_photo', photo_args))
        assert replay['replayed'] and replay['result']['id'] == saved['result']['id']
    assert len(requests) == 2
    assert await db.scalar(select(func.count()).select_from(MaintenanceObservationPhoto)) == 1
    assert await db.scalar(select(func.count()).select_from(ServiceAttachment)) == 1
    assert await db.scalar(audit_query) == 1
    receipts = (await db.execute(receipt_query)).scalars().all()
    assert len(receipts) == 1 and receipts[0].completed_at is not None
    assert 'private-retry' not in str(receipts[0].response_body) and 'private-retry' not in caplog.text


@pytest.mark.asyncio
async def test_large_proposal_read_is_bounded_and_cannot_look_complete(maintenance_db):
    from services.maintenance_offer_service import MaintenanceOfferService
    db = maintenance_db
    source, _, _ = await context(db)
    workspace = await MaintenanceOfferService.workspace(db, source_order_id=source.id, scope=TenantScope(1, 1), actor='test-manager')
    proposal = OrderProposal(order_id=workspace['continuation_order_id'], name='Large composition')
    db.add(proposal); await db.flush()
    db.add_all([OrderServiceLink(order_id=workspace['continuation_order_id'], proposal_id=proposal.id,
        title=f'Line {number}', quantity=1, price='10.25') for number in range(101)])
    await db.commit()
    token, _, _, _ = await grant(db)
    async with client_for(db, token) as client:
        result = success(await call(client, 'list_maintenance_offers', {'order_id': source.id}))
        assert result['available_proposals'][0]['lines_complete'] is False
        assert result['available_proposals'][0]['lines'] == []
