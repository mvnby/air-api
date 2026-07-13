import logging

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from core.request_context import RequestContextLogFilter, RequestContextMiddleware


def _client_for_app(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_request_context_preserves_safe_incoming_id():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/request-id")
    async def read_request_id(request: Request):
        return {"request_id": request.state.request_id}

    async with _client_for_app(app) as client:
        response = await client.get(
            "/request-id",
            headers={"X-Request-ID": "checkout-12345678"},
        )

    assert response.status_code == 200
    assert response.json()["request_id"] == "checkout-12345678"
    assert response.headers["X-Request-ID"] == "checkout-12345678"


async def test_request_context_replaces_unsafe_id_and_logs_it():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    captured: dict[str, str] = {}

    @app.get("/request-id")
    async def read_request_id(request: Request):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "ok", (), None)
        RequestContextLogFilter().filter(record)
        captured["request_id"] = record.request_id
        return {"request_id": request.state.request_id}

    async with _client_for_app(app) as client:
        response = await client.get(
            "/request-id",
            headers={"X-Request-ID": "bad id!"},
        )

    request_id = response.json()["request_id"]
    assert len(request_id) == 32
    assert request_id.isalnum()
    assert response.headers["X-Request-ID"] == request_id
    assert captured["request_id"] == request_id
