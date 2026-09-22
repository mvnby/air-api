from types import SimpleNamespace

from services.catalog_indoor_type_repair import indoor_repair_plan, repaired_indoor_specs


def test_repair_changes_only_incorrect_indoor_internal_fields():
    original = {
        "indoor_type": "консольный",
        "wifi_ready": "ready",
        "__filter_wifi": True,
        "__typed_specs": {
            "indoor_type": {"value": "column", "raw": "консольный"},
            "wifi_state": {"value": "ready"},
        },
    }

    updated, slug = repaired_indoor_specs(original)

    assert slug == "console"
    assert updated["indoor_type"] == original["indoor_type"]
    assert updated["wifi_ready"] == original["wifi_ready"]
    assert updated["__filter_wifi"] == original["__filter_wifi"]
    assert updated["__filter_indoor_type"] == "console"
    assert updated["__typed_specs"]["indoor_type"]["value"] == "console"
    assert updated["__typed_specs"]["wifi_state"] == original["__typed_specs"]["wifi_state"]
    assert "__filter_indoor_type" not in original
    assert repaired_indoor_specs(updated) is None


def test_repair_plan_digest_changes_when_a_candidate_changes():
    product = SimpleNamespace(id=17, specs={"indoor_type": "настенный", "__typed_specs": {"indoor_type": {"value": "настенный"}}})
    first, changes = indoor_repair_plan([product])

    assert first["changed"] == 1
    assert first["by_form"] == {"wall": 1}
    assert first["by_issue"] == {"filter": 1, "typed": 1}
    assert changes[0][1]["__typed_specs"]["indoor_type"]["value"] == "wall"

    product.specs = {**product.specs, "price_note": "edited"}
    second, _ = indoor_repair_plan([product])
    assert first["plan_digest"] != second["plan_digest"]
