from httpx import ASGITransport, AsyncClient

from core.config import settings
from core.database import get_session
from main import app
from services.bot_access_service import BotAccessContext, BotAccessService
from services.bot_catalog_service import BotCatalogAccessDeniedError, BotCatalogService
from services.bot_task_read_service import BotTaskAccessDeniedError, BotTaskReadService
from services.bot_task_mutation_service import (
    BotTaskMutationAccessDeniedError,
    BotTaskMutationConflictError,
    BotTaskMutationService,
    BotTaskReportMutationResult,
    BotTaskStatusMutationResult,
)
from models import OrderStageStatus


async def _request(
    path: str,
    *,
    token: str | None = None,
    method: str = "GET",
    json: dict | None = None,
):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, headers=headers, json=json)


async def test_internal_bot_api_fails_closed_when_token_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "")

    response = await _request("/api/internal/bot/v1/health", token="anything")

    assert response.status_code == 503
    assert response.json() == {"detail": "Bot API token is not configured"}


async def test_internal_bot_api_rejects_missing_and_invalid_tokens(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    missing = await _request("/api/internal/bot/v1/health")
    invalid = await _request("/api/internal/bot/v1/health", token="wrong-token")

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert invalid.headers["www-authenticate"] == "Bearer"


async def test_internal_bot_api_rejects_request_before_opening_db_session(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")
    session_opened = False

    async def guarded_session():
        nonlocal session_opened
        session_opened = True
        yield object()

    app.dependency_overrides[get_session] = guarded_session
    try:
        response = await _request("/api/internal/bot/v1/staff/context/123", token="wrong-token")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 401
    assert session_opened is False


async def test_internal_bot_api_health_uses_dedicated_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    response = await _request("/api/internal/bot/v1/health", token="expected-token")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api_version": "v1"}


def test_internal_bot_api_openapi_contract_is_versioned_and_secured():
    schema = app.openapi()

    health = schema["paths"]["/api/internal/bot/v1/health"]["get"]
    staff_context = schema["paths"]["/api/internal/bot/v1/staff/context/{telegram_id}"]["get"]
    catalog_search = schema["paths"]["/api/internal/bot/v1/catalog/search"]["post"]
    catalog_product = schema["paths"]["/api/internal/bot/v1/catalog/products/{product_id}"]["get"]
    task_list = schema["paths"]["/api/internal/bot/v1/tasks/my"]["post"]
    task_status = schema["paths"]["/api/internal/bot/v1/tasks/stages/{stage_id}/status"]["post"]
    task_report = schema["paths"]["/api/internal/bot/v1/tasks/stages/{stage_id}/report"]["post"]

    assert health["operationId"] == "get_internal_bot_api_health_v1"
    assert staff_context["operationId"] == "get_internal_bot_staff_context_v1"
    assert catalog_search["operationId"] == "search_internal_bot_catalog_v1"
    assert catalog_product["operationId"] == "get_internal_bot_catalog_product_v1"
    assert task_list["operationId"] == "list_internal_bot_my_tasks_v1"
    assert task_status["operationId"] == "update_internal_bot_task_status_v1"
    assert task_report["operationId"] == "save_internal_bot_task_report_v1"
    assert health["security"] == [{"BotServiceBearer": []}]
    assert staff_context["security"] == [{"BotServiceBearer": []}]
    assert catalog_search["security"] == [{"BotServiceBearer": []}]
    assert catalog_product["security"] == [{"BotServiceBearer": []}]
    assert task_list["security"] == [{"BotServiceBearer": []}]
    assert task_status["security"] == [{"BotServiceBearer": []}]
    assert task_report["security"] == [{"BotServiceBearer": []}]
    assert schema["components"]["securitySchemes"]["BotServiceBearer"] == {
        "type": "http",
        "description": "Dedicated bearer token used only by the MVN Telegram bot service.",
        "scheme": "bearer",
    }


async def test_internal_bot_staff_context_maps_backend_permissions(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    async def fake_get_context(_session, telegram_id):
        assert telegram_id == 123456
        return BotAccessContext(
            telegram_id=telegram_id,
            is_staff=True,
            display_name="Монтажник",
            primary_role="installer",
            roles=["installer", "repair"],
            legacy_installer_id=42,
        )

    async def fake_session():
        yield object()

    monkeypatch.setattr(BotAccessService, "get_context", fake_get_context)
    app.dependency_overrides[get_session] = fake_session
    try:
        response = await _request(
            "/api/internal/bot/v1/staff/context/123456",
            token="expected-token",
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json() == {
        "telegram_id": 123456,
        "is_staff": True,
        "display_name": "Монтажник",
        "primary_role": "installer",
        "roles": ["installer", "repair"],
        "legacy_installer_id": 42,
        "is_manager": False,
        "is_executor": True,
    }


async def test_internal_bot_catalog_search_returns_stable_product_projection(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    async def fake_search(_session, *, telegram_id, query, limit):
        assert (telegram_id, query, limit) == (123456, "Midea 12", 5)
        return [
            {
                "id": 42,
                "title": "Midea 12",
                "slug": "midea-12",
                "price": 3200,
                "area": 35,
                "main_image": "/media/midea.webp",
                "vitebsk_qty": 1,
                "availability_status": "in_stock_now",
                "specs": {"private_backend_detail": "not part of bot contract"},
            }
        ]

    async def fake_session():
        yield object()

    monkeypatch.setattr(BotCatalogService, "search_for_staff", fake_search)
    app.dependency_overrides[get_session] = fake_session
    try:
        response = await _request(
            "/api/internal/bot/v1/catalog/search",
            token="expected-token",
            method="POST",
            json={"telegram_id": 123456, "query": "Midea 12", "limit": 5},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": 42,
                "title": "Midea 12",
                "slug": "midea-12",
                "description": "",
                "price": 3200,
                "area": 35,
                "main_image": "/media/midea.webp",
                "categories": [],
                "vitebsk_qty": 1,
                "minsk_qty": 0,
                "availability_status": "in_stock_now",
            }
        ]
    }


async def test_internal_bot_catalog_product_can_report_missing_item(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    async def fake_get(_session, *, telegram_id, product_id):
        assert (telegram_id, product_id) == (123456, 404)
        return None

    async def fake_session():
        yield object()

    monkeypatch.setattr(BotCatalogService, "get_product_for_staff", fake_get)
    app.dependency_overrides[get_session] = fake_session
    try:
        response = await _request(
            "/api/internal/bot/v1/catalog/products/404?telegram_id=123456",
            token="expected-token",
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json() == {"product": None}


async def test_internal_bot_catalog_product_returns_card_detail(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    async def fake_get(_session, *, telegram_id, product_id):
        assert (telegram_id, product_id) == (123456, 42)
        return {
            "id": 42,
            "title": "Midea 12",
            "slug": "midea-12",
            "description": "Тихий инвертор",
            "price": 3200,
            "area": 35,
            "main_image": "/media/midea.webp",
            "categories": ["Настенные"],
            "vitebsk_qty": 0,
            "minsk_qty": 2,
            "availability_status": "available_2_3_days",
        }

    async def fake_session():
        yield object()

    monkeypatch.setattr(BotCatalogService, "get_product_for_staff", fake_get)
    app.dependency_overrides[get_session] = fake_session
    try:
        response = await _request(
            "/api/internal/bot/v1/catalog/products/42?telegram_id=123456",
            token="expected-token",
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json()["product"] == {
        "id": 42,
        "title": "Midea 12",
        "slug": "midea-12",
        "description": "Тихий инвертор",
        "price": 3200,
        "area": 35,
        "main_image": "/media/midea.webp",
        "categories": ["Настенные"],
        "vitebsk_qty": 0,
        "minsk_qty": 2,
        "availability_status": "available_2_3_days",
    }


async def test_internal_bot_catalog_denies_non_staff_identity(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    async def fake_search(_session, **_kwargs):
        raise BotCatalogAccessDeniedError("Staff catalog access is required")

    async def fake_session():
        yield object()

    monkeypatch.setattr(BotCatalogService, "search_for_staff", fake_search)
    app.dependency_overrides[get_session] = fake_session
    try:
        response = await _request(
            "/api/internal/bot/v1/catalog/search",
            token="expected-token",
            method="POST",
            json={"telegram_id": 123456, "query": "Midea"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 403
    assert response.json() == {"detail": "Staff catalog access is required"}


async def test_internal_bot_task_list_returns_stable_projection(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    async def fake_list(_session, *, telegram_id, limit):
        assert (telegram_id, limit) == (123456, 10)
        return [
            {
                "kind": "stage",
                "id": 7,
                "order_id": 42,
                "title": "Монтаж",
                "status": "planned",
                "start_time": "2026-07-20T12:00:00",
                "address": "Победы 15",
                "customer_name": "Иван",
                "customer_phone": "+375291234567",
                "comment": "Позвонить заранее",
                "private_field": "must not leak",
            }
        ]

    async def fake_session():
        yield object()

    monkeypatch.setattr(BotTaskReadService, "list_for_staff", fake_list)
    app.dependency_overrides[get_session] = fake_session
    try:
        response = await _request(
            "/api/internal/bot/v1/tasks/my",
            token="expected-token",
            method="POST",
            json={"telegram_id": 123456, "limit": 10},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "kind": "stage",
                "id": 7,
                "order_id": 42,
                "title": "Монтаж",
                "status": "planned",
                "start_time": "2026-07-20T12:00:00",
                "address": "Победы 15",
                "customer_name": "Иван",
                "customer_phone": "+375291234567",
                "comment": "Позвонить заранее",
            }
        ]
    }


async def test_internal_bot_task_list_denies_non_staff_identity(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    async def fake_list(_session, **_kwargs):
        raise BotTaskAccessDeniedError("Staff task access is required")

    async def fake_session():
        yield object()

    monkeypatch.setattr(BotTaskReadService, "list_for_staff", fake_list)
    app.dependency_overrides[get_session] = fake_session
    try:
        response = await _request(
            "/api/internal/bot/v1/tasks/my",
            token="expected-token",
            method="POST",
            json={"telegram_id": 123456},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 403
    assert response.json() == {"detail": "Staff task access is required"}


async def test_internal_bot_task_list_validates_body(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    response = await _request(
        "/api/internal/bot/v1/tasks/my",
        token="expected-token",
        method="POST",
        json={"telegram_id": 0, "limit": 21},
    )

    assert response.status_code == 422


async def test_internal_bot_task_status_mutation_uses_authorized_service(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    async def fake_update(_session, **kwargs):
        assert kwargs == {
            "telegram_id": 123456,
            "stage_id": 7,
            "status": OrderStageStatus.COMPLETED,
        }
        return BotTaskStatusMutationResult(
            stage_id=7,
            status=OrderStageStatus.COMPLETED,
            changed=True,
        )

    async def fake_session():
        yield object()

    monkeypatch.setattr(BotTaskMutationService, "update_stage_status", fake_update)
    app.dependency_overrides[get_session] = fake_session
    try:
        response = await _request(
            "/api/internal/bot/v1/tasks/stages/7/status",
            token="expected-token",
            method="POST",
            json={"telegram_id": 123456, "status": "completed"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json() == {
        "stage_id": 7,
        "status": "completed",
        "changed": True,
    }


async def test_internal_bot_task_status_maps_access_and_conflict(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    async def fake_session():
        yield object()

    app.dependency_overrides[get_session] = fake_session
    try:
        async def deny(*_args, **_kwargs):
            raise BotTaskMutationAccessDeniedError("denied")

        monkeypatch.setattr(BotTaskMutationService, "update_stage_status", deny)
        denied = await _request(
            "/api/internal/bot/v1/tasks/stages/7/status",
            token="expected-token",
            method="POST",
            json={"telegram_id": 123456, "status": "completed"},
        )

        async def conflict(*_args, **_kwargs):
            raise BotTaskMutationConflictError("terminal")

        monkeypatch.setattr(BotTaskMutationService, "update_stage_status", conflict)
        conflicted = await _request(
            "/api/internal/bot/v1/tasks/stages/7/status",
            token="expected-token",
            method="POST",
            json={"telegram_id": 123456, "status": "in_progress"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert denied.status_code == 403
    assert conflicted.status_code == 409


async def test_internal_bot_task_report_normalizes_and_saves(monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "expected-token")

    async def fake_save(_session, **kwargs):
        assert kwargs == {
            "telegram_id": 123456,
            "stage_id": 7,
            "report": "Работа выполнена",
        }
        return BotTaskReportMutationResult(stage_id=7, changed=False)

    async def fake_session():
        yield object()

    monkeypatch.setattr(BotTaskMutationService, "save_stage_report", fake_save)
    app.dependency_overrides[get_session] = fake_session
    try:
        response = await _request(
            "/api/internal/bot/v1/tasks/stages/7/report",
            token="expected-token",
            method="POST",
            json={"telegram_id": 123456, "report": "  Работа выполнена  "},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json() == {"stage_id": 7, "changed": False}
