from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services.catalog_decision_data_repair import (
    KIND_IDS, POWER_TARGETS, PRODUCT_IDS, SOURCE_HASHES, KINGHOME_PDF, TCL_PDF,
    SUPPLIER_SHEET, RepairBlocked, build_plan, digest, load_manifest,
    validate_manifest, validate_reviewed_plan,
)

NOW = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def catalog():
    products, rows = [], []
    for pid in sorted(PRODUCT_IDS):
        kind = pid in KIND_IDS
        target = POWER_TARGETS.get(pid, 10.55)
        specs = {
            "type": "полупромышленный кондиционер", "capacity_cooling_kw": str(target),
            "__typed_specs": {"capacity_cooling_kw": {"value": target, "nominal": target}},
            "untouched": {"raw": [1, 2]},
        }
        if kind:
            specs.update(includes_indoor_unit="true", includes_outdoor_unit=True, indoor_units_count="1")
        brand = SimpleNamespace(slug="kinghome" if kind else "tcl")
        identity = dict(id=pid, brand_id=4 if kind else 3, title=f"Exact model {pid}", slug=f"model-{pid}", source_url=KINGHOME_PDF if kind else TCL_PDF, series_id=231 if kind else 232)
        product = SimpleNamespace(**identity, specs=specs, product_kind="other" if kind else "complete_split_system", power_cooling=target if kind else 2.0, tags=[SimpleNamespace(slug="cat-industrial")], brand=brand, series=SimpleNamespace(slug="source-series"), price=4321, main_image="keep.webp")
        before = dict(product_kind=product.product_kind, power_cooling=product.power_cooling, specs_sha256=digest(specs), tag_slugs=["cat-industrial"])
        source = KINGHOME_PDF if kind else TCL_PDF
        evidence = [{"source_url": source, "source_sha256": SOURCE_HASHES[source], "locator": "PDF page 20; exact model column", "capacity_cooling_kw": target}]
        row = dict(identity=identity, before=before, before_sha256=digest(before), fields_set={"product_kind": "complete_split_system"} if kind else {"power_cooling": target}, evidence=evidence)
        if pid == 191:
            row.update(fields_set={}, blocked_reason="blocked_source_conflict")
            row["evidence"].append({"source_url": SUPPLIER_SHEET, "source_sha256": SOURCE_HASHES[SUPPLIER_SHEET], "locator": "TCL PAC row 51", "capacity_cooling_kw": 10.55})
        products.append(product)
        rows.append(row)
    return {"schema_version": 1, "sources": SOURCE_HASHES, "products": rows}, products


def _apply(plan, products):
    by_id = {p.id: p for p in products}
    for operation in plan["operations"]:
        for key, value in operation["fields_set"].items():
            setattr(by_id[operation["id"]], key, value)


def test_exact_plan_preserves_specs_price_media_and_becomes_noop(catalog):
    manifest, products = catalog
    original = deepcopy(products)
    plan = build_plan(manifest, products, now=NOW)
    assert plan["changed"] == 34
    assert len(plan["observed"]) == 35
    assert plan["manual_review_required"] is True
    assert plan["manual_kind_provenance"] == "unavailable_in_product_schema"
    assert plan["blocked_items"][0]["id"] == 191
    assert 191 not in plan["product_ids"]
    assert all(set(op["fields_set"]) in ({"product_kind"}, {"power_cooling"}) for op in plan["operations"])
    _apply(plan, products)
    noop = build_plan(manifest, products, now=NOW)
    assert noop["changed"] == 0 and noop["manual_review_required"] is False
    assert noop["product_ids"] == noop["brand_slugs"] == noop["series_paths"] == []
    for previous, current in zip(original, products):
        assert current.specs == previous.specs
        assert current.price == previous.price and current.main_image == previous.main_image
        assert current.source_url == previous.source_url


@pytest.mark.parametrize("fault", ["missing", "extra", "identity", "source_url", "kind", "power", "specs", "tags", "partial"])
def test_current_state_drift_fails_closed(catalog, fault):
    manifest, products = catalog
    if fault == "missing":
        products.pop()
    elif fault == "extra":
        products.append(SimpleNamespace(id=999999))
    elif fault == "identity":
        products[0].title += " edited"
    elif fault == "source_url":
        products[0].source_url = "https://example.invalid"
    elif fault == "kind":
        products[0].product_kind = "indoor_unit"
    elif fault == "power":
        products[0].power_cooling = 123
    elif fault == "specs":
        products[0].specs["untouched"] = "edited"
    elif fault == "tags":
        products[0].tags.append(SimpleNamespace(slug="new-tag"))
    else:
        products[0].product_kind = "complete_split_system"
    with pytest.raises(RepairBlocked):
        build_plan(manifest, products, now=NOW)


@pytest.mark.parametrize("fault", ["false_flag", "count", "multi", "type", "nominal", "typed_nominal", "typed_value"])
def test_exact_hash_alone_does_not_override_source_facts(catalog, fault):
    manifest, products = catalog
    product = products[0] if fault in {"false_flag", "count", "multi", "type"} else next(p for p in products if p.id == 180)
    if fault == "false_flag":
        product.specs["includes_outdoor_unit"] = False
    elif fault == "count":
        product.specs["indoor_units_count"] = "2"
    elif fault == "multi":
        product.tags.append(SimpleNamespace(slug="cat-multi"))
    elif fault == "type":
        product.specs["type"] = "внутренний блок"
    elif fault == "nominal":
        product.specs["capacity_cooling_kw"] = "5.69"
    elif fault == "typed_nominal":
        product.specs["__typed_specs"]["capacity_cooling_kw"]["value"] = 5.69
        product.specs["__typed_specs"]["capacity_cooling_kw"]["nominal"] = 5.69
    else:
        product.specs["__typed_specs"]["capacity_cooling_kw"]["value"] = 5.69
    row = next(r for r in manifest["products"] if r["identity"]["id"] == product.id)
    row["before"]["specs_sha256"] = digest(product.specs)
    row["before"]["tag_slugs"] = sorted(t.slug for t in product.tags)
    row["before_sha256"] = digest(row["before"])
    with pytest.raises(RepairBlocked):
        build_plan(manifest, products, now=NOW)


@pytest.mark.parametrize("fault", ["scope", "source", "price", "nominal", "blocked191", "before_hash", "evidence"])
def test_manifest_rejects_expansion_and_unreviewed_evidence(catalog, fault):
    manifest = catalog[0]
    row = manifest["products"][0]
    if fault == "scope":
        manifest["products"].pop()
    elif fault == "source":
        manifest["sources"] = {**SOURCE_HASHES, TCL_PDF: "0" * 64}
    elif fault == "price":
        row["fields_set"]["price"] = 1
    elif fault == "nominal":
        next(r for r in manifest["products"] if r["identity"]["id"] == 180)["fields_set"]["power_cooling"] = 5.69
    elif fault == "blocked191":
        next(r for r in manifest["products"] if r["identity"]["id"] == 191)["fields_set"] = {"power_cooling": 10.55}
    elif fault == "before_hash":
        row["before_sha256"] = "0" * 64
    else:
        row["evidence"] = []
    with pytest.raises(RepairBlocked):
        validate_manifest(manifest)


def test_execution_requires_fresh_untampered_plan_and_explicit_manual_review(catalog):
    reviewed = build_plan(*catalog, now=NOW)
    live = build_plan(*catalog, now=NOW + timedelta(minutes=1))
    token = reviewed["plan_digest"]
    with pytest.raises(RepairBlocked, match="Manual kind provenance"):
        validate_reviewed_plan(reviewed, live, token, now=NOW)
    with pytest.raises(RepairBlocked, match="Manual kind provenance"):
        validate_reviewed_plan(reviewed, live, token, manual_kind_review_digest="0" * 64, now=NOW)
    validate_reviewed_plan(reviewed, live, token, manual_kind_review_digest=token, now=NOW)
    with pytest.raises(RepairBlocked, match="expired"):
        validate_reviewed_plan(reviewed, live, token, manual_kind_review_digest=token, now=NOW + timedelta(minutes=30))
    changed = deepcopy(reviewed)
    changed["operations"][0]["fields_set"]["product_kind"] = "other"
    with pytest.raises(RepairBlocked, match="digest"):
        validate_reviewed_plan(changed, live, token, manual_kind_review_digest=token, now=NOW)
    changed["plan_digest"] = digest({key: value for key, value in changed.items() if key != "plan_digest"})
    with pytest.raises(RepairBlocked, match="state digest"):
        validate_reviewed_plan(changed, live, changed["plan_digest"], manual_kind_review_digest=changed["plan_digest"], now=NOW)
    live["state_digest"] = "0" * 64
    with pytest.raises(RepairBlocked, match="changed"):
        validate_reviewed_plan(reviewed, live, token, manual_kind_review_digest=token, now=NOW)


def test_primary_must_be_positively_verified():
    from scripts.repair_catalog_decision_data import require_primary
    require_primary(False, True)
    require_primary(True, False)
    for value in (True, None, "false", 0):
        with pytest.raises(RepairBlocked, match="primary"):
            require_primary(True, value)


def test_checked_in_manifest_retains_fixed_scope_and_blocked_conflict():
    manifest = load_manifest()
    assert len(manifest["products"]) == 35
    assert next(row for row in manifest["products"] if row["identity"]["id"] == 191)["fields_set"] == {}
