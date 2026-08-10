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
    assert payload["scheduler_runtime"]["expected"] is False
    assert payload["scheduler_runtime"]["status"] == "disabled"


@pytest.mark.asyncio
async def test_api_ready_returns_200_when_public_traffic_enabled(async_client, monkeypatch):
    from main import app

    monkeypatch.setattr(settings, "APP_ROLE", "standby", raising=False)
    monkeypatch.setattr(settings, "API_READY_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", True, raising=False)
    scheduler_runtime = {
        "expected": True,
        "status": "retrying",
        "reason": "attempt_failed_retry_scheduled",
        "changed_at": "2026-07-13T08:00:00+00:00",
    }
    monkeypatch.setattr(
        app.state,
        "scheduler_runtime",
        scheduler_runtime,
        raising=False,
    )

    response = await async_client.get("/api/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["api"] == "ready"
    assert payload["traffic"] == "enabled"
    assert payload["database"] == "online"
    assert payload["scheduler_runtime"] == scheduler_runtime


@pytest.mark.asyncio
async def test_standby_fences_api_mutations_before_auth_or_database(
    async_client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "APP_ROLE", "standby", raising=False)
    monkeypatch.setattr(settings, "API_READY_ENABLED", False, raising=False)

    response = await async_client.post(
        "/api/manager/content-ai/brands/short-description/draft",
        json={"brand_name": "TCL", "full_description": "Описание"},
    )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "3"
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"]["code"] == "api_write_fenced"


@pytest.mark.asyncio
async def test_primary_does_not_apply_standby_write_fence(async_client, monkeypatch):
    monkeypatch.setattr(settings, "APP_ROLE", "primary", raising=False)
    monkeypatch.setattr(settings, "API_READY_ENABLED", True, raising=False)

    response = await async_client.post(
        "/api/manager/content-ai/brands/short-description/draft",
        json={"brand_name": "TCL", "full_description": "Описание"},
    )

    assert response.status_code == 401
