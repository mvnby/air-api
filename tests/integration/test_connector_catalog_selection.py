from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from core.command_actor import CommandActor
from core.config import settings
from models import Brand, Product, ProductSeries, ProductTagLink, Tag, TagGroup, Tenant, TenantCatalogGrant, TenantOffer
from models.supplier import ProductLocalStock, ProductSupplierMapping, Supplier, SupplierOffer
from models.tenancy import Storefront, StorefrontDomain, TenantScope
from schemas_connector_catalog import CatalogProductInput, CatalogSelectionInput
from services.connector_catalog_selection_service import ConnectorCatalogSelectionService as Service


def _actor(tenant_id=1, storefront_id=1, *, canonical=None, system=True):
    return CommandActor(1, "catalog-manager", TenantScope(tenant_id, storefront_id, is_system=system, is_canonical_storefront=canonical))


def _product(index, **values):
    defaults = dict(
        title=f"SELECT model {index}", slug=f"select-model-{index}", price=1000 + index,
        product_kind="complete_split_system", power_cooling=2.6, is_inverter=True,
        specs={"area_m2": 25, "indoor_type": "настенный", "wifi_ready": True, "__filter_min_heat": -25},
    )
    defaults.update(values)
    return Product(**defaults)


async def _brand(db, index, **values):
    brand = Brand(title=f"Brand {index}", slug=f"brand-{index}", **values)
    db.add(brand)
    await db.flush()
    return brand


async def _scope(db, name):
    tenant = Tenant(slug=name, display_name=name)
    db.add(tenant)
    await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug=name, display_name=name, status="active")
    db.add(storefront)
    await db.flush()
    grant = TenantCatalogGrant(
        tenant_id=tenant.id, storefront_id=storefront.id, status="active",
        created_by_username="test", updated_by_username="test",
    )
    db.add(grant)
    await db.flush()
    return tenant, storefront, grant


def _offer(product, scope, **values):
    tenant, storefront, grant = scope
    defaults = dict(
        tenant_id=tenant.id, storefront_id=storefront.id, catalog_grant_id=grant.id,
        product_id=product.id, price=750, is_published=True,
        created_by_username="test", updated_by_username="test",
    )
    defaults.update(values)
    return TenantOffer(**defaults)


@pytest.mark.asyncio
async def test_price_tiers_span_full_catalog_and_are_not_quality_claims(db, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", "https://canonical.test")
    brand = await _brand(db, 1)
    products = [_product(index, price=1000 + index, brand_id=brand.id) for index in range(205)]
    db.add_all(products)
    await db.flush()
    result = await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, query="SELECT"))
    assert result.matching_products == 205
    assert [item.product.product_id for item in result.options] == [products[0].id, products[102].id, products[204].id]
    assert [item.label for item in result.options] == ["Бюджетный", "Средний", "Премиальный"]
    assert [item.product.site_url for item in result.options] == [
        f"https://canonical.test/product/{product.slug}/" for product in (products[0], products[102], products[204])
    ]
    assert any("не подтверждает более высокое качество" in warning for warning in result.warnings)
    assert "их суммы не складываются" in result.message_text


@pytest.mark.asyncio
@pytest.mark.parametrize("prices, expected", [
    ([100, 100, 100, 200, 300], [100, 200, 300]),
    ([100, 100, 100, 300, 300], [100, 300]),
    ([100, 100, 100], [100]),
])
async def test_price_tiers_rank_distinct_prices_and_choose_best_model_per_price(db, prices, expected):
    products = [_product(index, price=price) for index, price in enumerate(prices)]
    db.add_all(products)
    await db.flush()
    # A later equally priced model with sufficient stock must beat the first
    # one. Remaining ties use the stable catalog ranking, including product ID.
    db.add(ProductLocalStock(product_id=products[2].id, qty=2))
    await db.flush()
    result = await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, quantity=2))
    assert result.matching_products == len(prices)
    assert [item.product.unit_price_byn for item in result.options] == expected
    assert result.options[0].product.product_id == products[2].id
    assert len({item.product.unit_price_byn for item in result.options}) == len(result.options)
    if len(expected) < 3:
        assert any(f"различных публичных цен: {len(expected)}" in warning for warning in result.warnings)
    if len(expected) == 1:
        assert result.options[0].label == "Единственный ценовой уровень"
    if len(expected) > 1:
        assert result.options[-1].product.product_id == products[-2 if prices[-2] == prices[-1] else -1].id


@pytest.mark.asyncio
async def test_budget_brands_are_global_canonical_ids_and_quantity_budget_is_exact(db):
    brands = [await _brand(db, index) for index in range(3)]
    first_brand = [_product(index, price=450, brand_id=brands[0].id) for index in range(130)]
    other_brands = [_product(200 + index, price=500, brand_id=brand.id) for index, brand in enumerate(brands[1:])]
    over_budget = _product(300, price=501, brand_id=brands[2].id)
    unbranded = _product(301, price=100)
    db.add_all([*first_brand, *other_brands, over_budget, unbranded])
    await db.flush()
    db.add(ProductLocalStock(product_id=first_brand[-1].id, qty=2))
    await db.flush()
    result = await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, budget_byn=1001, budget_scope="total", quantity=2))
    assert result.matching_products == 133
    assert result.distinct_brands == 3
    assert {option.product.brand for option in result.options} == {brand.title for brand in brands}
    assert len(result.options) == 3
    assert first_brand[-1].id in {option.product.product_id for option in result.options}
    assert all(option.equipment_total_byn <= 1001 and option.quantity == 2 for option in result.options)
    assert over_budget.id not in {option.product.product_id for option in result.options}
    per_unit = await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, budget_byn=501, quantity=2))
    assert per_unit.matching_products == 134


@pytest.mark.asyncio
async def test_all_hard_constraints_apply_and_unknowns_do_not_pass(db):
    brand = await _brand(db, 1)
    other_brand = await _brand(db, 2)
    valid = _product(1, brand_id=brand.id)
    wrongs = [
        _product(2, brand_id=brand.id, power_cooling=5.3),
        _product(3, brand_id=brand.id, is_inverter=False),
        _product(4, brand_id=other_brand.id),
        _product(5, brand_id=brand.id, is_published=False),
        _product(6, brand_id=brand.id, product_kind="indoor_unit"),
        _product(7, brand_id=brand.id, title="Different query", slug="different-query"),
    ]
    for index, overrides in enumerate([
        {"area_m2": 15}, {"__filter_min_heat": -15}, {"wifi_ready": False},
        {"indoor_type": "кассетный"}, {"type": "мульти-сплит-система"},
        {"indoor_units_count": 2}, {"__filter_min_heat": "unknown"}, {"area_m2": None},
        {"wifi_ready": None},
    ], 20):
        specs = dict(valid.specs)
        specs.update(overrides)
        wrongs.append(_product(index, brand_id=brand.id, specs=specs))
    db.add_all([valid, *wrongs])
    await db.flush()
    result = await Service.select(db, _actor(), CatalogSelectionInput(
        cooling_btu_class=9, area_m2=20, is_inverter=True, has_wifi=True,
        heating_min_c=-25, brand_slugs=[brand.slug], query="SELECT",
    ))
    assert result.matching_products == 1
    assert [item.product.product_id for item in result.options] == [valid.id]
    impossible = await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, brand_slugs=["missing-brand"]))
    assert impossible.matching_products == 0
    assert impossible.options == []
    assert "Условия не изменялись" in impossible.message_text


@pytest.mark.asyncio
async def test_area_only_never_selects_oversized_expensive_premium(db):
    products = [_product(index, price=900 + index * 100, power_cooling=2.2, specs={"area_m2": 20, "indoor_type": "настенный"}) for index in range(3)]
    large = _product(10, price=9000, power_cooling=5.3, specs={"area_m2": 60, "indoor_type": "настенный"})
    small = _product(11, price=100, power_cooling=2.2, specs={"area_m2": 15, "indoor_type": "настенный"})
    unknown = _product(12, price=100, specs={"indoor_type": "настенный"})
    db.add_all([*products, large, small, unknown])
    await db.flush()
    result = await Service.select(db, _actor(), CatalogSelectionInput(area_m2=20))
    assert result.matching_products == 3
    assert {item.product.product_id for item in result.options} == {product.id for product in products}


@pytest.mark.asyncio
async def test_quantity_stock_excludes_inactive_mappings_offers_suppliers_and_negative_qty(db):
    active = Supplier(name="Active", code="active")
    inactive = Supplier(name="Inactive", code="inactive", is_active=False)
    db.add_all([active, inactive])
    products = [_product(index) for index in range(7)]
    db.add_all(products)
    await db.flush()
    cases = [
        (active, 1, True, True), (inactive, 100, True, True),
        (active, 100, False, True), (active, 100, True, False),
        (active, 2, True, True), (active, -100, True, True),
    ]
    for product, (supplier, quantity, mapping_active, offer_active) in zip(products, cases):
        external = f"stock-{product.id}"
        db.add(SupplierOffer(supplier_id=supplier.id, external_id=external, qty=quantity, is_active=offer_active, wholesale_value=777.77, wholesale_currency="USD"))
        await db.flush()
        db.add(ProductSupplierMapping(product_id=product.id, supplier_id=supplier.id, external_id=external, is_active=mapping_active))
    db.add_all([
        ProductLocalStock(product_id=products[5].id, qty=2),
        ProductLocalStock(product_id=products[6].id, qty=2),
    ])
    await db.flush()
    stock = await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, quantity=2, in_stock_only=True))
    assert stock.matching_products == 3
    assert {item.product.product_id for item in stock.options} == {product.id for product in products[4:]}
    assert all(item.product.availability == "in_stock" for item in stock.options)
    all_products = [await Service.get_product(db, _actor(), CatalogProductInput(product_id=product.id)) for product in products]
    assert all_products[0].availability == "in_stock"
    assert all(product.availability == "on_request" for product in all_products[1:4])
    assert "wholesale" not in stock.model_dump_json()
    assert "777.77" not in stock.model_dump_json()


@pytest.mark.asyncio
async def test_secondary_price_offer_grant_isolation_and_verified_links(db, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", "https://other-seller.test")
    scope = await _scope(db, "seller-a")
    other = await _scope(db, "seller-b")
    products = [_product(index, price=9000) for index in range(7)]
    products[-1].is_published = False
    db.add_all(products)
    await db.flush()
    db.add_all([
        _offer(products[0], scope),
        _offer(products[1], scope, is_published=False),
        _offer(products[2], scope, status="disabled"),
        _offer(products[3], scope, catalog_grant_id=None),
        _offer(products[4], other),
        _offer(products[6], scope),
        StorefrontDomain(storefront_id=scope[1].id, hostname="seller-a.test", status="active", verified_at=datetime.now(timezone.utc)),
        StorefrontDomain(storefront_id=other[1].id, hostname="seller-b.test", status="active", verified_at=datetime.now(timezone.utc)),
    ])
    await db.flush()
    # is_system is deliberately True: only the canonical storefront resolver
    # may decide whether shared public prices are usable.
    actor = _actor(scope[0].id, scope[1].id, canonical=False)
    result = await Service.select(db, actor, CatalogSelectionInput(cooling_btu_class=9, budget_byn=800))
    assert result.matching_products == 1
    product = result.options[0].product
    assert product.unit_price_byn == 750
    assert product.site_url == f"https://seller-a.test/product/{products[0].slug}/"
    assert "9000" not in result.model_dump_json()
    assert "other-seller" not in result.model_dump_json()
    detail = await Service.get_product(db, actor, CatalogProductInput(product_id=products[0].id))
    assert detail.unit_price_byn == 750
    assert detail.site_url == product.site_url
    for hidden in products[1:]:
        with pytest.raises(HTTPException) as caught:
            await Service.get_product(db, actor, CatalogProductInput(product_id=hidden.id))
        assert caught.value.status_code == 404
    scope[2].status = "disabled"
    db.add(scope[2])
    await db.flush()
    assert (await Service.select(db, actor, CatalogSelectionInput(cooling_btu_class=9))).matching_products == 0


@pytest.mark.asyncio
async def test_unverified_disabled_or_foreign_domains_do_not_create_link(db):
    scope = await _scope(db, "seller-a")
    other = await _scope(db, "seller-b")
    product = _product(1)
    db.add(product)
    await db.flush()
    db.add_all([
        _offer(product, scope),
        StorefrontDomain(storefront_id=scope[1].id, hostname="pending.test", status="active"),
        StorefrontDomain(storefront_id=scope[1].id, hostname="disabled.test", status="disabled", verified_at=datetime.now(timezone.utc)),
        StorefrontDomain(storefront_id=other[1].id, hostname="foreign.test", status="active", verified_at=datetime.now(timezone.utc)),
    ])
    await db.flush()
    actor = _actor(scope[0].id, scope[1].id, canonical=False)
    result = await Service.select(db, actor, CatalogSelectionInput(cooling_btu_class=9))
    assert result.options[0].product.site_url is None
    assert "Ссылка на сайт этой витрины недоступна" in result.message_text
    assert any("подтверждённого домена" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_public_taxonomy_and_wifi_unknown_are_not_fabricated(db):
    hidden_brand = await _brand(db, 1, is_published=False)
    series = ProductSeries(title="Hidden Series", slug="hidden-series", brand_id=hidden_brand.id, is_published=False)
    group = TagGroup(title="Private", slug="private", is_public=False)
    db.add_all([series, group])
    await db.flush()
    tag = Tag(title="secret-match", slug="secret-match", group_id=group.id)
    db.add(tag)
    await db.flush()
    product = _product(1, brand_id=hidden_brand.id, series_id=series.id, specs={"indoor_type": "настенный", "area_m2": 25})
    db.add(product)
    await db.flush()
    db.add(ProductTagLink(product_id=product.id, tag_id=tag.id))
    await db.flush()
    result = await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, budget_byn=2000))
    assert result.distinct_brands == 0
    assert len(result.options) == 1
    public_product = result.options[0].product
    assert public_product.brand is public_product.series is None
    assert public_product.wifi == "unknown"
    assert public_product.heating_min_c is None
    assert (await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, query="secret-match"))).options == []
    assert (await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, has_wifi=False))).options == []
    assert (await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, brand_slugs=[hidden_brand.slug]))).options == []


@pytest.mark.asyncio
async def test_short_catalog_returns_distinct_choices_and_reports_shortfall(db):
    brands = [await _brand(db, index) for index in range(2)]
    products = [_product(index, brand_id=brand.id) for index, brand in enumerate(brands)]
    db.add_all(products)
    await db.flush()
    for budget in (None, 5000):
        result = await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, budget_byn=budget))
        assert len(result.options) == 2
        assert len({item.product.product_id for item in result.options}) == 2
        assert result.distinct_brands == 2
        assert any("доступно вариантов: 2" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_currency_series_brand_and_legacy_wifi_are_not_misrepresented(db):
    brands = [await _brand(db, index) for index in range(2)]
    series = ProductSeries(title="Other brand series", slug="other-brand-series", brand_id=brands[1].id)
    db.add(series)
    await db.flush()
    product = _product(1, brand_id=brands[0].id, series_id=series.id, specs={"area_m2": 25, "indoor_type": "настенный", "__filter_wifi": True})
    db.add(product)
    await db.flush()
    result = await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, has_wifi=True))
    assert result.matching_products == 1
    assert result.options[0].product.series is None
    assert result.options[0].product.wifi == "unknown"
    scope = await _scope(db, "euro-seller")
    scope[1].currency = "EUR"
    db.add(scope[1])
    await db.flush()
    actor = _actor(scope[0].id, scope[1].id, canonical=False)
    with pytest.raises(HTTPException) as caught:
        await Service.select(db, actor, CatalogSelectionInput(cooling_btu_class=9))
    assert caught.value.status_code == 409
    with pytest.raises(HTTPException) as caught:
        await Service.get_product(db, actor, CatalogProductInput(product_id=product.id))
    assert caught.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("values", [{"query": "  "}, {"brand_slugs": ["  "]}])
async def test_blank_search_or_brand_does_not_silently_relax_constraints(db, values):
    with pytest.raises(HTTPException) as caught:
        await Service.select(db, _actor(), CatalogSelectionInput(cooling_btu_class=9, **values))
    assert caught.value.status_code == 422
