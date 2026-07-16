import httpx
import pytest

from bot_app.api_gateway import (
    BotApiAuthenticationError,
    BotApiAuthorizationError,
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
