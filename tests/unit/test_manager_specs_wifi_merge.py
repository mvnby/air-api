from services.manager_specs_service import _merge_spec_update
from services.spec_normalizer import normalize_specs


def test_bulk_wifi_state_edit_replaces_stale_flat_and_derived_fields():
    current = normalize_specs({"wifi_ready": False, "area_m2": 35})

    merged = _merge_spec_update(current, {"wifi_state": "ready"})
    updated = normalize_specs(merged)

    assert updated["wifi_ready"] == "ready"
    assert updated["wifi_state"] == "ready"
    assert updated["__filter_wifi"] is True
    assert updated["area_m2"] == 35


def test_bulk_wifi_ready_edit_replaces_stale_state_and_raw_module():
    current = normalize_specs({"wifi_module": "встроен", "area_m2": 35})

    merged = _merge_spec_update(current, {"wifi_ready": "false"})
    updated = normalize_specs(merged)

    assert updated["wifi_ready"] is False
    assert updated["wifi_state"] == "none"
    assert updated["__filter_wifi"] is False
    assert updated["area_m2"] == 35
