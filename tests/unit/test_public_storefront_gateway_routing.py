from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from core.storefront_public_routes import (
    INTENTIONALLY_OPEN_PUBLIC_V1_REQUESTS,
    requires_storefront_gateway,
)
from core.storefront_request_gateway import StorefrontRequestGatewayMiddleware
from core.tenant_scope import verify_public_storefront_request
from main import app
from routers.api_products import router as products_router


_INTENTIONALLY_OPEN_V1_ROUTES = {
    ("/api/v1/address-suggest", frozenset({"GET"})),
    ("/api/v1/feeds/yandex-business.yml", frozenset({"GET"})),
    ("/api/v1/proxy/bank", frozenset({"GET"})),
    ("/api/v1/proxy/egr", frozenset({"GET"})),
}


def _group_open_requests_by_route() -> set[tuple[str, frozenset[str]]]:
    paths = {path for _, path in INTENTIONALLY_OPEN_PUBLIC_V1_REQUESTS}
    return {
        (
            path,
            frozenset(
                method
                for method, request_path in INTENTIONALLY_OPEN_PUBLIC_V1_REQUESTS
                if request_path == path
            ),
        )
        for path in paths
    }


def _has_gateway_dependency(route: APIRoute) -> bool:
    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        if dependency.call is verify_public_storefront_request:
            return True
        pending.extend(dependency.dependencies)
    return False


def test_every_app_v1_route_is_gateway_protected_or_exactly_allowlisted():
    routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/")
    ]
    unprotected = {
        (route.path, frozenset(route.methods or ()))
        for route in routes
        if not _has_gateway_dependency(route)
    }
    assert routes
    assert _group_open_requests_by_route() == _INTENTIONALLY_OPEN_V1_ROUTES
    assert unprotected == _INTENTIONALLY_OPEN_V1_ROUTES


def test_intentionally_open_request_allowlist_matches_method_and_path_exactly():
    for method, path in INTENTIONALLY_OPEN_PUBLIC_V1_REQUESTS:
        assert not requires_storefront_gateway(method=method, path=path)
        assert requires_storefront_gateway(method="POST", path=path)
        assert requires_storefront_gateway(method=method, path=f"{path}/")


def test_legacy_authenticated_description_endpoint_does_not_gain_gateway_auth():
    route = next(
        route
        for route in products_router.routes
        if isinstance(route, APIRoute)
        and route.path == "/products/{product_id}/generate-description"
    )

    assert not _has_gateway_dependency(route)


def test_application_installs_signed_gateway_before_route_parsing():
    middleware_classes = [item.cls for item in app.user_middleware]

    assert StorefrontRequestGatewayMiddleware in middleware_classes
    assert middleware_classes.index(StorefrontRequestGatewayMiddleware) < (
        middleware_classes.index(CORSMiddleware)
    )
