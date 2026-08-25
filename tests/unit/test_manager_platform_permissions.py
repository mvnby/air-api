from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from core.database import get_session
from core.security import (
    AuthenticatedUser,
    get_current_auth_context,
    require_system_manager_tenant_scope,
    require_system_owner_access,
)
from models.tenancy import TenantScope
from routers import (
    api_yandex_business,
    manager_backups,
    manager_brands,
    manager_catalog,
    manager_catalog_decision,
    manager_catalog_quality,
    manager_content_ai,
    manager_crm,
    manager_equipment,
    manager_features,
    manager_google_auth,
    manager_leads,
    manager_mdv_catalog,
    manager_media_cleanup,
    manager_media_gallery_read,
    manager_media_gallery_write,
    manager_media_ingest_write,
    manager_media_library,
    manager_media_processing,
    manager_media_worker,
    manager_installation_discounts,
    manager_installation_rates,
    manager_orders,
    manager_product_collections,
    manager_repair_complaints,
    manager_service_estimates,
    manager_settings,
    manager_specs,
    manager_supply,
    manager_supplier_mapping,
    manager_tags,
    manager_tariffs,
    manager_tenant_offers,
    manager_warranties,
    manager_yandex_business,
)
from routers.manager_permission_policy import (
    PLATFORM_MANAGER_OPERATION_IDS,
    STOREFRONT_COLLECTION_OPERATION_IDS,
    SYSTEM_OWNER_OPERATION_IDS,
    require_storefront_collections_manage,
)
from services.settings_service import SettingsService
from services.manager_catalog_service import ManagerCatalogService
from services.equipment_service import EquipmentService
from services.supplier_mapping_service import SupplierCatalogService
from services.tag_service import TagService
from services.tenant_offer_service import TenantOfferService


PLATFORM_ROUTERS = (
    manager_catalog.router,
    manager_catalog_decision.router,
    manager_brands.router,
    manager_tags.router,
    manager_features.router,
    manager_specs.router,
    manager_mdv_catalog.router,
    manager_supply.router,
    manager_supplier_mapping.router,
    manager_media_gallery_write.router,
    manager_media_ingest_write.router,
    manager_media_library.router,
    manager_media_processing.router,
    manager_media_cleanup.router,
    manager_installation_rates.router,
    manager_installation_discounts.router,
    manager_tariffs.router,
    manager_repair_complaints.router,
    manager_catalog_quality.router,
    manager_content_ai.router,
    manager_service_estimates.router,
    manager_warranties.router,
    manager_media_gallery_read.router,
    manager_crm.router,
    manager_yandex_business.router,
    manager_tenant_offers.router,
)

PURE_GLOBAL_MUTATION_ROUTERS = (
    manager_brands.router,
    manager_tags.router,
    manager_features.router,
    manager_specs.router,
    manager_mdv_catalog.router,
    manager_supply.router,
    manager_supplier_mapping.router,
    manager_media_gallery_write.router,
    manager_media_ingest_write.router,
    manager_media_library.router,
    manager_media_processing.router,
    manager_media_cleanup.router,
    manager_installation_rates.router,
    manager_installation_discounts.router,
    manager_tenant_offers.router,
)
FULLY_SYSTEM_SCOPED_ROUTERS = (
    manager_supply.router,
    manager_supplier_mapping.router,
    manager_media_library.router,
    manager_media_processing.router,
    manager_media_cleanup.router,
)
SERVICE_DICTIONARY_MUTATION_OPERATION_IDS = frozenset(
    {
        "create_manager_tariff",
        "update_manager_tariff",
        "delete_manager_tariff",
        "create_manager_tariff_rule",
        "update_manager_tariff_rule",
        "delete_manager_tariff_rule",
        "create_manager_repair_complaint_preset",
        "update_manager_repair_complaint_preset",
        "delete_manager_repair_complaint_preset",
    }
)
SERVICE_DICTIONARY_TENANT_READ_OPERATION_IDS = frozenset(
    {
        "list_manager_tariffs",
        "list_manager_quick_tariffs",
        "list_manager_tariff_rules",
        "list_manager_favorite_tariff_rules",
        "list_manager_repair_complaint_presets",
        "generate_manager_repair_act_ai_draft",
    }
)
ADDITIONAL_PLATFORM_OPERATION_IDS = frozenset(
    {
        "get_manager_catalog_quality_report",
        "create_manager_service_estimate",
        "list_manager_service_estimates",
        "get_manager_service_estimate",
        "get_manager_service_estimate_order_lines",
        "delete_manager_service_estimate",
        "create_manager_warranty_policy",
        "patch_manager_warranty_policy",
        "get_image_variant_candidates",
        "get_manager_crm_health_report",
        "get_manager_yandex_business_quality_report",
    }
)
ADDITIONAL_TENANT_OPERATION_IDS = frozenset(
    {
        "calculate_manager_install_estimate",
        "list_manager_warranty_policies",
        "list_manager_equipment_warranty_coverages",
        "decide_manager_warranty_coverage",
        "reuse_search",
        "get_common_gallery_images",
        "get_manager_yandex_business_price_list",
    }
)
INFRASTRUCTURE_ROUTERS = (
    manager_settings.router,
    manager_backups.router,
    manager_google_auth.router,
)
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _api_routes(*routers):
    return [
        route
        for router in routers
        for route in router.routes
        if isinstance(route, APIRoute)
    ]


def _has_direct_dependency(route: APIRoute, dependency) -> bool:
    return any(item.call is dependency for item in route.dependant.dependencies)


def test_platform_policy_is_attached_to_every_registered_operation():
    routes = _api_routes(*PLATFORM_ROUTERS, *INFRASTRUCTURE_ROUTERS)
    by_operation_id = {route.operation_id: route for route in routes}

    missing_platform = PLATFORM_MANAGER_OPERATION_IDS - by_operation_id.keys()
    missing_infrastructure = SYSTEM_OWNER_OPERATION_IDS - by_operation_id.keys()
    assert not missing_platform
    assert not missing_infrastructure

    for operation_id in PLATFORM_MANAGER_OPERATION_IDS:
        assert _has_direct_dependency(
            by_operation_id[operation_id],
            require_system_manager_tenant_scope,
        ), operation_id
    for operation_id in SYSTEM_OWNER_OPERATION_IDS:
        assert _has_direct_dependency(
            by_operation_id[operation_id],
            require_system_owner_access,
        ), operation_id


def test_all_collection_routes_require_the_scoped_collection_capability():
    routes = _api_routes(manager_product_collections.router)
    by_operation_id = {route.operation_id: route for route in routes}

    assert STOREFRONT_COLLECTION_OPERATION_IDS == by_operation_id.keys()
    assert not (STOREFRONT_COLLECTION_OPERATION_IDS & PLATFORM_MANAGER_OPERATION_IDS)
    for operation_id in STOREFRONT_COLLECTION_OPERATION_IDS:
        assert _has_direct_dependency(
            by_operation_id[operation_id],
            require_storefront_collections_manage,
        ), operation_id
        assert not _has_direct_dependency(
            by_operation_id[operation_id],
            require_system_manager_tenant_scope,
        ), operation_id


def test_every_global_mutation_in_policy_routers_requires_system_manager():
    for route in _api_routes(*PURE_GLOBAL_MUTATION_ROUTERS):
        if route.methods.intersection(UNSAFE_METHODS):
            assert route.operation_id in PLATFORM_MANAGER_OPERATION_IDS, route.operation_id
            assert _has_direct_dependency(route, require_system_manager_tenant_scope)

    for route in _api_routes(manager_catalog.router):
        is_catalog_operation = route.path.startswith("/api/manager/products") or route.path.startswith(
            "/api/manager/catalog"
        )
        if is_catalog_operation and (
            route.methods.intersection(UNSAFE_METHODS)
            or route.path.startswith("/api/manager/catalog/import/jobs")
        ):
            assert route.operation_id in PLATFORM_MANAGER_OPERATION_IDS, route.operation_id
            assert _has_direct_dependency(route, require_system_manager_tenant_scope)


def test_sensitive_supply_and_reusable_media_routers_are_fully_system_scoped():
    for route in _api_routes(*FULLY_SYSTEM_SCOPED_ROUTERS):
        assert route.operation_id in PLATFORM_MANAGER_OPERATION_IDS, route.operation_id
        assert _has_direct_dependency(route, require_system_manager_tenant_scope)


def test_service_dictionary_policy_gates_mutations_but_preserves_tenant_reads():
    routes = _api_routes(
        manager_tariffs.router,
        manager_repair_complaints.router,
    )
    by_operation_id = {route.operation_id: route for route in routes}

    assert SERVICE_DICTIONARY_MUTATION_OPERATION_IDS <= by_operation_id.keys()
    assert SERVICE_DICTIONARY_TENANT_READ_OPERATION_IDS <= by_operation_id.keys()
    for operation_id in SERVICE_DICTIONARY_MUTATION_OPERATION_IDS:
        assert operation_id in PLATFORM_MANAGER_OPERATION_IDS
        assert _has_direct_dependency(
            by_operation_id[operation_id],
            require_system_manager_tenant_scope,
        )
    for operation_id in SERVICE_DICTIONARY_TENANT_READ_OPERATION_IDS:
        assert operation_id not in PLATFORM_MANAGER_OPERATION_IDS
        assert not _has_direct_dependency(
            by_operation_id[operation_id],
            require_system_manager_tenant_scope,
        )


def test_additional_global_surfaces_are_gated_without_widening_exceptions():
    routers = (
        manager_catalog_quality.router,
        manager_service_estimates.router,
        manager_warranties.router,
        manager_media_gallery_read.router,
        manager_crm.router,
        manager_yandex_business.router,
    )
    routes = _api_routes(*routers)
    by_operation_id = {route.operation_id: route for route in routes}

    assert ADDITIONAL_PLATFORM_OPERATION_IDS <= by_operation_id.keys()
    assert ADDITIONAL_TENANT_OPERATION_IDS <= by_operation_id.keys()
    for operation_id in ADDITIONAL_PLATFORM_OPERATION_IDS:
        assert operation_id in PLATFORM_MANAGER_OPERATION_IDS
        assert _has_direct_dependency(
            by_operation_id[operation_id],
            require_system_manager_tenant_scope,
        )
    for operation_id in ADDITIONAL_TENANT_OPERATION_IDS:
        assert operation_id not in PLATFORM_MANAGER_OPERATION_IDS
        assert not _has_direct_dependency(
            by_operation_id[operation_id],
            require_system_manager_tenant_scope,
        )

    for route in _api_routes(api_yandex_business.router):
        assert not _has_direct_dependency(route, require_system_manager_tenant_scope)


def test_tenant_crm_routes_and_media_worker_do_not_gain_platform_gate():
    tenant_routes = _api_routes(
        manager_leads.router,
        manager_orders.router,
        manager_catalog.router,
    )
    tenant_routes = [
        route
        for route in tenant_routes
        if "/customers" in route.path
        or "/leads" in route.path
        or "/orders" in route.path
    ]
    assert tenant_routes
    for route in tenant_routes:
        assert not _has_direct_dependency(route, require_system_manager_tenant_scope)
        assert not _has_direct_dependency(route, require_system_owner_access)

    worker_routes = _api_routes(manager_media_worker.router)
    assert worker_routes
    for route in worker_routes:
        assert route.operation_id not in PLATFORM_MANAGER_OPERATION_IDS
        assert not _has_direct_dependency(route, require_system_manager_tenant_scope)


@pytest.mark.asyncio
async def test_system_scope_dependencies_reject_non_system_tenants():
    with pytest.raises(HTTPException) as manager_error:
        await require_system_manager_tenant_scope(
            TenantScope(tenant_id=2, storefront_id=20, is_system=False)
        )
    assert manager_error.value.status_code == 403

    with pytest.raises(HTTPException) as owner_error:
        await require_system_owner_access(
            AuthenticatedUser(
                username="tenant-owner",
                auth_source="staff_password",
                role="owner",
                tenant_id=2,
                storefront_id=20,
                is_system_tenant=False,
            )
        )
    assert owner_error.value.status_code == 403


def _auth_context(*, role: str, is_system: bool) -> AuthenticatedUser:
    return AuthenticatedUser(
        username=f"{role}-user",
        auth_source="staff_password",
        staff_user_id=42,
        role=role,
        tenant_id=1 if is_system else 2,
        storefront_id=10 if is_system else 20,
        tenant_membership_id=100 if is_system else 200,
        is_system_tenant=is_system,
    )


@pytest.mark.asyncio
async def test_catalog_dictionary_mutation_is_denied_before_service_for_tenant_manager(
    monkeypatch,
):
    app = FastAPI()
    app.include_router(manager_tags.router)
    app.dependency_overrides[get_current_auth_context] = lambda: _auth_context(
        role="manager",
        is_system=False,
    )

    async def _session():
        yield object()

    app.dependency_overrides[get_session] = _session
    create_group = AsyncMock()
    monkeypatch.setattr(TagService, "create_tag_group", create_group)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/manager/tags/groups",
            json={"title": "Restricted"},
        )

    assert response.status_code == 403
    create_group.assert_not_awaited()


@pytest.mark.asyncio
async def test_sensitive_supplier_read_is_denied_before_service_for_tenant_manager(
    monkeypatch,
):
    app = FastAPI()
    app.include_router(manager_supply.router)
    app.dependency_overrides[get_current_auth_context] = lambda: _auth_context(
        role="manager",
        is_system=False,
    )

    async def _session():
        yield object()

    app.dependency_overrides[get_session] = _session
    list_suppliers = AsyncMock()
    monkeypatch.setattr(SupplierCatalogService, "list_suppliers", list_suppliers)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/manager/suppliers")

    assert response.status_code == 403
    list_suppliers.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload", "service_method"),
    [
        (
            "post",
            "/api/manager/tenant-offers",
            {"product_id": 1, "price": 1000},
            "upsert_offer",
        ),
        (
            "patch",
            "/api/manager/tenant-offers/1",
            {"price": 1000},
            "update_offer",
        ),
    ],
)
async def test_tenant_offer_mutation_is_denied_before_service_for_non_system_manager(
    monkeypatch,
    method,
    path,
    payload,
    service_method,
):
    app = FastAPI()
    app.include_router(manager_tenant_offers.router)
    app.dependency_overrides[get_current_auth_context] = lambda: _auth_context(
        role="manager",
        is_system=False,
    )

    async def _session():
        yield object()

    app.dependency_overrides[get_session] = _session
    service = AsyncMock()
    monkeypatch.setattr(TenantOfferService, service_method, service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await getattr(client, method)(path, json=payload)

    assert response.status_code == 403
    service.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "service_method"),
    [
        ("/api/manager/products/list", "list_products"),
        ("/api/manager/products/smart-search?q=Allowed", "smart_search"),
        ("/api/manager/products/1", "get_product"),
    ],
)
async def test_sensitive_legacy_catalog_read_is_denied_before_service_for_tenant_manager(
    monkeypatch,
    path,
    service_method,
):
    app = FastAPI()
    app.include_router(manager_catalog.router)
    app.dependency_overrides[get_current_auth_context] = lambda: _auth_context(
        role="manager",
        is_system=False,
    )

    async def _session():
        yield object()

    app.dependency_overrides[get_session] = _session
    service = AsyncMock()
    monkeypatch.setattr(ManagerCatalogService, service_method, service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(path)

    assert response.status_code == 403
    service.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload", "service_method"),
    [
        (
            "post",
            "/api/manager/equipment",
            {"customer_id": 1, "supplier_id": None},
            "create_equipment",
        ),
        (
            "post",
            "/api/manager/equipment/from-order/1",
            {"supplier_id": 7},
            "create_equipment_from_order",
        ),
        (
            "post",
            "/api/manager/equipment/1/components",
            {"title": "Denied", "supplier_invoice_number": "INV-1"},
            "create_component",
        ),
        (
            "patch",
            "/api/manager/equipment/1/components/2",
            {"supplier_invoice_date": None},
            "update_component",
        ),
    ],
)
async def test_equipment_supplier_fields_are_denied_before_service_for_tenant_manager(
    monkeypatch,
    method,
    path,
    payload,
    service_method,
):
    app = FastAPI()
    app.include_router(manager_equipment.router)
    app.dependency_overrides[get_current_auth_context] = lambda: _auth_context(
        role="manager",
        is_system=False,
    )

    async def _session():
        yield object()

    app.dependency_overrides[get_session] = _session
    service = AsyncMock()
    monkeypatch.setattr(EquipmentService, service_method, service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await getattr(client, method)(path, json=payload)

    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "forbidden"
    service.assert_not_awaited()


def test_tenant_offer_reads_remain_tenant_scoped_without_platform_gate():
    routes = {
        route.operation_id: route
        for route in _api_routes(manager_tenant_offers.router)
    }
    for operation_id in (
        "list_manager_tenant_offers",
        "get_manager_tenant_offer",
        "list_manager_tenant_audit_events",
    ):
        assert operation_id not in PLATFORM_MANAGER_OPERATION_IDS
        assert not _has_direct_dependency(
            routes[operation_id],
            require_system_manager_tenant_scope,
        )


@pytest.mark.asyncio
async def test_system_manager_can_run_registered_catalog_mutation(monkeypatch):
    app = FastAPI()
    app.include_router(manager_tags.router)
    app.dependency_overrides[get_current_auth_context] = lambda: _auth_context(
        role="manager",
        is_system=True,
    )

    async def _session():
        yield object()

    app.dependency_overrides[get_session] = _session
    create_group = AsyncMock(
        return_value={
            "id": 1,
            "title": "Allowed",
            "slug": "allowed",
            "color": "secondary",
            "is_public": True,
            "allow_multiple": False,
            "tags": [],
        }
    )
    monkeypatch.setattr(TagService, "create_tag_group", create_group)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/manager/tags/groups",
            json={"title": "Allowed"},
        )

    assert response.status_code == 200
    create_group.assert_awaited_once()


@pytest.mark.asyncio
async def test_infrastructure_mutation_requires_system_owner(monkeypatch):
    app = FastAPI()
    app.include_router(manager_settings.router)
    current_auth = {"value": _auth_context(role="owner", is_system=False)}
    app.dependency_overrides[get_current_auth_context] = lambda: current_auth["value"]

    async def _session():
        yield object()

    app.dependency_overrides[get_session] = _session
    create_setting = AsyncMock(
        return_value={
            "key": "allowed",
            "value": "yes",
            "description": None,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    monkeypatch.setattr(SettingsService, "create_setting", create_setting)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        denied = await client.post(
            "/api/manager/settings",
            json={"key": "allowed", "value": "yes"},
        )
        current_auth["value"] = _auth_context(role="owner", is_system=True)
        allowed = await client.post(
            "/api/manager/settings",
            json={"key": "allowed", "value": "yes"},
        )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    create_setting.assert_awaited_once()
