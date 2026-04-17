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


def test_brand_normalization_and_auto_tag_slug_output():
    auto_slugs = []
    specs = normalize_specs(
        {"Бренд": "TCL", "Тип кондиционера": "сплит-система"},
        title="TCL Elite TAC-09",
        auto_tag_slugs=auto_slugs,
    )

    assert specs["brand"] == "TCL"
    assert "tcl" in auto_slugs


def test_invalid_brand_value_falls_back_to_title_brand():
    auto_slugs = []
    specs = normalize_specs(
        {"Бренд": "Мульти-сплит-система", "Тип": "мульти-сплит-система"},
        title="Мульти-сплит-система TCL Free Match Inverter",
        auto_tag_slugs=auto_slugs,
    )

    assert specs["brand"] == "TCL"
    assert "tcl" in auto_slugs


def test_multisplit_russian_keys_are_normalized():
    specs = normalize_specs(
        {
            "Тип": "внутренний блок",
            "Инверторный": "да",
            "Максимальное количество внутренних блоков": "4",
        }
    )

    assert specs["type"] == "внутренний блок"
    assert specs["inverter"] is True
    assert specs["multi_max_indoor_units"] == "4"
    assert "Тип" not in specs
    assert "Инверторный" not in specs
    assert "Максимальное количество внутренних блоков" not in specs


def test_indoor_type_filter_key_for_semi_industrial():
    cassette = normalize_specs({"Тип внутреннего блока": "кассетный"})
    assert cassette["__filter_indoor_type"] == "cassette"

    duct = normalize_specs({"indoor_type": "Канальный"})
    assert duct["__filter_indoor_type"] == "duct"

    floor_ceiling = normalize_specs({"Тип внутреннего блока": "напольно-потолочный"})
    assert floor_ceiling["__filter_indoor_type"] == "floor_ceiling"


def test_hobot_power_and_controls_keys_are_normalized():
    specs = normalize_specs(
        {
            "Мощность охлаждения, кВт": "2.80",
            "Мощность обогрева, кВт": "3.63",
            "Рабочий диапазон температур при охлаждении, °C": "от -15 до +53",
            "Рабочий диапазон температур при обогреве, °C": "от -20 до +30",
            "Инверторное управление мощностью": "Есть",
            "Пульт": "Есть",
            "Режим осушения воздуха": "есть",
            "Регулятор скорости вращения вентилятора": "Есть",
        }
    )

    assert specs["capacity_cooling_kw"] == "2.80"
    assert specs["capacity_heating_kw"] == "3.63"
    assert specs["temp_range_cool"] == "от -15 до +53"
    assert specs["temp_range_heat"] == "от -20 до +30"
    assert specs["inverter"] is True
    assert specs["remote_control"] is True
    assert specs["dehumidification"] is True
    assert specs["fan_speed"] is True


def test_haierproff_core_keys_are_normalized():
    specs = normalize_specs(
        {
            "Охлаждение, кВт": "5,2",
            "Нагрев, кВт": "6,0",
            "Рекомендованная площадь, м 2": "35 - 50",
            "Марка используемого хладагента": "R32",
            "Диаметр жидкостной линии, мм": "6,35",
            "Диаметр газовой линии, мм": "9,52",
            "Инверторный компрессор": "Да",
        }
    )

    assert specs["capacity_cooling_kw"] == "5.2"
    assert specs["capacity_heating_kw"] == "6.0"
    assert specs["area_m2"] == "50"
    assert specs["freon_type"] == "R32"
    assert specs["pipe_liquid"] == "6.35"
    assert specs["pipe_gas"] == "9.52"
    assert specs["inverter"] is True


def test_min_nom_max_values_use_nominal_component():
    specs = normalize_specs(
        {
            "Мощность охлаждения (Мин/Ном/Макс), кВт": "0.89 / 2.5 / 3.7",
            "Мощность нагрева (Мин/Ном/Макс), кВт": "0.89 / 3.3 / 4.1",
            "Потребление электроэнергии в режиме охлаждения (Мин / Ном / Макс), кВт": "0.20 / 0.656 / 1.4",
            "Потребление электроэнергии в режиме нагрева (Мин / Ном / Макс), кВт": "0.195 / 0.800 / 1.6",
            "Тип системы": "Инверторная",
        }
    )

    assert specs["capacity_cooling_kw"] == "2.5"
    assert specs["capacity_heating_kw"] == "3.3"
    assert specs["power_cons_cooling_kw"] == "0.656"
    assert specs["power_cons_heating_kw"] == "0.800"
    assert specs["inverter"] is True
