from types import SimpleNamespace

import pytest

from services.catalog_user_wifi_repair import load_user_wifi_manifest, user_wifi_repair_plan


def _products(manifest):
    return [
        SimpleNamespace(
            id=entry["id"],
            title=entry["title"],
            product_kind=entry["product_kind"],
            specs={
                "model_indoor": entry["model_indoor"],
                "model_outdoor": entry["model_outdoor"],
                "wifi_state": entry["old_state"],
                "wifi_ready": entry["old_ready"],
                "area_m2": 35,
                "__typed_specs": {"area_m2": {"value": 35}},
            },
        )
        for entry in manifest["wifi"]
    ]


def test_user_wifi_repair_is_exact_and_idempotent():
    manifest = load_user_wifi_manifest()
    products = _products(manifest)

    plan, changes = user_wifi_repair_plan(products, manifest)

    assert plan["matched"] == 18
    assert plan["changed"] == 18
    assert plan["wifi_states"] == {"builtin": 13, "ready": 5}
    assert len(changes) == 18
    for product, updated in changes:
        assert updated["area_m2"] == 35
        assert updated["__typed_specs"]["area_m2"] == {"value": 35}
        product.specs = updated

    repeated, no_changes = user_wifi_repair_plan(products, manifest)
    assert repeated["changed"] == 0
    assert no_changes == []


def test_user_wifi_repair_rejects_changed_model_and_source():
    manifest = load_user_wifi_manifest()
    products = _products(manifest)
    products[0].specs["model_indoor"] = "OTHER"
    with pytest.raises(ValueError, match="identity changed"):
        user_wifi_repair_plan(products, manifest)

    products = _products(manifest)
    products[0].specs["wifi_ready"] = "mystery"
    with pytest.raises(ValueError, match="Wi-Fi source changed"):
        user_wifi_repair_plan(products, manifest)


def test_user_wifi_manifest_covers_confirmed_series_exceptions():
    entries = {entry["id"]: entry for entry in load_user_wifi_manifest()["wifi"]}
    assert {entries[product_id]["new_state"] for product_id in (900, 901, 902, 903, 904, 1055, 1056)} == {"builtin"}
    assert {entries[product_id]["new_state"] for product_id in (100, 103, 107, 108, 905, 906)} == {"builtin"}
    assert {entries[product_id]["new_state"] for product_id in (59, 60, 101, 104, 109)} == {"ready"}
