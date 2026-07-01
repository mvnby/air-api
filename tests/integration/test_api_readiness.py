import pytest

from core.config import settings


@pytest.mark.asyncio
async def test_api_ready_returns_503_when_public_traffic_disabled(async_client, monkeypatch):
    monkeypatch.setattr(settings, "APP_ROLE", "standby", raising=False)
    monkeypatch.setattr(settings, "API_READY_ENABLED", None, raising=False)

    response = await async_client.get("/api/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["api"] == "not_ready"
    assert payload["traffic"] == "disabled"


@pytest.mark.asyncio
async def test_api_ready_returns_200_when_public_traffic_enabled(async_client, monkeypatch):
    monkeypatch.setattr(settings, "APP_ROLE", "standby", raising=False)
    monkeypatch.setattr(settings, "API_READY_ENABLED", True, raising=False)

    response = await async_client.get("/api/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["api"] == "ready"
    assert payload["traffic"] == "enabled"
    assert payload["database"] == "online"
