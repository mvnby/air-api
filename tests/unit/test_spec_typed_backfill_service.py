from services.spec_typed_backfill_service import build_specs_with_typed_internal_layer


def test_typed_backfill_preserves_public_flat_specs():
    original = {
        "Мощность охлаждения": "2,5 кВт",
        "Шум внутреннего блока": "23/26/31/35",
        "Wi-Fi": "Опция",
    }

    updated = build_specs_with_typed_internal_layer(original)

    assert updated["Мощность охлаждения"] == "2,5 кВт"
    assert updated["Шум внутреннего блока"] == "23/26/31/35"
    assert updated["Wi-Fi"] == "Опция"
    assert "capacity_cooling_kw" not in updated
    assert "noise_indoor" not in updated
    assert updated["__filter_wifi"] is True
    assert updated["__filter_wifi_builtin"] is False
    assert updated["__typed_specs"]["capacity_cooling_kw"]["value"] == 2.5
    assert updated["__typed_specs"]["noise_indoor"]["values"] == [23, 26, 31, 35]
    assert updated["__typed_specs"]["wifi_state"]["value"] == "ready"


def test_typed_backfill_refreshes_stale_internal_specs():
    original = {
        "Рабочая температура при обогреве": "от -20 до +30 °C",
        "__filter_min_heat": -5,
        "__typed_specs": {"old": {"value": "stale"}},
    }

    updated = build_specs_with_typed_internal_layer(original)

    assert updated["Рабочая температура при обогреве"] == "от -20 до +30 °C"
    assert updated["__filter_min_heat"] == -20
    assert "old" not in updated["__typed_specs"]
    assert updated["__typed_specs"]["temp_range_heat"]["min"] == -20
    assert updated["__typed_specs"]["temp_range_heat"]["max"] == 30

