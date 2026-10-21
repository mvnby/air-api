"""Regressions found in independent acceptance of catalog selection PR #1188."""

import pytest
from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import select

from models import Brand, Order, Product, ProductCollection
from models.tenancy import TenantScope
from services.catalog_decision_collection_service import CatalogDecisionCollectionService
from services.catalog_decision_order_service import CatalogDecisionOrderService
from services.catalog_decision_projection import CatalogDecisionFilters, CatalogDecisionQueryService
from services.catalog_decision_quick_order_service import CatalogDecisionQuickOrderService
from services.importer_service import ImporterService
from services.product_write_service import ProductWriteService


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


async def _list(session, ids, **kwargs):
    return await CatalogDecisionQueryService.list_products(
        session, tenant_scope=SCOPE,
        filters=CatalogDecisionFilters(product_ids=tuple(ids), **kwargs),
        page=1, limit=100, sort="recommended", direction="asc",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["includes_indoor_unit", "includes_outdoor_unit"])
@pytest.mark.parametrize("updated", [False, None])
async def test_reimport_preserves_kind_but_explicit_missing_component_vetoes_selection(db, monkeypatch, flag, updated):
    flags = {"includes_indoor_unit": True, "includes_outdoor_unit": True}

    class Parser:
        def supports(self, url):
            return True

        async def parse(self, url):
            return {
                "title": "Reimport complete system", "slug": "reimport-complete",
                "description": "", "price": 2000,
                "specs": {"type": "полупромышленный кондиционер", "indoor_type": "канальный",
                          "capacity_cooling_kw": "10", "indoor_units_count": 1, **flags},
            }

    monkeypatch.setattr("services.importer_service.async_session_maker", lambda: _SessionContext(db))
    importer = ImporterService()
    importer.parsers = [Parser()]
    url = "https://example.test/reimport-complete"
    product = (await importer.import_product(url))["product"]
    assert product.product_kind == "complete_split_system"
    if updated is None:
        flags.pop(flag)
    else:
        flags[flag] = updated
    product = (await importer.import_product(url, update_existing=True))["product"]
    assert product.product_kind == "complete_split_system"  # keep the manual decision
    expected = {product.id} if updated is None else set()
    assert await CatalogDecisionQueryService.eligible_system_product_ids(db, [product.id]) == expected
    result = await _list(db, [product.id])
    assert {row["id"] for row in result["items"]} == expected
    assert result["meta"]["total"] == len(expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["includes_indoor_unit", "includes_outdoor_unit"])
@pytest.mark.parametrize("layout,value", [
    ("flat", False), ("flat", 0), ("flat", " FALSE "), ("flat", "нет"),
    ("value", False), ("raw", "не входит"), ("conflict", False),
])
async def test_component_denials_apply_to_rows_counts_facets_and_selected_ids(db, flag, layout, value):
    brand = Brand(title="Denied components", slug="denied-components")
    db.add(brand)
    await db.flush()
    specs = {"type": "полупромышленный кондиционер", "indoor_units_count": 1}
    if layout == "flat":
        specs[flag] = value
    else:
        specs["__typed_specs"] = {flag: {"value" if layout == "conflict" else layout: value}}
        if layout == "conflict":
            specs[flag] = True
    denied = Product(title="Denied manual complete", slug="denied-complete", price=1000,
                     brand_id=brand.id, product_kind="complete_split_system", specs=specs)
    missing = Product(title="Manual complete without component details", slug="missing-details",
                      price=1000, product_kind="complete_split_system", specs={})
    manual_other = Product(title="Manual other despite evidence", slug="manual-other", price=1000,
                           product_kind="other", specs={"includes_indoor_unit": True, "includes_outdoor_unit": True})
    db.add_all([denied, missing, manual_other])
    await db.commit()
    ids = [denied.id, missing.id, manual_other.id]
    result = await _list(db, ids)
    assert [row["id"] for row in result["items"]] == [missing.id]
    assert result["meta"]["total"] == 1
    assert await CatalogDecisionQueryService.eligible_system_product_ids(db, ids) == {missing.id}
    assert set(await CatalogDecisionQueryService.get_product_snapshots(db, tenant_scope=SCOPE, product_ids=ids)) == {missing.id}
    options = await CatalogDecisionQueryService.list_filter_options(db, tenant_scope=SCOPE)
    assert brand.id not in {item["id"] for item in options["brands"]}
    assert denied.product_kind == "complete_split_system" and manual_other.product_kind == "other"


@pytest.mark.asyncio
async def test_typed_multi_count_cannot_override_single_system_scope(db):
    product = Product(title="Typed multi", slug="typed-multi", price=1000, product_kind="complete_split_system",
                      specs={"__typed_specs": {"indoor_units_count": {"value": 2}}})
    db.add(product)
    await db.commit()
    assert await CatalogDecisionQueryService.eligible_system_product_ids(db, [product.id]) == set()


@pytest.mark.asyncio
async def test_contradiction_is_rejected_before_collection_and_order_writes(db):
    product = Product(title="Stale basket complete", slug="stale-basket-complete", price=2000,
                      product_kind="complete_split_system", specs={"includes_outdoor_unit": False})
    db.add(product)
    await db.commit()
    product_id = product.id
    with pytest.raises(HTTPException) as error:
        await CatalogDecisionCollectionService.create(
            db, title="Stale basket", product_ids=[product_id], tenant_scope=SCOPE,
            actor_username="test-admin", actor_staff_user_id=None,
        )
    assert error.value.status_code == 400
    with pytest.raises(ValueError, match="Товары не найдены"):
        await CatalogDecisionOrderService._load_snapshots(db, tenant_scope=SCOPE, product_ids=[product_id])
    with pytest.raises(ValueError, match="Товары не найдены"):
        await CatalogDecisionQuickOrderService.create(
            db, product_ids=[product_id], idempotency_key="stale-basket", prospect_type="individual", tenant_scope=SCOPE,
        )
    assert (await db.execute(select(func.count()).select_from(Order))).scalar_one() == 0
    assert (await db.execute(select(func.count()).select_from(ProductCollection))).scalar_one() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["0", "-1", 0, -1, True, "NaN", "Infinity", "-Infinity", None])
async def test_invalid_capacity_preserves_valid_core_for_filter_display_and_sort(db, invalid):
    created = await ProductWriteService.create_product(db, {
        "title": "Legacy capacity", "price": 2000, "power_cooling": 7,
        "specs": {"type": "сплит-система", "capacity_cooling_kw": invalid,
                  "power_cons_cooling_kw": "2", "capacity_cooling_min_kw": "3", "capacity_cooling_max_kw": "12"},
    })
    product = await db.get(Product, created["id"])
    assert product.power_cooling == 7
    result = await _list(db, [product.id], cooling_btu_classes=(24,))
    assert [row["id"] for row in result["items"]] == [product.id]
    assert result["items"][0]["cooling_power_kw"] == 7
    peers = [Product(title=f"Peer {kw}", slug=f"peer-{kw}", price=1000, power_cooling=kw,
                     product_kind="complete_split_system") for kw in (6, 8)]
    db.add_all(peers)
    await db.commit()
    ids = (product.id, *(peer.id for peer in peers))
    for direction, expected in (("asc", [6, 7, 8]), ("desc", [8, 7, 6])):
        sorted_result = await CatalogDecisionQueryService.list_products(
            db, tenant_scope=SCOPE, filters=CatalogDecisionFilters(product_ids=ids),
            page=1, limit=100, sort="cooling_power", direction=direction,
        )
        assert [row["cooling_power_kw"] for row in sorted_result["items"]] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_fallback", [None, 0, -1, float("nan"), float("inf"), float("-inf")])
async def test_invalid_core_and_non_nominal_specs_never_produce_a_nominal(db, invalid_fallback):
    product = Product(title="No valid nominal", slug="no-valid-nominal", price=1000,
                      power_cooling=invalid_fallback, product_kind="complete_split_system",
                      specs={"capacity_cooling_kw": "-1", "power_cons_cooling_kw": "7",
                             "capacity_cooling_min_kw": "3", "capacity_cooling_max_kw": "9"})
    db.add(product)
    await db.commit()
    result = await _list(db, [product.id])
    assert result["items"][0]["cooling_power_kw"] is None
    assert (await _list(db, [product.id], cooling_btu_classes=(24,)))["meta"]["total"] == 0
    valid = Product(title="Valid nominal", slug="valid-nominal", price=1000,
                    power_cooling=7, product_kind="complete_split_system")
    db.add(valid)
    await db.commit()
    for direction in ("asc", "desc"):
        sorted_result = await CatalogDecisionQueryService.list_products(
            db, tenant_scope=SCOPE, filters=CatalogDecisionFilters(product_ids=(product.id, valid.id)),
            page=1, limit=100, sort="cooling_power", direction=direction,
        )
        assert [row["cooling_power_kw"] for row in sorted_result["items"]] == [7, None]


@pytest.mark.asyncio
@pytest.mark.parametrize("kw", [100, 125])
async def test_explicit_large_kw_search_uses_nominal_without_watt_conversion(db, kw):
    correct = Product(title="Large nominal", slug="large-nominal", price=1000,
                      power_cooling=kw, product_kind="complete_split_system")
    trap = Product(title=f"{kw} kW title only", slug="watt-trap", price=1000,
                   power_cooling=kw / 1000, product_kind="complete_split_system")
    db.add_all([correct, trap])
    await db.commit()
    result = await _list(db, [correct.id, trap.id], search=f"{kw} кВт")
    assert [row["id"] for row in result["items"]] == [correct.id]
    assert result["items"][0]["cooling_power_kw"] == kw


@pytest.mark.asyncio
async def test_overflowing_legacy_numeric_capacity_falls_back_without_failing_the_page(db):
    product = Product(title="Overflow capacity", slug="overflow-capacity", price=1000,
                      power_cooling=7, product_kind="complete_split_system",
                      specs={"capacity_cooling_kw": "9" * 400})
    db.add(product)
    await db.commit()
    result = await _list(db, [product.id], cooling_btu_classes=(24,))
    assert [row["cooling_power_kw"] for row in result["items"]] == [7]
