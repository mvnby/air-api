import httpx
import pytest

from bot_app.api_gateway import (
    BotApiAuthenticationError,
    BotApiAuthorizationError,
    BotApiConflictError,
    BotApiGateway,
    BotApiGatewayConfig,
    BotApiResponseError,
    BotApiUnavailableError,
)


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        "ftp://api.mvn.by/internal",
        "https://user:password@api.mvn.by/internal",
        "https://api.mvn.by/internal?token=secret",
    ],
)
def test_bot_api_gateway_rejects_unsafe_base_urls(base_url):
    with pytest.raises(ValueError):
        BotApiGatewayConfig(base_url=base_url, token="secret")


async def test_bot_api_gateway_sends_bearer_token_and_decodes_context():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.mvn.by/api/internal/bot/v1/staff/context/123"
        assert request.headers["authorization"] == "Bearer service-secret"
        return httpx.Response(
            200,
            json={
                "telegram_id": 123,
                "is_staff": True,
                "display_name": "Менеджер",
                "primary_role": "manager",
                "roles": ["manager"],
                "legacy_installer_id": None,
                "is_manager": True,
                "is_executor": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(
                base_url="https://api.mvn.by/api/internal/bot/v1/",
                token=" service-secret ",
            ),
            client=client,
        )
        context = await gateway.get_staff_context(123)

    assert context.display_name == "Менеджер"
    assert context.is_manager is True


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, BotApiAuthenticationError),
        (403, BotApiAuthorizationError),
        (422, BotApiResponseError),
        (503, BotApiUnavailableError),
    ],
)
async def test_bot_api_gateway_maps_http_failures(status_code, error_type):
    transport = httpx.MockTransport(lambda _request: httpx.Response(status_code, json={"detail": "failed"}))
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(base_url="https://api.mvn.by/api/internal/bot/v1", token="secret"),
            client=client,
        )
        with pytest.raises(error_type):
            await gateway.health()


async def test_bot_api_gateway_maps_transport_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(base_url="https://api.mvn.by/api/internal/bot/v1", token="secret"),
            client=client,
        )
        with pytest.raises(BotApiUnavailableError, match="temporarily unavailable"):
            await gateway.health()


async def test_bot_api_gateway_rejects_invalid_contract():
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"status": "wrong"}))
    async with httpx.AsyncClient(transport=transport) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(base_url="https://api.mvn.by/api/internal/bot/v1", token="secret"),
            client=client,
        )
        with pytest.raises(BotApiResponseError):
            await gateway.get_staff_context(123)


async def test_bot_api_gateway_posts_catalog_search_without_query_string():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/internal/bot/v1/catalog/search"
        assert request.method == "POST"
        assert request.url.query == b""
        assert request.content == (
            b'{"telegram_id":123,"query":"Midea 12","limit":5}'
        )
        assert request.headers["content-type"] == "application/json"
        assert request.headers["authorization"] == "Bearer service-secret"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": 42,
                        "title": "Midea 12",
                        "slug": "midea-12",
                        "price": 3200,
                        "area": 35,
                        "vitebsk_qty": 1,
                        "availability_status": "in_stock_now",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(
                base_url="https://api.mvn.by/api/internal/bot/v1",
                token="service-secret",
            ),
            client=client,
        )
        response = await gateway.search_catalog(telegram_id=123, query=" Midea 12 ")

    assert response.items[0].id == 42
    assert response.items[0].vitebsk_qty == 1


async def test_bot_api_gateway_decodes_missing_catalog_product():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/internal/bot/v1/catalog/products/404"
        assert request.url.params["telegram_id"] == "123"
        return httpx.Response(200, json={"product": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(base_url="https://api.mvn.by/api/internal/bot/v1", token="secret"),
            client=client,
        )
        response = await gateway.get_catalog_product(telegram_id=123, product_id=404)

    assert response.product is None


async def test_bot_api_gateway_decodes_catalog_product_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/internal/bot/v1/catalog/products/42"
        return httpx.Response(
            200,
            json={
                "product": {
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
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(base_url="https://api.mvn.by/api/internal/bot/v1", token="secret"),
            client=client,
        )
        response = await gateway.get_catalog_product(telegram_id=123, product_id=42)

    assert response.product is not None
    assert response.product.description == "Тихий инвертор"
    assert response.product.categories == ["Настенные"]
    assert response.product.minsk_qty == 2


async def test_bot_api_gateway_posts_task_list_without_staff_id_in_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/internal/bot/v1/tasks/my"
        assert request.method == "POST"
        assert request.url.query == b""
        assert request.content == b'{"telegram_id":123,"limit":10}'
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "kind": "stage",
                        "id": 7,
                        "order_id": 42,
                        "title": "Монтаж",
                        "status": "planned",
                        "start_time": "2026-07-20T12:00:00",
                        "customer_name": "Иван",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(base_url="https://api.mvn.by/api/internal/bot/v1", token="secret"),
            client=client,
        )
        response = await gateway.list_my_tasks(telegram_id=123)

    assert response.items[0].id == 7
    assert response.items[0].start_time.isoformat() == "2026-07-20T12:00:00"


async def test_bot_api_gateway_posts_task_status_mutation():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/internal/bot/v1/tasks/stages/7/status"
        assert request.method == "POST"
        assert request.content == b'{"telegram_id":123,"status":"completed"}'
        return httpx.Response(
            200,
            json={"stage_id": 7, "status": "completed", "changed": True},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(base_url="https://api.mvn.by/api/internal/bot/v1", token="secret"),
            client=client,
        )
        response = await gateway.update_task_status(
            telegram_id=123,
            stage_id=7,
            status="completed",
        )

    assert response.stage_id == 7
    assert response.status == "completed"
    assert response.changed is True


async def test_bot_api_gateway_posts_normalized_task_report():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/internal/bot/v1/tasks/stages/7/report"
        assert request.content.decode() == '{"telegram_id":123,"report":"Готово"}'
        return httpx.Response(200, json={"stage_id": 7, "changed": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(base_url="https://api.mvn.by/api/internal/bot/v1", token="secret"),
            client=client,
        )
        response = await gateway.save_task_report(
            telegram_id=123,
            stage_id=7,
            report="  Готово  ",
        )

    assert response.stage_id == 7
    assert response.changed is False


async def test_bot_api_gateway_maps_task_conflict():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(409, json={"detail": "terminal"}))
    ) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(base_url="https://api.mvn.by/api/internal/bot/v1", token="secret"),
            client=client,
        )
        with pytest.raises(BotApiConflictError):
            await gateway.update_task_status(
                telegram_id=123,
                stage_id=7,
                status="in_progress",
            )


async def test_bot_api_gateway_parses_and_creates_quick_order_with_stable_key():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/quick-orders/parse"):
            assert request.content == '{"telegram_id":123,"text":"ТО Иван"}'.encode()
            return httpx.Response(
                200,
                json={
                    "draft": {
                        "name": "Иван",
                        "phone": "+375291234567",
                        "service_type": "maintenance",
                        "service_label": "Обслуживание",
                        "request_text": "ТО Иван",
                        "parser": "fallback",
                    }
                },
            )
        assert request.url.path.endswith("/quick-orders")
        body = request.content.decode()
        assert '"idempotency_key":"telegram:-100:55"' in body
        assert '"service_label":"Обслуживание"' in body
        return httpx.Response(
            200,
            json={"order_id": 42, "customer_id": 7, "created": True},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(base_url="https://api.mvn.by/api/internal/bot/v1", token="secret"),
            client=client,
        )
        parsed = await gateway.parse_quick_order(telegram_id=123, text="  ТО Иван  ")
        created = await gateway.create_quick_order(
            telegram_id=123,
            idempotency_key="telegram:-100:55",
            draft=parsed.draft,
        )

    assert len(requests) == 2
    assert parsed.draft.service_type == "maintenance"
    assert created.order_id == 42
    assert created.created is True


async def test_bot_api_gateway_sends_requisites_file_as_multipart():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/customers/requisites/recognize-file")
        assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
        assert b'name="telegram_id"' in request.content
        assert b"123" in request.content
        assert b'filename="req.png"' in request.content
        assert b"image-bytes" in request.content
        return httpx.Response(
            200,
            json={
                "id": 12,
                "status": "recognized",
                "source": "telegram",
                "extracted": {"name": "ООО Тест"},
                "validation_flags": {},
                "duplicate_customer": None,
                "created_at": "2026-07-17T12:00:00",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(base_url="https://api.mvn.by/api/internal/bot/v1", token="secret"),
            client=client,
        )
        response = await gateway.recognize_customer_requisites_file(
            telegram_id=123,
            content=b"image-bytes",
            filename="req.png",
            mime_type="image/png",
            telegram_chat_id=-100,
            telegram_message_id=55,
        )

    assert response.id == 12
    assert response.extracted["name"] == "ООО Тест"


async def test_bot_api_gateway_applies_customer_requisites_action():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/customers/requisites/12/action")
        assert request.content == b'{"telegram_id":123,"action":"create"}'
        return httpx.Response(
            200,
            json={
                "recognition": {
                    "id": 12,
                    "status": "confirmed",
                    "source": "telegram_text",
                    "extracted": {"name": "ООО Тест"},
                    "validation_flags": {},
                    "confirmed_customer_id": 7,
                    "confirmed_action": "create",
                    "created_at": "2026-07-17T12:00:00",
                },
                "customer": {"id": 7, "name": "ООО Тест"},
                "changed": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = BotApiGateway(
            BotApiGatewayConfig(base_url="https://api.mvn.by/api/internal/bot/v1", token="secret"),
            client=client,
        )
        response = await gateway.apply_customer_requisites_action(
            telegram_id=123,
            recognition_id=12,
            action="create",
        )

    assert response.customer.id == 7
    assert response.changed is False
