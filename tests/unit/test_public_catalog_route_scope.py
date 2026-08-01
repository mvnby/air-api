from fastapi.routing import APIRoute

from api_contracts.public_catalog import PublicProductSearchItemResponse
from core.tenant_scope import get_public_tenant_scope
from main import app


_SCOPED_PUBLIC_CATALOG_PATHS = {
    "/api/products/search",
    "/api/v1/catalog",
    "/api/v1/products",
    "/api/v1/products/vitebsk-featured",
    "/api/v1/products/{identifier}",
    "/api/v1/product-series/navigation",
    "/api/v1/specs/keys",
    "/api/v1/filters/config",
    "/api/v1/content/brands",
    "/api/v1/content/brands/{slug}",
    "/api/v1/content/brands/{brand_slug}/series/{series_slug}",
    "/api/v1/content/placements/{surface_key}/{slot_key}/collections",
    "/api/v1/leads/product-availability",
    "/api/v1/orders",
}


def _has_dependency(route: APIRoute, dependency_call) -> bool:
    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        if dependency.call is dependency_call:
            return True
        pending.extend(dependency.dependencies)
    return False


def test_every_product_bearing_public_surface_resolves_exact_storefront_scope():
    routes = {
        route.path: route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path in _SCOPED_PUBLIC_CATALOG_PATHS
    }

    assert set(routes) == _SCOPED_PUBLIC_CATALOG_PATHS
    assert all(
        _has_dependency(route, get_public_tenant_scope)
        for route in routes.values()
    )


def test_public_search_contract_excludes_internal_commercial_fields():
    internal_fields = {
        "source_url",
        "min_cost_byn",
        "recommended_price_byn",
        "margin_abs_preview",
        "margin_pct_preview",
        "supplier_offer_id",
        "tags",
    }

    assert internal_fields.isdisjoint(PublicProductSearchItemResponse.model_fields)
