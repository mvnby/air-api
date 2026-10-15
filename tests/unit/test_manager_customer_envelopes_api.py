from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from core.database import get_session
from core.security import get_current_manager_tenant_scope
from models.tenancy import TenantScope
from routers import manager_customer_envelopes as envelopes


@pytest.mark.asyncio
async def test_print_route_checks_customer_scope_and_returns_private_pdf(monkeypatch):
    app = FastAPI()
    app.include_router(envelopes.router, prefix='/api/manager')
    scope = TenantScope(tenant_id=17, storefront_id=24, is_system=False)
    session = AsyncMock()

    async def test_session():
        yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_current_manager_tenant_scope] = lambda: scope
    get_customer = AsyncMock(return_value={'id': 8})
    monkeypatch.setattr(envelopes.CustomerService, 'get_for_manager', get_customer)
    party = {'name': 'ООО Клиент', 'address': 'г. Минск, ул. Ленина, д. 1', 'postal_code': '220030'}
    payload = {'sender': party, 'recipient': party}
    url = '/api/manager/customers/8/envelope-pdf'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post(url, json=payload)
        assert response.status_code == 200
        assert response.content.startswith(b'%PDF-')
        assert response.headers['cache-control'] == 'no-store'
        get_customer.assert_awaited_once_with(session, 8, tenant_scope=scope)

        get_customer.return_value = None
        hidden = await client.post(url, json=payload)
        assert hidden.status_code == 404
        get_customer.return_value = {'id': 8}

        too_long = {**party, 'name': 'Ш' * 300, 'address': 'Ш' * 600}
        overflow = await client.post(url, json={**payload, 'recipient': too_long})
        assert overflow.status_code == 400
        assert 'не помещается' in overflow.json()['detail']['message']

        invalid = await client.post(url, json={**payload, 'sender': {**party, 'postal_code': '123'}})
        assert invalid.status_code == 422

        lookup = AsyncMock(return_value=envelopes.PostcodeSearchResponse(items=[]))
        monkeypatch.setattr(envelopes, 'lookup_postcodes', lookup)
        postcode_url = '/api/manager/customers/8/envelope-postcodes'
        search = await client.post(postcode_url, json={'address': 'Минск, Ленина'})
        assert search.status_code == 200
        assert search.json()['items'] == []
        assert search.headers['cache-control'] == 'no-store'
        lookup.assert_awaited_once_with('Минск, Ленина')
        get_customer.return_value = None
        assert (await client.post(postcode_url, json={'address': 'Минск, Ленина'})).status_code == 404
        assert lookup.await_count == 1
        get_customer.return_value = {'id': 8}
        lookup.side_effect = envelopes.PostcodeLookupUnavailable('Введите индекс вручную')
        unavailable = await client.post(postcode_url, json={'address': 'Минск, Ленина'})
        assert unavailable.status_code == 502
        assert 'вручную' in unavailable.json()['detail']['message']
