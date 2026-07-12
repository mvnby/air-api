from starlette.requests import Request

from core.app_http import global_exception_handler


async def test_global_exception_log_does_not_include_query_or_exception_text(monkeypatch):
    captured: list[tuple[object, ...]] = []

    def _capture(*args, **kwargs):  # noqa: ARG001
        captured.append(args)

    monkeypatch.setattr("core.app_http.logger.error", _capture)
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/orders",
            "raw_path": b"/api/v1/orders",
            "query_string": b"phone=%2B375291112233&code=oauth-secret",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("test", 443),
        }
    )

    await global_exception_handler(request, RuntimeError("customer-secret"))

    rendered = repr(captured)
    assert "/api/v1/orders" in rendered
    assert "+375291112233" not in rendered
    assert "oauth-secret" not in rendered
    assert "customer-secret" not in rendered
