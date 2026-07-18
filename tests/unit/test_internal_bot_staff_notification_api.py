from datetime import datetime, timezone
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from core.config import settings
from core.database import get_session
from main import app
from services.bot_staff_notification_api_service import (
    BotStaffNotificationApiService,
    BotStaffNotificationLeaseConflictError,
)


async def _request(path: str, *, token: str | None = None, json: dict | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.post(path, headers=headers, json=json)


async def test_staff_notification_claim_rejects_token_before_database(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")
    session_opened = False

    async def guarded_session():
        nonlocal session_opened
        session_opened = True
        yield object()

    app.dependency_overrides[get_session] = guarded_session
    try:
        response = await _request(
            "/api/internal/bot/v1/staff-notifications/claim",
            token="wrong-token",
            json={"worker_id": "bot-1"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 401
    assert session_opened is False


async def test_staff_notification_claim_returns_typed_delivery(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")
    expires_at = datetime(2026, 7, 20, 8, 1, tzinfo=timezone.utc)
    claim = AsyncMock(
        return_value={
            "delivery_id": "a" * 32,
            "event_id": "b" * 32,
            "telegram_id": 123456,
            "payload": {
                "event_kind": "assigned",
                "staff_user_id": 20,
                "stage_id": 50,
                "order_id": 40,
                "stage_name": "Монтаж",
                "status": "planned",
                "timezone": "Europe/Minsk",
                "manager_url": "https://api.mvn.by/manager/orders/kanban?orderId=40",
                "change_fields": ["assignee"],
            },
            "attempt": 1,
            "max_attempts": 8,
            "lease_token": "x" * 43,
            "lease_expires_at": expires_at,
        }
    )
    monkeypatch.setattr(BotStaffNotificationApiService, "claim", claim)

    session = object()

    async def fake_session():
        yield session

    app.dependency_overrides[get_session] = fake_session
    try:
        response = await _request(
            "/api/internal/bot/v1/staff-notifications/claim",
            token="expected-token",
            json={"worker_id": "bot-1", "visibility_timeout_seconds": 90},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json()["notification"]["payload"]["event_kind"] == "assigned"
    claim.assert_awaited_once_with(
        session,
        worker_id="bot-1",
        visibility_timeout_seconds=90,
    )


async def test_staff_notification_ack_maps_lease_conflict(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")
    ack = AsyncMock(side_effect=BotStaffNotificationLeaseConflictError("lease lost"))
    monkeypatch.setattr(BotStaffNotificationApiService, "ack", ack)

    async def fake_session():
        yield object()

    app.dependency_overrides[get_session] = fake_session
    try:
        response = await _request(
            f"/api/internal/bot/v1/staff-notifications/{'a' * 32}/ack",
            token="expected-token",
            json={
                "worker_id": "bot-1",
                "lease_token": "x" * 43,
                "telegram_message_id": 777,
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 409
    assert response.json() == {"detail": "lease lost"}


def test_staff_notification_openapi_contract_is_versioned_and_secured():
    paths = app.openapi()["paths"]
    expected = {
        "/api/internal/bot/v1/staff-notifications/claim": (
            "claim_internal_bot_staff_notification_v1"
        ),
        "/api/internal/bot/v1/staff-notifications/{delivery_id}/renew": (
            "renew_internal_bot_staff_notification_v1"
        ),
        "/api/internal/bot/v1/staff-notifications/{delivery_id}/ack": (
            "ack_internal_bot_staff_notification_v1"
        ),
        "/api/internal/bot/v1/staff-notifications/{delivery_id}/nack": (
            "nack_internal_bot_staff_notification_v1"
        ),
    }
    for path, operation_id in expected.items():
        operation = paths[path]["post"]
        assert operation["operationId"] == operation_id
        assert operation["security"] == [{"BotServiceBearer": []}]
