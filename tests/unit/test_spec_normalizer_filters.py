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


def test_wifi_option_value_maps_to_ready():
    specs = normalize_specs({"Wi-Fi": "Опция"})

    assert specs["wifi_ready"] == "ready"
    assert specs["__filter_wifi"] is True
    assert specs["__filter_wifi_builtin"] is False


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
    assert specs["capacity_heating_kw"] == "3.3"
    assert specs["power_cons_cooling_kw"] == "0.656"
    assert specs["power_cons_heating_kw"] == "0.800"
    assert specs["inverter"] is True


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
