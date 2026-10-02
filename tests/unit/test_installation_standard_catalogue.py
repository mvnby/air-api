"""Published templates and read-only suggestions preserve approved prices and bounds."""
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from core.database import get_session
from core.security import AuthenticatedUser, get_current_auth_context, get_current_manager_tenant_scope, require_manager_access
from models import InstallationPriceBook, Product, ServiceTariff, Storefront, Tenant, TenantCatalogGrant, TenantOffer
from models.tenancy import TenantScope
from routers import manager_installation_estimates, manager_tariffs
from routers.manager_operation_ids import SUGGEST_MANAGER_INSTALLATION_STANDARD_TARIFFS
from routers.manager_permission_policy import TENANT_SERVICE_OPERATION_IDS, required_permission_dependency
from schemas import ManagerTariffServiceKind
from services.installation_grid_seed import canonical_installation_grid
from services.installation_price_book_service import InstallationPriceBookService as Book
from services.installation_standard_catalogue_service import list_standard_tariffs, suggest_standard_tariffs
from services.product_collection_catalog_access import ProductCollectionCatalogAccess
from services.tariffs_service import TariffsService


def _entries():
    return [{"code": row.code, "mode": "fixed", "match": deepcopy(row.match),
             "base_price": str(row.base_price), "short_name": row.label,
             "included_route_m": str(row.included_route_meters), "included_holes": deepcopy(row.included_holes)}
            for row in canonical_installation_grid()]


def _product(product_id, capacity="3.5", indoor_type="wall", **overrides):
    values = dict(id=product_id, title=f"AC {product_id}", slug=f"ac-{product_id}", price=1000,
                  is_published=True, product_kind="complete_split_system",
                  specs={"indoor_type": indoor_type, "capacity_cooling_kw": capacity})
    values.update(overrides)
    return Product(**values)


@pytest.mark.asyncio
async def test_published_standard_templates_rank_wall_small_first_and_preserve_exact_bounds(monkeypatch):
    entries = list(reversed(_entries()))
    next(entry for entry in entries if "wall.small.standard" in entry["code"])["base_price"] = "600.25"
    monkeypatch.setattr(Book, "latest", AsyncMock(return_value=SimpleNamespace(entries=entries, revision=4)))
    result = await list_standard_tariffs(None, TenantScope(tenant_id=1, storefront_id=2))
    assert result.price_book_revision == 4
    assert len(result.items) == 9  # No ready-route, multisplit or strict legacy choices.
    small, middle, large = result.items[:3]
    assert small.title == "Стандартный монтаж настенного кондиционера до 4,2 кВт"
    assert small.price == Decimal("600.25")
    assert (middle.capacity_min_kw, middle.capacity_min_inclusive, middle.capacity_max_kw,
            middle.capacity_max_inclusive) == (Decimal("4.2"), False, Decimal("8"), False)
    assert middle.title.endswith("свыше 4,2 и менее 8 кВт")
    assert large.title.endswith("от 8 до 10,55 кВт")
    assert small.route_m == 3 and small.holes_by_type == {"shared_pass_through": 1}
    for text in ("Трасса до 3 м", "80 см", "Электропитание до 5 м", "Расходные материалы",
                 "дренажный насос", "вышка", "леса", "дополнительная трасса", "линия от щита", "розетка"):
        assert text in small.description


@pytest.mark.asyncio
async def test_batch_suggestions_match_exact_capacity_tiers_and_omit_ambiguous_specs(monkeypatch):
    scope = TenantScope(tenant_id=1, storefront_id=2)
    monkeypatch.setattr(Book, "latest", AsyncMock(return_value=SimpleNamespace(entries=_entries())))
    products = [
        _product(1, "4.2"), _product(2, "4.201"), _product(3, "7.999"),
        _product(4, "8.0"), _product(5, "10.55"), _product(6, "10.551"),
        _product(7, None), _product(8, "3.5 / 5"), _product(9, "3.5", "unsupported"),
        _product(10, specs={"indoor_type": "wall", "type": "кассетный", "capacity_cooling_kw": "3.5"}),
        _product(11, product_kind="indoor_unit"), _product(12, is_published=False),
        _product(13, "8", "console"), _product(14, "12", "cassette"),
        _product(15, specs={"indoor_type": "wall", "capacity_cooling_kw": "invalid"}, power_cooling=3.5),
        _product(16, specs={"indoor_type": "wall"}, power_cooling=3.5),
        _product(17, specs={"__typed_specs": {"indoor_type": {"value": "wall"},
                        "capacity_cooling_kw": {"value": "4.2"}}}),
        _product(18, specs={"indoor_type": "wall", "capacity_cooling_kw": "3.5",
                            "weight_outdoor": "21.123", "pipe_gas": "invalid"}),
    ]
    visible = AsyncMock(return_value={product.id: SimpleNamespace(product=product) for product in products})
    monkeypatch.setattr(ProductCollectionCatalogAccess, "visible_by_ids", visible)
    ids = [product.id for product in products] + [999, 1]
    result = await suggest_standard_tariffs(None, scope, ids)
    visible.assert_awaited_once_with(None, tenant_scope=scope, product_ids=ids)
    assert [item.product_id for item in result.items] == [1, 2, 3, 4, 5, 14, 16, 17, 18]
    assert [item.tariff.price for item in result.items] == [600, 750, 750, 960, 960, 1500, 600, 600, 600]
    # No pipe or weight specs are required for the basic standards.
    assert all(not product.specs.get("pipe_liquid") for product in products)


@pytest.mark.asyncio
async def test_no_book_or_multiple_exact_matches_never_produce_a_guess(monkeypatch):
    scope = TenantScope(tenant_id=1, storefront_id=2)
    visible = AsyncMock(return_value={1: SimpleNamespace(product=_product(1))})
    monkeypatch.setattr(ProductCollectionCatalogAccess, "visible_by_ids", visible)
    monkeypatch.setattr(Book, "latest", AsyncMock(return_value=None))
    assert (await suggest_standard_tariffs(None, scope, [1])).items == []
    visible.assert_not_awaited()
    entries = _entries()
    duplicate = deepcopy(next(entry for entry in entries if "wall.small.standard" in entry["code"]))
    duplicate["code"] = "conflicting-standard"
    monkeypatch.setattr(Book, "latest", AsyncMock(return_value=SimpleNamespace(entries=entries + [duplicate])))
    assert (await suggest_standard_tariffs(None, scope, [1])).items == []


@pytest.mark.asyncio
async def test_quick_add_merges_published_standards_and_active_tenant_services(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'templates.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    try:
        async with sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            scope = TenantScope(tenant_id=1, storefront_id=10, is_system=False, is_canonical_storefront=False)
            entries = _entries()
            next(entry for entry in entries if "wall.small.standard" in entry["code"])["base_price"] = "600.25"
            session.add_all([
                InstallationPriceBook(tenant_id=1, revision=1, fingerprint="a", entries=entries),
                InstallationPriceBook(tenant_id=2, revision=1, fingerprint="b", entries=[]),
                ServiceTariff(id=1, tenant_id=1, selector_label="Старый монтаж", base_price=50),
                ServiceTariff(id=2, tenant_id=1, service_kind="maintenance", selector_label="Чистка", base_price=120),
                ServiceTariff(id=3, tenant_id=1, service_kind="repair", selector_label="Архив", is_active=False),
                ServiceTariff(id=4, tenant_id=2, service_kind="repair", selector_label="Чужая услуга"),
            ])
            await session.commit()
            result = await TariffsService.list_quick_add_tariffs(session, tenant_scope=scope, limit=100)
            assert len(result) == 10
            assert result[0].price == Decimal("600.25") and result[0].tariff_id is None
            assert result[0].installation_standard.code.endswith("wall.small.standard.v20260925")
            assert [item.tariff_id for item in result if item.tariff_id] == [2]
            assert len(await TariffsService.list_quick_add_tariffs(session, tenant_scope=scope, limit=1)) == 1
            result = await TariffsService.list_quick_add_tariffs(session, tenant_scope=scope, q="НАСТЕННОГО", limit=100)
            assert len(result) == 3 and all(item.installation_standard.indoor_type == "wall" for item in result)
            result = await TariffsService.list_quick_add_tariffs(session, tenant_scope=scope,
                service_kind=ManagerTariffServiceKind.maintenance, limit=100)
            assert [item.tariff_id for item in result] == [2]
            result = await TariffsService.list_quick_add_tariffs(session,
                tenant_scope=TenantScope(tenant_id=3, storefront_id=30, is_system=False), limit=100)
            assert result == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_suggestions_use_actual_tenant_offer_and_grant_visibility(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'visibility.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    try:
        async with sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            for tenant_id in (1, 2, 3):
                session.add(Tenant(id=tenant_id, slug=f"tenant-{tenant_id}", display_name="Tenant"))
                session.add(Storefront(id=tenant_id * 10, tenant_id=tenant_id, slug="main", display_name="Storefront"))
            session.add_all([_product(1), _product(2), _product(3)])
            for tenant_id, price in ((1, "600.25"), (2, "777.75")):
                entries = _entries()
                next(entry for entry in entries if "wall.small.standard" in entry["code"])["base_price"] = price
                session.add(InstallationPriceBook(tenant_id=tenant_id, revision=1, fingerprint=str(tenant_id), entries=entries))
                session.add(TenantCatalogGrant(id=tenant_id, tenant_id=tenant_id, storefront_id=tenant_id * 10,
                    status="active", created_by_username="system:test", updated_by_username="system:test"))
                session.add(TenantOffer(tenant_id=tenant_id, storefront_id=tenant_id * 10,
                    product_id=tenant_id, catalog_grant_id=tenant_id, price=1000, status="active", is_published=True,
                    created_by_username="system:test", updated_by_username="system:test"))
            # An active offer without an active catalog grant remains unavailable.
            session.add(TenantOffer(tenant_id=1, storefront_id=10, product_id=3, price=1000, status="active", is_published=True,
                created_by_username="system:test", updated_by_username="system:test"))
            await session.commit()
            for tenant_id, expected_product, expected_price in ((1, 1, "600.25"), (2, 2, "777.75")):
                scope = TenantScope(tenant_id=tenant_id, storefront_id=tenant_id * 10,
                                    is_system=False, is_canonical_storefront=False)
                result = await suggest_standard_tariffs(session, scope, [1, 2, 3])
                assert [item.product_id for item in result.items] == [expected_product]
                assert result.items[0].tariff.price == Decimal(expected_price)
            empty_scope = TenantScope(tenant_id=3, storefront_id=30, is_system=False, is_canonical_storefront=False)
            assert (await suggest_standard_tariffs(session, empty_scope, [1, 2, 3])).items == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_suggestion_api_is_read_only_bounded_and_available_to_tenant_manager(monkeypatch):
    app = FastAPI()
    app.include_router(manager_installation_estimates.router)
    app.include_router(manager_tariffs.router)
    scope = TenantScope(tenant_id=2, storefront_id=20, is_system=False)
    app.dependency_overrides[get_session] = lambda: None
    app.dependency_overrides[get_current_auth_context] = lambda: AuthenticatedUser(
        username="tenant-manager", auth_source="staff_password", staff_user_id=42, role="manager",
        tenant_id=2, storefront_id=20, tenant_membership_id=200, is_system_tenant=False)
    app.dependency_overrides[get_current_manager_tenant_scope] = lambda: scope
    suggestions = AsyncMock(return_value={"items": []})
    quick_add = AsyncMock(return_value=[])
    monkeypatch.setattr(manager_installation_estimates, "suggest_standard_tariffs", suggestions)
    monkeypatch.setattr(TariffsService, "list_quick_add_tariffs", quick_add)
    assert SUGGEST_MANAGER_INSTALLATION_STANDARD_TARIFFS in TENANT_SERVICE_OPERATION_IDS
    assert required_permission_dependency(SUGGEST_MANAGER_INSTALLATION_STANDARD_TARIFFS) is require_manager_access
    route = next(route for route in app.routes if route.path.endswith("/standard-suggestions"))
    assert route.operation_id == SUGGEST_MANAGER_INSTALLATION_STANDARD_TARIFFS
    assert route.methods == {"POST"}
    assert any(dependency.call is require_manager_access for dependency in route.dependant.dependencies)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/manager/installation-estimates/standard-suggestions", json={"product_ids": [1, 2]})
        assert response.status_code == 200 and response.json() == {"items": []}
        suggestions.assert_awaited_once_with(None, scope, [1, 2])
        for invalid_ids in ([0], [-1], [True], ["1"], [1.5], list(range(1, 102))):
            response = await client.post("/api/manager/installation-estimates/standard-suggestions", json={"product_ids": invalid_ids})
            assert response.status_code == 422
        assert suggestions.await_count == 1
        suggestions.return_value = {"items": [{"product_id": 100, "tariff": {
            "code": "wall.small", "title": "Стандартный монтаж", "description": "Расходные материалы",
            "price": Decimal("600.25"), "product_kind": "complete_split_system", "indoor_type": "wall",
            "route_m": Decimal("3"), "holes_by_type": {"shared_pass_through": Decimal("1")},
        }}]}
        ids = list(range(1, 101))
        response = await client.post("/api/manager/installation-estimates/standard-suggestions", json={"product_ids": ids})
        assert response.status_code == 200
        assert response.json()["items"][0]["tariff"]["price"] == "600.25"
        suggestions.assert_awaited_with(None, scope, ids)
        assert (await client.get("/api/manager/tariffs/quick-add?limit=100")).status_code == 200
        assert (await client.get("/api/manager/tariffs/quick-add?limit=101")).status_code == 422
        app.dependency_overrides.pop(get_current_auth_context)
        assert (await client.post("/api/manager/installation-estimates/standard-suggestions", json={"product_ids": [1]})).status_code == 401
        assert suggestions.await_count == 2
