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
    assert specs["wifi_builtin"] is True
    assert specs["wifi_state"] == "builtin"
    assert specs["__filter_wifi"] is True
    assert specs["__filter_wifi_builtin"] is True


def test_dynamic_wifi_key_understands_english_yes_no_values():
    yes_specs = normalize_specs({"wifi": "yes"})
    no_specs = normalize_specs({"wi-fi": "no"})

    assert yes_specs["wifi_ready"] is True
    assert yes_specs["wifi_builtin"] is True
    assert yes_specs["wifi_state"] == "builtin"
    assert yes_specs["__filter_wifi"] is True

    assert no_specs["wifi_ready"] is False
    assert no_specs["wifi_builtin"] is False
    assert no_specs["wifi_state"] == "none"
    assert no_specs["__filter_wifi"] is False


def test_wifi_ready_false_does_not_override_wifi_module_true():
    specs = normalize_specs({"wifi_ready": False, "wifi_module": "true"})

    assert specs["wifi_ready"] is True
    assert specs["__filter_wifi"] is True


def test_dynamic_wifi_key_mapping_from_onliner_specs():
    specs = normalize_specs({"Wi-Fi модуль (опция)": "приобретается отдельно"})

    assert specs["wifi_ready"] == "ready"
    assert specs["wifi_builtin"] is False
    assert specs["wifi_state"] == "ready"
    assert specs["__filter_wifi"] is True
    assert specs["__filter_wifi_builtin"] is False


def test_wifi_option_value_maps_to_ready():
    specs = normalize_specs({"Wi-Fi": "Опция"})

    assert specs["wifi_ready"] == "ready"
    assert specs["wifi_builtin"] is False
    assert specs["wifi_state"] == "ready"
    assert specs["__filter_wifi"] is True
    assert specs["__filter_wifi_builtin"] is False


def test_explicit_wifi_ready_and_builtin_fields_can_represent_optional_module():
    specs = normalize_specs({"wifi_ready": True, "wifi_builtin": False})

    assert specs["wifi_ready"] == "ready"
    assert specs["wifi_builtin"] is False
    assert specs["wifi_state"] == "ready"
    assert specs["__filter_wifi"] is True
    assert specs["__filter_wifi_builtin"] is False


def test_wifi_state_can_drive_normalized_wifi_fields():
    builtin = normalize_specs({"wifi_state": "builtin"})
    assert builtin["wifi_ready"] is True
    assert builtin["wifi_builtin"] is True
    assert builtin["wifi_state"] == "builtin"

    ready = normalize_specs({"wifi_state": "ready"})
    assert ready["wifi_ready"] == "ready"
    assert ready["wifi_builtin"] is False
    assert ready["__filter_wifi"] is True
    assert ready["__filter_wifi_builtin"] is False


def test_severcon_keys_are_normalized_for_catalog_filters():
    specs = normalize_specs(
        {
            "Вайфай": "Опционально",
            "Тип управления компрессором": "Инверторный",
            "Серия": "BADEN",
            "Категория поставщика": "Energolux BADEN",
            "ID предложения Severcon": "123",
            "URL поставщика": "https://www.severcon.ru/catalog/item.html",
            "Модель внутреннего блока": "SAS09",
            "Модель наружного блока": "SAU09",
            "Гарантированный диапазон рабочих t° наружного воздуха, обогрев": "-15 ~ +24",
            "Размеры внутреннего блока без упаковки (Ш х В х Г)": "292x788x198",
        }
    )

    assert specs["wifi_ready"] == "ready"
    assert specs["__filter_wifi"] is True
    assert specs["series"] == "BADEN"
    assert specs["compressor_type_norm"] == "inverter"
    assert specs["model_indoor"] == "SAS09"
    assert specs["model_outdoor"] == "SAU09"
    assert specs["__filter_min_heat"] == -15
    assert specs["width_indoor"] == "788"
    assert specs["height_indoor"] == "292"
    assert specs["depth_indoor"] == "198"
    assert "Категория поставщика" not in specs
    assert "ID предложения Severcon" not in specs
    assert "URL поставщика" not in specs


def test_non_inverter_values_do_not_match_inverter_substring():
    by_value = normalize_specs({"Инверторный": "неинверторный"})
    assert by_value["inverter"] is False
    assert by_value["compressor_type_norm"] == "on_off"

    by_type = normalize_specs({"Тип управления компрессором": "Неинверторный"})
    assert by_type["compressor_type_norm"] == "on_off"


def test_severcon_wall_split_specs_are_normalized_with_source_quirks():
    specs = normalize_specs(
        {
            "Размеры внутреннего блока без упаковки (Ш х В х Г)": "283?690?199",
            "Размеры наружного блока без упаковки (Ш х В х Г)": "455?650?233",
            "Максимальный перепад высот": "5",
            "Потребляемая мощность, охлаждение": "0,83",
            "Потребляемая мощность, обогрев": "0,76",
            "Расход воздуха внутреннего блока": "400",
            "Расход воздуха наружного блока": "1430",
            "Уровень звукового давления внутреннего блока": "23/26/31/35",
            "Вес внутреннего блока без упаковки": "6,5",
            "Вес наружного блока без упаковки": "20,0",
            "Пульт управления в комплекте": "Да",
            "Цвет корпуса": "Белый",
            "Страна производства": "Китай",
            "Электропитание": "1 фаза, 220 ~ 240 В, 50 Гц",
            "Сторона подключения": "Внутренний блок",
            "Гарантия": "48",
            "Артикул": "SAS09B4-A/SAU09B4-A",
            "Осушение": "1,3",
            "EER (коэффициент / класс)": "3,23/А",
            "COP (коэффициент / класс)": "3,63/A",
        }
    )

    assert specs["width_indoor"] == "690"
    assert specs["height_indoor"] == "283"
    assert specs["depth_indoor"] == "199"
    assert specs["width_outdoor"] == "650"
    assert specs["height_outdoor"] == "455"
    assert specs["depth_outdoor"] == "233"
    assert specs["pipe_max_height"] == "5"
    assert "multi_max_height_diff" not in specs
    assert specs["power_cons_cooling_kw"] == "0.83"
    assert specs["power_cons_heating_kw"] == "0.76"
    assert specs["airflow_max"] == "400"
    assert specs["airflow_outdoor"] == "1430"
    assert specs["noise_indoor"] == "23/26/31/35"
    assert specs["__filter_noise_min"] == 23
    assert specs["weight_indoor"] == "6.5"
    assert specs["weight_outdoor"] == "20.0"
    assert specs["remote_control"] is True
    assert specs["color"] == "Белый"
    assert specs["country"] == "Китай"
    assert specs["power_supply"] == "1 фаза, 220 ~ 240 В, 50 Гц"
    assert specs["power_supply_location"] == "Внутренний блок"
    assert specs["warranty_months"] == "48"
    assert specs["sku"] == "SAS09B4-A/SAU09B4-A"
    assert specs["dehumidification_l_h"] == "1.3"
    assert "dehumidification" not in specs
    assert specs["eer"] == "3.23"
    assert specs["cop"] == "3.63"
    assert specs["energy_class_cooling"] == "A"
    assert specs["energy_class_heating"] == "A"


def test_severcon_wall_dimensions_handle_reversed_first_two_numbers():
    specs = normalize_specs(
        {
            "Размеры внутреннего блока без упаковки (Ш х В х Г)": "713?270?195",
            "Размеры наружного блока без упаковки (Ш х В х Г)": "710?450?293",
        }
    )

    assert specs["width_indoor"] == "713"
    assert specs["height_indoor"] == "270"
    assert specs["depth_indoor"] == "195"
    assert specs["width_outdoor"] == "710"
    assert specs["height_outdoor"] == "450"
    assert specs["depth_outdoor"] == "293"


def test_severcon_semi_industrial_extra_keys_are_normalized():
    specs = normalize_specs(
        {
            "Максимальный рабочий ток, охлаждение": "4,8",
            "Максимальный рабочий ток, обогрев": "5,6",
            "Диаметр дренажной трубы: мм (дюйм)": "25",
            "Размеры внутреннего блока в упаковке (Ш х В х Г)": "290х655x655",
            "Размеры наружного блока в упаковке (Ш х В х Г)": "615x915x370",
            "Вес внутреннего блока в упаковке": "17,8",
            "Вес наружного блока в упаковке": "34,9",
            "Зимний комплект": "Опционально",
            "Параметры питающей сети": "220-240",
            "Установка": "Горизонтальная",
        }
    )

    assert specs["current_cooling_max_a"] == "4.8"
    assert specs["current_heating_max_a"] == "5.6"
    assert specs["drain_pipe_diameter"] == "25"
    assert specs["dimensions_indoor_package_mm"] == "290 × 655 × 655"
    assert specs["dimensions_outdoor_package_mm"] == "615 × 915 × 370"
    assert specs["weight_indoor_package"] == "17.8"
    assert specs["weight_outdoor_package"] == "34.9"
    assert specs["winter_kit"] == "Опционально"
    assert specs["power_supply_voltage"] == "220-240"
    assert specs["installation_orientation"] == "Горизонтальная"


def test_registry_aliases_convert_watts_and_refrigerant_units():
    specs = normalize_specs(
        {
            "Охлаждение максимум, Вт": "3400",
            "Номинальная потребляемая мощность (охлаждение), Вт": "2030",
            "Заправка хладагента, кг": "0,51",
            "Заводская заправка хладагента R410a (до 5 м)": "1300 г",
        }
    )

    assert specs["capacity_cooling_max_kw"] == "3.4"
    assert specs["power_cons_cooling_kw"] == "2.03"
    assert specs["refrigerant_charge_g"] == "1300"


def test_registry_keeps_small_mislabeled_watt_values_as_kw():
    specs = normalize_specs({"Охлаждение максимум, Вт": "3,4"})

    assert specs["capacity_cooling_max_kw"] == "3.4"


def test_registry_maps_real_unmapped_catalog_keys():
    specs = normalize_specs(
        {
            "Габаритные размеры без упаковки (Ш/Г/В), мм": "975 × 220 × 320",
            "Внутренний блок: Расход воздуха (высокая скорость), м 3 /ч": "1000",
            "Наружный блок: Уровень звукового давления, дБ, А": "50",
            "Увлажнение воздуха": "нет",
            "Датчик присутствия": "да",
            "Компрессор: Инверторный компрессор": "Да",
        }
    )

    assert specs["width_indoor"] == "975"
    assert specs["depth_indoor"] == "220"
    assert specs["height_indoor"] == "320"
    assert specs["airflow_max"] == "1000"
    assert specs["noise_outdoor"] == "50"
    assert specs["humidification"] is False
    assert specs["presence_sensor"] is True
    assert specs["inverter"] is True


def test_registry_maps_temperature_and_energy_class_aliases():
    specs = normalize_specs(
        {
            "min_temp_cool": "-15",
            "min_temp_heat": "-25",
            "Класс энергоэффективности (охлаждение/нагрев)": "A++ / A+",
            "Энергоэффективность EER/COP": "3,21 / 3,61",
            "Максимальное количество подключаемых внутренних блоков": "4",
            "multi_max_height_diff": "10 м",
        }
    )

    assert specs["temp_range_cool"] == "-15"
    assert specs["temp_range_heat"] == "-25"
    assert specs["energy_class_cooling"] == "A++"
    assert specs["energy_class_heating"] == "A+"
    assert specs["eer"] == "3.21"
    assert specs["cop"] == "3.61"
    assert specs["multi_max_indoor_units"] == "4"
    assert specs["pipe_max_height"] == "10"


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
    assert cassette["indoor_type"] == "кассетный"
    assert cassette["__typed_specs"]["indoor_type"]["value"] == "cassette"

    duct = normalize_specs({"indoor_type": "Канальный"})
    assert duct["__filter_indoor_type"] == "duct"
    assert duct["indoor_type"] == "канальный"

    floor_ceiling = normalize_specs({"Тип внутреннего блока": "напольно-потолочный"})
    assert floor_ceiling["__filter_indoor_type"] == "floor_ceiling"
    assert floor_ceiling["indoor_type"] == "напольно-потолочный"

    universal = normalize_specs({"Тип внутреннего блока": "универсальный"})
    assert universal["__filter_indoor_type"] == "floor_ceiling"
    assert universal["type"] == "полупромышленный кондиционер"
    assert universal["indoor_type"] == "напольно-потолочный"


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
    assert specs["pipe_liquid"] == '1/4"'
    assert specs["pipe_gas"] == '3/8"'
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
    assert specs["capacity_cooling_min_kw"] == "0.89"
    assert specs["capacity_cooling_max_kw"] == "3.7"
    assert specs["capacity_heating_kw"] == "3.3"
    assert specs["capacity_heating_min_kw"] == "0.89"
    assert specs["capacity_heating_max_kw"] == "4.1"
    assert specs["power_cons_cooling_kw"] == "0.656"
    assert specs["power_cons_cooling_min_kw"] == "0.20"
    assert specs["power_cons_cooling_max_kw"] == "1.4"
    assert specs["power_cons_heating_kw"] == "0.800"
    assert specs["power_cons_heating_min_kw"] == "0.195"
    assert specs["power_cons_heating_max_kw"] == "1.6"
    assert specs["inverter"] is True

    typed = specs["__typed_specs"]
    assert typed["capacity_cooling_kw"]["value"] == 2.5
    assert typed["capacity_cooling_kw"]["nominal"] == 2.5
    assert typed["capacity_cooling_kw"]["min"] == 0.89
    assert typed["capacity_cooling_kw"]["max"] == 3.7
    assert typed["capacity_cooling_kw"]["unit"] == "kW"


def test_typed_specs_capture_ranges_lists_quantities_and_wifi_state():
    specs = normalize_specs(
        {
            "Рабочая температура при обогреве": "от -20 до +30 °C",
            "Уровень звукового давления внутреннего блока": "23/26/31/35",
            "Расход воздуха внутреннего блока": "400",
            "Заправка хладагента, кг": "0,51",
            "Wi-Fi": "Опция",
        }
    )

    typed = specs["__typed_specs"]

    assert typed["temp_range_heat"]["type"] == "range"
    assert typed["temp_range_heat"]["unit"] == "C"
    assert typed["temp_range_heat"]["min"] == -20
    assert typed["temp_range_heat"]["max"] == 30
    assert typed["temp_range_heat"]["values"] == [-20, 30]

    assert typed["noise_indoor"]["type"] == "number_list"
    assert typed["noise_indoor"]["unit"] == "dB"
    assert typed["noise_indoor"]["values"] == [23, 26, 31, 35]
    assert typed["noise_indoor"]["min"] == 23
    assert typed["noise_indoor"]["max"] == 35

    assert typed["airflow_max"]["type"] == "number_list"
    assert typed["airflow_max"]["unit"] == "m3/h"
    assert typed["airflow_max"]["values"] == [400]

    assert typed["refrigerant_charge_g"]["value"] == 510
    assert typed["refrigerant_charge_g"]["unit"] == "g"

    assert typed["wifi_state"]["type"] == "state"
    assert typed["wifi_state"]["value"] == "ready"
    assert typed["wifi_builtin"]["value"] is False


def test_haier_packaging_weight_and_import_rate_keys_are_normalized():
    specs = normalize_specs(
        {
            "Наружный блок: Габаритные размеры без упаковки (Ш/Г/В), мм": "898 × 355 × 643",
            "Габаритные размеры в упаковке (Ш/Г/В), мм": "940 × 390 × 697",
            "Чистый вес / Вес в упаковке, кг": "14,9 / 18,9",
            "Чистый вес / вес в упаковке, кг": "36,5 / 38,5",
            "Наличие": "В наличии",
            "Цена источника": "191700 RUB",
            "Курс RUB/BYN (импорт)": "0.0374",
        }
    )

    assert specs["width_outdoor"] == "898"
    assert specs["depth_outdoor"] == "355"
    assert specs["height_outdoor"] == "643"
    assert specs["dimensions_outdoor_package_mm"] == "940 × 390 × 697"
    assert specs["weight_indoor"] == "14.9"
    assert specs["weight_outdoor"] == "36.5"
    assert specs["availability"] == "В наличии"
    assert "source_price_rub" not in specs
    assert "source_fx_rub_byn" not in specs
    assert "Цена источника" not in specs
    assert "Курс RUB/BYN (импорт)" not in specs


def test_registry_unit_conversions_for_weight_and_warranty():
    specs = normalize_specs(
        {
            "Вес внутреннего блока, кг": "6500 г",
            "Вес наружного блока, кг": "32 кг",
            "Гарантия": "2 года",
        }
    )

    assert specs["weight_indoor"] == "6.5"
    assert specs["weight_outdoor"] == "32"
    assert specs["warranty_months"] == "24"

    typed = specs["__typed_specs"]
    assert typed["weight_indoor"]["value"] == 6.5
    assert typed["weight_indoor"]["unit"] == "kg"
    assert typed["weight_outdoor"]["value"] == 32
    assert typed["warranty_months"]["value"] == 24
    assert typed["warranty_months"]["unit"] == "month"


def test_registry_weight_conversion_does_not_reformat_plain_kg_values():
    specs = normalize_specs({"Вес наружного блока, кг": "20,0"})

    assert specs["weight_outdoor"] == "20.0"
    assert specs["__typed_specs"]["weight_outdoor"]["value"] == 20


def test_dynamic_temp_and_pipe_aliases_are_normalized():
    specs = normalize_specs(
        {
            "для работы в режиме охлаждения, ⁰C CТ": "-15 ~ 48",
            "Для работы в режиме нагрева , ⁰C ВТ": "-18 ~ 18",
            "Диаметр труб жидкого хладагента, мм": "6.35",
            "Диаметр труб газообразного хладагента, мм": "9.52",
        }
    )

    assert specs["temp_range_cool"] == "-15 ~ 48"
    assert specs["temp_range_heat"] == "-18 ~ 18"
    assert specs["pipe_liquid"] == '1/4"'
    assert specs["pipe_gas"] == '3/8"'


def test_type_canonicalization_marks_cassette_split_as_semi_industrial():
    specs = normalize_specs(
        {
            "Тип кондиционера": "4-поточная кассетная сплит-система",
            "Тип внутреннего блока": "кассетный",
        }
    )

    assert specs["type"] == "полупромышленный кондиционер"


def test_type_fallback_from_indoor_type_sets_semi_industrial():
    specs = normalize_specs(
        {
            "Тип внутреннего блока": "канальный",
        }
    )

    assert specs["type"] == "полупромышленный кондиционер"


def test_haier_grouped_indoor_outdoor_dimensions_are_split_correctly():
    specs = normalize_specs(
        {
            "Внутренний блок: Габаритные размеры без упаковки (Ш/Г/В), мм": "974 × 223 × 318",
            "Наружный блок: Габаритные размеры без упаковки (Ш/Г/В), мм": "875 × 355 × 642",
        }
    )

    assert specs["width_indoor"] == "974"
    assert specs["depth_indoor"] == "223"
    assert specs["height_indoor"] == "318"
    assert specs["width_outdoor"] == "875"
    assert specs["depth_outdoor"] == "355"
    assert specs["height_outdoor"] == "642"


def test_non_inverter_compressor_sets_inverter_false():
    specs = normalize_specs({"Неинверторный компрессор": "Да"})
    assert specs["inverter"] is False


def test_remote_control_model_implies_remote_control_true():
    specs = normalize_specs({"Пульт управления": "YR-HE"})
    assert specs["remote_control"] is True


def test_compressor_brand_is_canonicalized_for_select():
    specs = normalize_specs({"Производитель компрессора": "HIGHLY"})
    assert specs["compressor_brand"] == "Highly"


def test_eer_cop_pair_is_split_into_two_specs():
    specs = normalize_specs({"EER/COP": "3,21 / 3,61"})
    assert specs["eer"] == "3.21"
    assert specs["cop"] == "3.61"


def test_lg24_watt_scale_power_values_are_converted_to_kw():
    specs = normalize_specs(
        {
            "Потребление электроэнергии в режиме охлаждения (Мин / Ном / Макс), кВт": "210 / 2164 / 2500",
            "Потребление электроэнергии в режиме нагрева (Мин / Ном / Макс), кВт": "190 / 2027 / 2700",
        }
    )

    assert specs["power_cons_cooling_min_kw"] == "0.21"
    assert specs["power_cons_cooling_kw"] == "2.164"
    assert specs["power_cons_cooling_max_kw"] == "2.5"
    assert specs["power_cons_heating_min_kw"] == "0.19"
    assert specs["power_cons_heating_kw"] == "2.027"
    assert specs["power_cons_heating_max_kw"] == "2.7"
    assert specs["__typed_specs"]["power_cons_cooling_kw"]["value"] == 2.164


def test_lg24_current_nominal_max_pairs_are_split():
    specs = normalize_specs(
        {
            "Рабочий ток в режиме охлаждения (Ном / Макс), А": "4.7 / 6.0",
            "Рабочий ток в режиме нагрева (Ном/Макс), А": "4.7 / 7.0",
        }
    )

    assert specs["current_cooling_nominal_a"] == "4.7"
    assert specs["current_cooling_max_a"] == "6.0"
    assert specs["current_heating_nominal_a"] == "4.7"
    assert specs["current_heating_max_a"] == "7.0"


def test_lg24_commercial_dimensions_airflow_pipes_and_route_limits_are_normalized():
    specs = normalize_specs(
        {
            "Внутренний блок (Ш х В х Г) мм": "1 250 x 270 x 700",
            "Внешний блок (Ш х В х Г) мм": "950 x 834 x 330",
            "Расход воздуха Выс./Средн./Низ. , м³": "38.0 / 33.0 / 28.0",
            "Диаметр трубопровода, жидкость, внутренний блок, мм ( дюйм)": "6.35 (1/4)",
            "Диаметр трубопровода, газ, внутренний блок, мм ( дюйм)": "9.52 (3/8)",
            "Диаметр трубопровода, дренаж, внутренний блок, Нар. Ø / Внутр. Ø, мм": "32 / 25",
            "Длина трассы (Мин / Макс), м": "3 / 30",
            "Перепад высоты между блоками (Макс), м": "15",
        }
    )

    assert specs["width_indoor"] == "1250"
    assert specs["height_indoor"] == "270"
    assert specs["depth_indoor"] == "700"
    assert specs["width_outdoor"] == "950"
    assert specs["height_outdoor"] == "834"
    assert specs["depth_outdoor"] == "330"
    assert specs["airflow_max"] == "2280 / 1980 / 1680"
    assert specs["pipe_liquid"] == '1/4"'
    assert specs["pipe_gas"] == '3/8"'
    assert specs["drain_pipe_diameter"] == "32"
    assert specs["pipe_max_length"] == "30"
    assert specs["pipe_max_height"] == "15"
