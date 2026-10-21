from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from services.catalog_decision_data_repair import RepairBlocked, digest, validate_reviewed_plan
from services.catalog_decision_source_repair import SCOPE_IDS, build_plan, commerce_projection, load_manifest, product_projection, validate_manifest
from tests.catalog_decision_source_repair_support import pin_fixture, prepared_catalog

NOW = datetime(2026, 10, 21, 19, tzinfo=timezone.utc)


@pytest.fixture
def catalog(monkeypatch):
    values = prepared_catalog()
    pin_fixture(monkeypatch, values[0])
    return values


def test_real_manifest_covers_original_scope_and_preserves_old_power_repairs():
    manifest = load_manifest()
    candidates = [r for r in manifest["products"] if r["fields_set"]]
    assert len(manifest["products"]) == len(SCOPE_IDS) == 217
    assert len(candidates) == 149
    assert all(r["fields_set"] == {"product_kind": "complete_split_system"} for r in candidates)
    assert not {94, 95, 96, 97, 98, 99, 180, 196, *range(1297, 1310)} & SCOPE_IDS
    blocked = {r["identity"]["id"] for r in manifest["products"] if not r["fields_set"]}
    assert {191, 188, 189, 1080, 1082, 1084, 504, 505, 507, 525, 531, 924, 949, 951, 164} <= blocked
    assert 162 not in blocked
    assert all(not r["nominal_review"]["conflicts"] for r in candidates)


def test_public_manifest_contains_no_raw_financial_or_supplier_records():
    forbidden = {"price", "old_price", "wholesale_value", "wholesale_raw", "rrc_byn", "rrc_raw",
                 "qty", "qty_raw", "supplier_mappings", "local_stocks"}

    def check(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            assert not str(value.get("source_url", "")).startswith("https://docs.google.com/spreadsheets/")
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    manifest = load_manifest()
    check(manifest)
    assert all({"retail_sha256", "commerce_sha256"} <= row["before"].keys() for row in manifest["products"])


def test_only_reviewed_kind_targets_and_fresh_manual_review_then_noop(catalog):
    manifest, products, commerce = catalog
    original = deepcopy(products)
    plan = build_plan(manifest, products, commerce, now=NOW)
    assert plan["changed"] == 149 and len(plan["blocked_items"]) == 68
    assert len(plan["observed"]) == 217 and plan["manual_review_required"]
    with pytest.raises(RepairBlocked, match="Manual kind provenance"):
        validate_reviewed_plan(plan, plan, plan["plan_digest"], now=NOW)
    validate_reviewed_plan(plan, plan, plan["plan_digest"], manual_kind_review_digest=plan["plan_digest"], now=NOW)
    with pytest.raises(RepairBlocked, match="expired"):
        validate_reviewed_plan(plan, plan, plan["plan_digest"], manual_kind_review_digest=plan["plan_digest"], now=NOW + timedelta(minutes=30))
    by_id = {p.id: p for p in products}
    for op in plan["operations"]:
        by_id[op["id"]].product_kind = op["fields_set"]["product_kind"]
    noop = build_plan(manifest, products, commerce, now=NOW)
    assert noop["changed"] == 0 and not noop["manual_review_required"]
    assert noop["product_ids"] == noop["brand_slugs"] == noop["series_paths"] == []
    for before, after in zip(original, products):
        assert {k: v for k, v in vars(before).items() if k != "product_kind"} == {k: v for k, v in vars(after).items() if k != "product_kind"}


@pytest.mark.parametrize("fault", ["scope", "power_target", "blocked_target", "source", "proof", "identity", "before"])
def test_unreviewed_manifest_is_rejected(fault):
    manifest = deepcopy(load_manifest())
    row = next(r for r in manifest["products"] if r["fields_set"])
    if fault == "scope":
        manifest["products"].pop()
    elif fault == "power_target":
        row["fields_set"]["power_cooling"] = 7
    elif fault == "blocked_target":
        next(r for r in manifest["products"] if r["identity"]["id"] == 191)["fields_set"] = {"product_kind": "complete_split_system"}
    elif fault == "source":
        row["evidence"][0]["source_sha256"] = "0" * 64
    elif fault == "proof":
        row["proof"]["outdoor_count"] = 0
    elif fault == "identity":
        row["identity"]["title"] += " other"
    else:
        row["before"]["retail_sha256"] = "0" * 64
    with pytest.raises(RepairBlocked, match="Unreviewed"):
        validate_manifest(manifest)


@pytest.mark.parametrize("fault", ["missing", "extra", "identity", "source_url", "kind", "power", "specs", "tags", "price", "publication", "commerce", "partial"])
def test_product_and_commerce_drift_fails_closed(catalog, fault):
    manifest, products, commerce = catalog
    p = next(p for p in products if p.id == 162)
    if fault == "missing":
        products.pop()
    elif fault == "extra":
        products.append(NS(id=999999))
    elif fault == "identity":
        p.title += " other"
    elif fault == "source_url":
        p.source_url = "https://example.invalid/different-source"
    elif fault == "kind":
        p.product_kind = "indoor_unit"
    elif fault == "power":
        p.power_cooling = 100
    elif fault == "specs":
        p.specs["includes_outdoor_unit"] = False
    elif fault == "tags":
        p.tags.append(NS(slug="cat-multi"))
    elif fault == "price":
        p.price += 1
    elif fault == "publication":
        p.is_published = not p.is_published
    elif fault == "commerce":
        commerce[p.id]["local_stocks"] = [{"id": 1, "qty": 1}]
    else:
        p.product_kind = "complete_split_system"
    with pytest.raises(RepairBlocked):
        build_plan(manifest, products, commerce, now=NOW)


@pytest.mark.parametrize("specs,tag", [
    ({"includes_outdoor_unit": False}, None),
    ({"includes_indoor_unit": "нет"}, None),
    ({"includes_outdoor_unit": True, "__typed_specs": {"includes_outdoor_unit": {"value": False}}}, None),
    ({"__typed_specs": {"includes_indoor_unit": {"raw": "0"}}}, None),
    ({"indoor_units_count": 2}, None),
    ({"__typed_specs": {"indoor_units_count": {"value": 0}}}, None),
    ({"__typed_specs": {"type": {"value": "внутренний блок"}}}, None),
    ({}, "cat-multi"),
])
def test_component_veto_survives_recomputed_fixture_guards(catalog, monkeypatch, specs, tag):
    manifest, products, commerce = catalog
    p = next(p for p in products if p.id == 162)
    p.specs = specs
    if tag:
        p.tags.append(NS(slug=tag))
    row = next(r for r in manifest["products"] if r["identity"]["id"] == p.id)
    row["before"] = product_projection(p, commerce[p.id])
    row["before_sha256"] = digest(row["before"])
    pin_fixture(monkeypatch, manifest)
    with pytest.raises(RepairBlocked, match="component"):
        build_plan(manifest, products, commerce, now=NOW)


def test_polling_timestamps_are_neutral_but_business_fields_are_guarded():
    record = {"supplier_mappings": [{"id": 1, "supplier_id": 2, "product_id": 162,
        "external_id": "exact-kit", "is_active": True,
        "supplier": dict(id=2, name="Supplier", code="code", is_active=True, spreadsheet_id="sheet", spreadsheet_url="https://example.invalid"),
        "offer": {"qty": 2, "wholesale_value": "1000.00", "last_seen_at": "old", "updated_at": "old"}}], "local_stocks": []}
    before = commerce_projection(record, [])
    record["supplier_mappings"][0]["offer"].update(last_seen_at="new", updated_at="new")
    assert commerce_projection(record, []) == before
    record["supplier_mappings"][0]["offer"]["qty"] = 3
    assert commerce_projection(record, []) != before
