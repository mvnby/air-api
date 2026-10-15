import httpx
import pytest

from services import belpost_postcode_service as service


@pytest.mark.asyncio
async def test_lookup_uses_fixed_official_endpoint_and_preserves_ambiguous_houses(monkeypatch):
    def handler(request):
        assert str(request.url).startswith('https://api.belpost.by/api/v1/postcodes/autocomplete?')
        assert request.url.params['search'] == 'Минск, улица Ленина'
        return httpx.Response(200, json=[
            {'postcode': '220030', 'short_address': 'Минск, ул. Ленина', 'buildings': '2, 3, 4'},
            {'postcode': '220008', 'short_address': 'Минск, ул. Ленина', 'buildings': '14'},
            {'postcode': '220030', 'short_address': 'Минск, ул. Ленина', 'buildings': '2, 3, 4'},
            {'postcode': 'bad', 'short_address': 'Invalid'},
        ])
    client_type = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, 'AsyncClient', lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))
    result = await service.lookup_postcodes('Минск, улица Ленина')
    assert [row.postal_code for row in result.items] == ['220030', '220008']
    assert result.items[1].buildings == '14'
    assert result.source == 'Белпочта'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['timeout', 'status', 'json', 'shape'])
async def test_provider_failure_returns_actionable_manual_fallback(monkeypatch, kind):
    def handler(request):
        if kind == 'timeout':
            raise httpx.ReadTimeout('timeout', request=request)
        if kind == 'status':
            return httpx.Response(503)
        if kind == 'json':
            return httpx.Response(200, text='not-json')
        return httpx.Response(200, json={'unexpected': []})
    client_type = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, 'AsyncClient', lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(service.PostcodeLookupUnavailable, match='вручную'):
        await service.lookup_postcodes('Минск, Ленина')
