from parsers.haierproff import HaierProffParser


def test_haierproff_infers_poluprom_and_universal_indoor_from_breadcrumbs():
    parts = [
        "Каталог",
        "Полупромышленные сплит-системы",
        "Super Match Plus",
        "AC105S2SH2FA / 1U105S2SS1FB",
    ]
    title = "Haier AC105S2SH2FA / 1U105S2SS1FB AC (Универсальные блоки) Super Match Plus"

    inferred = HaierProffParser._infer_type_specs_from_breadcrumb_and_title(
        title=title,
        breadcrumb_parts=parts,
    )

    assert inferred["Тип"] == "Полупромышленный кондиционер"
    assert inferred["Тип внутреннего блока"] == "Напольно-потолочный"


def test_haierproff_infers_household_for_wall_from_title_only():
    inferred = HaierProffParser._infer_type_specs_from_breadcrumb_and_title(
        title="Haier AS35S2SJ2FA Jade настенный блок",
        breadcrumb_parts=[],
    )

    assert inferred["Тип"] == "Сплит-система"
    assert inferred["Тип внутреннего блока"] == "Настенный"


def test_haierproff_detects_wifi_by_feature_title_and_icon():
    entries = [
        {"img": "/images/uploads/2023/04/12/resize_cache/46_1/44cdb19d3e20378d090e233fdcc44d44.png", "title": "", "desc": "", "text": ""},
        {"img": "", "title": "Управление Wi-Fi (Стандартно)", "desc": "", "text": "Управление Wi-Fi (Стандартно)"},
    ]

    assert HaierProffParser._feature_entries_indicate_wifi(entries) is True


def test_haierproff_wifi_fallback_is_option_for_non_outdoor():
    assert HaierProffParser._should_assume_wifi_option({"Тип": "Сплит-система"}) is True
    assert HaierProffParser._should_assume_wifi_option({"Тип": "Наружный блок"}) is False
