from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from scripts.repair_catalog_power_supply import require_primary
from services.catalog_power_supply_repair import (
    DEFAULT_MANIFEST, RepairBlocked, build_plan, digest, load_manifest,
    power_projection, repaired_specs, validate_manifest, validate_reviewed_plan,
)
from services.spec_registry import build_typed_specs

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


@pytest.fixture
def catalog():
    manifest = deepcopy(load_manifest())
    products = []
    for row in manifest["products"]:
        specs = {**deepcopy(row["before"]["specs"]), "__typed_specs": deepcopy(row["before"]["typed"])}
        specs.update({"unrelated": {"keep": [1, 2]}, "__filter_unrelated": 91, "power_cons_cooling_kw": "9.123"})
        specs["__typed_specs"]["unrelated"] = {"value": "exact"}
        products.append(SimpleNamespace(**row["identity"], specs=specs, price="preserve"))
    return manifest, products, [SimpleNamespace(**row) for row in manifest["brands"]]


def test_exact_82_row_plan_preserves_unrelated_values_and_repeats_as_noop(catalog):
    manifest, products, brands = catalog
    plan = build_plan(*catalog, now=NOW)
    assert plan["changed"] == len(plan["product_ids"]) == 82
    assert plan["brand_slugs"] == ["energolux", "hisense", "kinghome", "tcl"]
    assert "preserve" not in json.dumps(plan)
    for row, product in zip(manifest["products"], products):
        original = deepcopy(product.specs)
        updated = repaired_specs(product.specs, row)
        assert product.specs == original
        assert updated["unrelated"] == original["unrelated"]
        assert updated["__filter_unrelated"] == 91
        assert updated["power_cons_cooling_kw"] == "9.123"
        assert updated["__typed_specs"]["unrelated"] == {"value": "exact"}
        for key, value in row["specs_set"].items():
            assert updated[key] == value
            assert updated["__typed_specs"][key] == build_typed_specs({key: value})[key]
        if product.id in {520, 555, 558}:
            assert row["specs_set"] == {"power_supply_voltage": "220-240"}
            for key in ("power_supply", "power_supply_location"):
                assert updated[key] == original[key]
                assert updated["__typed_specs"][key] == original["__typed_specs"][key]
        product.specs = updated
    assert build_plan(manifest, products, brands, now=NOW)["changed"] == 0
    tcl = next(product for product in products if product.id == 179)
    assert "Напряжение, В" not in tcl.specs
    assert "380-415" in tcl.specs["power_supply_outdoor"]
    assert "220-240" in tcl.specs["power_supply_indoor"]
    assert "power_supply_location" not in tcl.specs
    assert "power_supply_indoor" not in next(product for product in products if product.id == 94).specs


@pytest.mark.parametrize("fault", ["missing", "extra", "title", "source_url", "kind", "brand", "new_raw", "new_alias", "new_typed", "unknown_family", "removed", "changed_typed", "partial"])
def test_missing_new_changed_or_partial_power_state_is_blocked(catalog, fault):
    manifest, products, brands = catalog
    tcl = next(product for product in products if product.id == 179)
    if fault == "missing":
        products.pop()
    elif fault == "extra":
        products.append(SimpleNamespace(id=99999))
    elif fault in {"title", "source_url", "kind", "brand"}:
        setattr(products[0], {"kind": "product_kind", "brand": "brand_id"}.get(fault, fault), "unreviewed")
    elif fault == "new_raw":
        products[0].specs["power_supply"] = "new"
    elif fault == "new_alias":
        products[0].specs[" Электропитание "] = "220"
    elif fault == "new_typed":
        products[0].specs["__typed_specs"]["power_supply"] = {"value": "new"}
    elif fault == "unknown_family":
        products[0].specs["power_supply_new_supplier_variant"] = "new"
    elif fault == "removed":
        tcl.specs.pop("Напряжение, В")
    elif fault == "changed_typed":
        tcl.specs["__typed_specs"]["power_supply_voltage"] = {"value": "unreviewed"}
    else:
        products[0].specs = repaired_specs(products[0].specs, manifest["products"][0])
    with pytest.raises(RepairBlocked):
        build_plan(manifest, products, brands, now=NOW)


def test_raw_and_typed_objects_are_required_and_internal_family_is_guarded():
    for value in ([], {"__typed_specs": []}):
        with pytest.raises(RepairBlocked):
            power_projection(value)
    assert power_projection({"__filter_power_supply": 380, "power_cons_cooling_kw": 2}) == {
        "specs": {"__filter_power_supply": 380}, "typed": {},
    }


@pytest.mark.parametrize("fault", ["price", "unreviewed_delete", "missing_before_hash", "duplicate_product", "other_guard", "alias_no_replacement", "missing_source"])
def test_manifest_cannot_expand_power_mutation_scope(catalog, fault):
    manifest = catalog[0]
    row = manifest["products"][0]
    if fault == "price":
        row["specs_set"]["price"] = "10"
    elif fault == "unreviewed_delete":
        row["specs_delete"].append("unrelated")
    elif fault == "missing_before_hash":
        row["before_sha256"] = "0" * 64
    elif fault == "duplicate_product":
        manifest["products"].append(deepcopy(row))
    elif fault == "other_guard":
        row["before"]["specs"]["wifi_state"] = "none"
        row["before_sha256"] = digest(row["before"])
    elif fault == "alias_no_replacement":
        row["before"]["specs"]["Напряжение, В"] = "220"
        row["before_sha256"] = digest(row["before"])
        row["specs_delete"].append("Напряжение, В")
        row["specs_set"].pop("power_supply_voltage")
    else:
        row["evidence"] = []
    with pytest.raises(RepairBlocked):
        validate_manifest(manifest)


def test_checked_in_manifest_digest_is_pinned(tmp_path):
    manifest = json.loads(DEFAULT_MANIFEST.read_text())
    manifest["products"][0]["specs_set"]["power_supply"] = "unreviewed source edit"
    changed = tmp_path / "edited.json"
    changed.write_text(json.dumps(manifest))
    with pytest.raises(RepairBlocked, match="checked-in"):
        load_manifest(changed)


@pytest.mark.parametrize("fault", ["expired", "future", "digest", "changed_operation"])
def test_full_reviewed_plan_digest_time_and_payload_are_validated(catalog, fault):
    plan = build_plan(*catalog, now=NOW)
    reviewed = deepcopy(plan)
    if fault == "expired":
        now = NOW + timedelta(minutes=30)
    elif fault == "future":
        now = NOW - timedelta(seconds=1)
    else:
        now = NOW
    if fault == "digest":
        reviewed["changed"] = 0
    elif fault == "changed_operation":
        reviewed["operations"] = []
        reviewed["plan_digest"] = digest({key: value for key, value in reviewed.items() if key != "plan_digest"})
    with pytest.raises(RepairBlocked):
        validate_reviewed_plan(reviewed, plan, reviewed["plan_digest"], now=now)
    validate_reviewed_plan(plan, plan, plan["plan_digest"], now=NOW + timedelta(minutes=29))


@pytest.mark.parametrize("role", [None, True, "false", 0])
def test_primary_requires_positive_boolean_proof(role):
    with pytest.raises(RepairBlocked):
        require_primary(True, role)
    require_primary(False, role)
    require_primary(True, False)
