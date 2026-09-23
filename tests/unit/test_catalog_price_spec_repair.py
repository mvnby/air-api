from types import SimpleNamespace

import pytest

from services.catalog_price_spec_repair import load_price_repair_manifest, price_spec_repair_plan


def _reviewed_products(manifest):
    products = []
    for entry in manifest["indoor_forms"]:
        products.append(SimpleNamespace(
            id=entry["id"], title=entry["title"],
            specs={"indoor_type": entry["old_form"], "area_m2": 42, "__typed_specs": {"area_m2": {"value": 42}}},
        ))
    for entry in manifest["wifi"]:
        products.append(SimpleNamespace(
            id=entry["id"], title=entry["title"],
            specs={"wifi_state": entry["old_state"], "wifi_ready": entry["old_ready"], "area_m2": 42,
                   "__typed_specs": {"area_m2": {"value": 42}}},
        ))
    return products


def test_price_repair_is_exact_and_idempotent():
    manifest = load_price_repair_manifest()
    products = _reviewed_products(manifest)
    assert all(
        entry["model_indoor"] in entry["title"] and entry["model_outdoor"] in entry["title"]
        for entry in manifest["wifi"]
    )

    plan, changes = price_spec_repair_plan(products, manifest)

    assert plan["matched"] == 57
    assert plan["changed"] == 57
    assert plan["indoor_forms"] == {
        "канальный": 7, "кассетный": 14, "консольный": 5,
    }
    assert plan["wifi_states"] == {"builtin": 5, "ready": 26}
    assert len(changes) == 57
    for product, specs, title in changes:
        assert specs["area_m2"] == 42
        assert specs["__typed_specs"]["area_m2"] == {"value": 42}
        product.specs = specs
        product.title = title

    repeated, no_changes = price_spec_repair_plan(products, manifest)
    assert repeated["changed"] == 0
    assert no_changes == []


def test_price_repair_rejects_changed_model_or_source():
    manifest = load_price_repair_manifest()
    products = _reviewed_products(manifest)
    products[0].title = "Another model"
    with pytest.raises(ValueError, match="form source or title changed"):
        price_spec_repair_plan(products, manifest)

    products = _reviewed_products(manifest)
    wifi = next(product for product in products if product.id == manifest["wifi"][0]["id"])
    wifi.specs["wifi_ready"] = "ready"
    with pytest.raises(ValueError, match="Wi-Fi source or title changed"):
        price_spec_repair_plan(products, manifest)


def test_price_repair_digest_changes_with_unrelated_spec():
    manifest = load_price_repair_manifest()
    products = _reviewed_products(manifest)
    first, _ = price_spec_repair_plan(products, manifest)
    products[0].specs["other_note"] = "changed"
    second, _ = price_spec_repair_plan(products, manifest)
    assert first["plan_digest"] != second["plan_digest"]
