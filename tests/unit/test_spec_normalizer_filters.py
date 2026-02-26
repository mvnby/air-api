from services.spec_normalizer import normalize_specs


def test_enrich_filter_keys_from_strings():
    specs = normalize_specs(
        {
            "Рабочая температура при обогреве": "от -20 до +30 °C",
            "Wi-Fi": "да",
            "Шум внутреннего блока": "16 — 44 дБ",
        }
    )

    assert specs["__filter_min_heat"] == -20
    assert specs["__filter_wifi"] is True
    assert specs["__filter_noise_min"] == 16


def test_enrich_filter_keys_rebuilds_stale_values():
    specs = normalize_specs(
        {
            "temp_range_heat": "от -25 до +24 °C",
            "wifi_ready": False,
            "__filter_min_heat": -10,
            "__filter_wifi": True,
        }
    )

    assert specs["__filter_min_heat"] == -25
    assert specs["__filter_wifi"] is False
    assert "__filter_noise_min" not in specs


def test_compressor_type_norm_variants():
    full_dc = normalize_specs({"inverter_type": "Full DC Inverter"})
    assert full_dc["compressor_type_norm"] == "full_dc"

    inverter = normalize_specs({"inverter_type": "Inverter", "inverter": True})
    assert inverter["compressor_type_norm"] == "inverter"

    on_off = normalize_specs({"inverter_type": "on/off", "inverter": False})
    assert on_off["compressor_type_norm"] == "on_off"


def test_wifi_module_alias_sets_wifi_filter_flags():
    specs = normalize_specs({"wifi_module": "true"})

    assert specs["wifi_ready"] is True
    assert specs["__filter_wifi"] is True
    assert specs["__filter_wifi_builtin"] is True


def test_wifi_ready_false_does_not_override_wifi_module_true():
    specs = normalize_specs({"wifi_ready": False, "wifi_module": "true"})

    assert specs["wifi_ready"] is True
    assert specs["__filter_wifi"] is True


def test_dynamic_wifi_key_mapping_from_onliner_specs():
    specs = normalize_specs({"Wi-Fi модуль (опция)": "приобретается отдельно"})

    assert specs["wifi_ready"] == "ready"
    assert specs["__filter_wifi"] is True
    assert specs["__filter_wifi_builtin"] is False
