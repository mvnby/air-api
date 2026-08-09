import inspect

from routers.manager_content_ai import _rate_limit_http_error, router
from services.manager_content_ai_limiter import ManagerContentAIRateLimitError


def test_content_ai_routes_are_post_only_non_mutating_drafts_without_database_dependency():
    draft_routes = [route for route in router.routes if getattr(route, "path", "").endswith("/draft")]

    assert {route.path for route in draft_routes} == {
        "/api/manager/content-ai/features/draft",
        "/api/manager/content-ai/series/draft",
    }
    assert all(route.methods == {"POST"} for route in draft_routes)
    assert all("session" not in inspect.signature(route.endpoint).parameters for route in draft_routes)
    assert all("entity_id" not in inspect.signature(route.endpoint).parameters for route in draft_routes)


def test_content_ai_rate_limit_maps_to_429_with_retry_after():
    error = _rate_limit_http_error(ManagerContentAIRateLimitError(retry_after=7))

    assert error.status_code == 429
    assert error.headers == {"Retry-After": "7"}
    assert error.detail["code"] == "content_ai_rate_limited"
