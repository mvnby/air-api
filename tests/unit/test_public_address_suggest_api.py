from httpx import ASGITransport, AsyncClient
import httpx
import pytest

from main import app
from services.address_suggest_service import AddressSuggestService


@pytest.mark.asyncio
async def test_public_address_suggest_returns_normalized_items(monkeypatch):
    async def fake_suggest(query: str):
        assert query == "Минск"
        return [
            {
                "title": "Минск",
                "subtitle": "Беларусь",
                "value": "Минск, Беларусь",
            }
        ]

    monkeypatch.setattr(AddressSuggestService, "suggest", fake_suggest)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/address-suggest", params={"q": "Минск"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["value"] == "Минск, Беларусь"


@pytest.mark.asyncio
async def test_public_address_suggest_returns_502_on_provider_error(monkeypatch):
    async def fake_suggest(_query: str):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(AddressSuggestService, "suggest", fake_suggest)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/address-suggest", params={"q": "Минск"})

    assert response.status_code == 200
    assert response.json() == {"items": []}


@pytest.mark.asyncio
async def test_public_address_suggest_returns_empty_list_when_not_configured(monkeypatch):
    async def fake_suggest(_query: str):
        raise RuntimeError("YANDEX_API_KEY not configured")

    monkeypatch.setattr(AddressSuggestService, "suggest", fake_suggest)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/address-suggest", params={"q": "Минск"})

    assert response.status_code == 200
    assert response.json() == {"items": []}
