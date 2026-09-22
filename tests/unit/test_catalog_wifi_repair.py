from types import SimpleNamespace

import pytest

from services.catalog_wifi_repair import WIFI_CORRECTIONS, repaired_wifi_specs, wifi_repair_plan


def test_wifi_repair_changes_only_wifi_fields():
    original = {"wifi_ready": False, "wifi_state": "none", "area_m2": 35, "__typed_specs": {"area_m2": {"value": 35}}}
    updated = repaired_wifi_specs(original, "builtin")

    assert updated["wifi_ready"] is True
    assert updated["wifi_state"] == "builtin"
    assert updated["__filter_wifi"] is True
    assert updated["__filter_wifi_builtin"] is True
    assert updated["area_m2"] == 35
    assert updated["__typed_specs"]["area_m2"] == {"value": 35}
    assert repaired_wifi_specs(updated, "builtin") is None


def test_wifi_repair_rejects_changed_source():
    with pytest.raises(ValueError, match="Unexpected Wi-Fi source"):
        repaired_wifi_specs({"wifi_ready": "ready", "wifi_state": "ready"}, "builtin")


def test_wifi_plan_requires_exact_reviewed_models():
    products = [SimpleNamespace(id=product_id, title=title, specs={"wifi_ready": False}) for product_id, (title, _) in WIFI_CORRECTIONS.items()]
    plan, changes = wifi_repair_plan(products)

    assert plan["changed"] == 10
    assert plan["by_state"] == {"ready": 2, "builtin": 8}
    assert len(changes) == 10
    products[0].title = "Changed model"
    with pytest.raises(ValueError, match="title differs"):
        wifi_repair_plan(products)
