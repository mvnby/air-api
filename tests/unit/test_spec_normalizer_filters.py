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
