from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from services.catalog_decision_data_repair import RepairBlocked, digest, validate_reviewed_plan
from services.catalog_decision_price_repair import SCOPE_IDS, apply_operation, build_plan, load_manifest, validate_manifest
from services.catalog_decision_source_repair import load_manifest as load_original_manifest
from services.catalog_decision_data_repair import POWER_TARGETS, load_manifest as load_prior_repairs
from services.product_cooling_capacity import nominal_cooling_capacity
from tests.catalog_decision_price_repair_support import pin_fixture, prepared_catalog, refresh_guards

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


@pytest.fixture
def catalog(monkeypatch):
    values = prepared_catalog()
    pin_fixture(monkeypatch, values[0])
    return values


def test_exact_approved_scope_source_policy_and_original_manifest_preserved():
    manifest = load_manifest()
    candidates = [r for r in manifest["products"] if r["fields_set"]]
    technical = [r for r in candidates if r["patches"]]
    assert len(manifest["products"]) == len(SCOPE_IDS) == 217
    assert len(candidates) == 167 and len(technical) == 67
    assert sum(len(r["patches"]) for r in technical) == 319
    assert Counter(r["disposition"] for r in manifest["products"]) == {
        "approved_system": 167, "defer_unconfirmed_history": 42, "actual_blocker": 5, "standalone_indoor": 3}
    held = {r["identity"]["id"] for r in manifest["products"] if not r["fields_set"]}
    assert {188, 189, 191, 1004, 1005, 1080, 1082, 1084} <= held
    assert not {94, 95, 96, 97, 98, 99, 180, 196, *range(1297, 1310)} & SCOPE_IDS
    original = load_original_manifest()
    assert digest(original) == "1ae8feb3c36db550ed7f15f8303188624dd9aaa8f5eeb2095b4b0be94b67c0ee"
    assert sum(bool(r["fields_set"]) for r in original["products"]) == 149
    # Literal winter SKU nominals must not silently revert to a base model's power.
    for pid, kw in [(556, 7.0), (559, 7.2), (924, 17.15), (949, 16.1), (951, 14.1)]:
        row = next(r for r in manifest["products"] if r["identity"]["id"] == pid)
        assert next(p["after"] for p in row["patches"] if p["path"] == "power_cooling") == kw


def test_public_manifest_omits_private_prices_records_and_sheet_urls():
    forbidden = {"price", "old_price", "wholesale_value", "wholesale_raw", "rrc_byn", "rrc_raw",
                 "qty", "qty_raw", "supplier_mappings", "local_stocks"}

    def inspect(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for item in value.values():
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)
        elif isinstance(value, str):
            assert "docs.google.com/spreadsheets/" not in value

    inspect(load_manifest())


def test_previous_34_targets_survive_later_individually_approved_tcl_kinds():
    rows = {r["identity"]["id"]: r for r in load_manifest()["products"]}
    prior = {r["identity"]["id"]: r for r in load_prior_repairs()["products"]}
    later_kinds = []
    for pid, power in POWER_TARGETS.items():
        if pid in rows:
            row = rows[pid]
            assert not row["patches"]
            assert row["target"]["power_cooling"] == power
            assert row["target"]["specs_sha256"] == prior[pid]["before"]["specs_sha256"]
            if row["fields_set"]:
                later_kinds.append(pid)
                assert prior[pid]["before"]["product_kind"] == "other"
                assert row["target"]["product_kind"] == "complete_split_system"
    # The old kind guard is deliberately superseded for these cards. Verify
    # its repaired fields directly instead of rerunning that historical plan.
    assert sorted(later_kinds) == [179, 181, 182, 183, 184, 185, 186, 187, 190, 192, 193]


def test_readonly_plan_exact_patches_manual_review_and_idempotence(catalog):
    manifest, products, commerce = catalog
    originals = deepcopy(products)
    plan = build_plan(manifest, products, commerce, now=NOW)
    assert products == originals  # A dry-run must not mutate even in-memory state.
    assert plan["changed"] == 167 and len(plan["blocked_items"]) == 50
    assert plan["technical_changes"] == {"products": 67, "fields": 319}
    with pytest.raises(RepairBlocked, match="Manual kind provenance"):
        validate_reviewed_plan(plan, plan, plan["plan_digest"], now=NOW)
    validate_reviewed_plan(plan, plan, plan["plan_digest"], manual_kind_review_digest=plan["plan_digest"], now=NOW)
    with pytest.raises(RepairBlocked, match="expired"):
        validate_reviewed_plan(plan, plan, plan["plan_digest"], manual_kind_review_digest=plan["plan_digest"], now=NOW + timedelta(minutes=30))
    by_id = {p.id: p for p in products}
    for operation in plan["operations"]:
        apply_operation(by_id[operation["id"]], operation)
    noop = build_plan(manifest, products, commerce, now=NOW)
    assert noop["changed"] == 0 and noop["technical_changes"] == {"products": 0, "fields": 0}
    rows = {r["identity"]["id"]: r for r in manifest["products"]}
    for old, new in zip(originals, products):
        row = rows[new.id]
        if not row["fields_set"]:
            assert old == new
        assert {k: v for k, v in vars(old).items() if k not in {"product_kind", "specs", "power_cooling"}} == {
            k: v for k, v in vars(new).items() if k not in {"product_kind", "specs", "power_cooling"}}
        changed_spec_keys = {p["path"].split(".")[1] for p in row["patches"] if p["path"].startswith("specs.")}
        assert {k: v for k, v in old.specs.items() if k not in changed_spec_keys} == {k: v for k, v in new.specs.items() if k not in changed_spec_keys}
        for patch in row["patches"]:
            if patch["path"] == "power_cooling":
                assert nominal_cooling_capacity(new.specs, fallback=new.power_cooling) == patch["after"]


@pytest.mark.parametrize("fault", ["kind", "spec", "typed", "retail", "commerce", "held", "identity", "missing", "partial_kind", "partial_technical"])
def test_drift_and_partial_application_abort_entire_plan(catalog, fault):
    manifest, products, commerce = catalog
    by_id = {p.id: p for p in products}
    p = by_id[161]
    if fault == "kind":
        p.product_kind = "indoor_unit"
    elif fault == "spec":
        p.specs["unrelated_manual_edit"] = "keep"
    elif fault == "typed":
        p.specs.setdefault("__typed_specs", {})["model_outdoor"] = {"value": "another-suffix"}
    elif fault == "retail":
        p.price += 1
    elif fault == "commerce":
        commerce[p.id]["mappings"].append({"is_active": False})
    elif fault == "held":
        by_id[191].power_cooling = 10.55
    elif fault == "identity":
        p.slug += "-new"
    elif fault == "missing":
        products.pop()
    elif fault == "partial_kind":
        p.product_kind = "complete_split_system"
    else:
        apply_operation(p, next(r for r in manifest["products"] if r["identity"]["id"] == 161))
    with pytest.raises(RepairBlocked):
        build_plan(manifest, products, commerce, now=NOW)


@pytest.mark.parametrize("fault", ["kind", "path", "value", "source", "scope", "before", "target"])
def test_exact_manifest_pin_rejects_every_unreviewed_change(fault):
    manifest = deepcopy(load_manifest())
    row = next(r for r in manifest["products"] if r["patches"])
    if fault == "kind":
        row["fields_set"]["product_kind"] = "indoor_unit"
    elif fault == "path":
        row["patches"][0]["path"] = "specs.temp_range_heat"
    elif fault == "value":
        row["patches"][0]["after"] = "different"
    elif fault == "source":
        row["evidence"][0]["source_sha256"] = "0" * 64
    elif fault == "scope":
        manifest["products"].pop()
    else:
        row[fault]["specs_sha256"] = "0" * 64
    with pytest.raises(RepairBlocked, match="Unreviewed"):
        validate_manifest(manifest)


@pytest.mark.parametrize("key,value", [
    ("includes_outdoor_unit", False), ("includes_indoor_unit", "нет"),
    ("__typed_specs", {"includes_outdoor_unit": {"value": False}}),
    ("__typed_specs", {"includes_indoor_unit": {"raw": "0"}}),
    ("indoor_units_count", 2), ("type", "внутренний блок"),
])
def test_source_review_cannot_bypass_explicit_component_veto(catalog, monkeypatch, key, value):
    manifest, products, commerce = catalog
    p = next(p for p in products if p.id == 170)  # No technical patches on this card.
    row = next(r for r in manifest["products"] if r["identity"]["id"] == p.id)
    assert not row["patches"]
    p.specs[key] = value
    refresh_guards(row, p, commerce[p.id])
    pin_fixture(monkeypatch, manifest)
    with pytest.raises(RepairBlocked, match="component"):
        build_plan(manifest, products, commerce, now=NOW)
