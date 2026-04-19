from services.tag_logic import (
    detect_category_slug,
    extract_brand_name,
    extract_brand_slug,
    get_auto_tags,
)


def test_get_auto_tags_skips_legacy_area_and_compressor_tags():
    tags = get_auto_tags(
        {"power_cooling": 3.5, "is_inverter": True, "min_temp_heating": -20},
        {"Тип внутреннего блока": "настенный"},
    )

    assert "area-35" not in tags
    assert "inverter" not in tags
    assert "on-off" not in tags
    assert "winter-20" in tags
    assert "wall" in tags
    assert "cat-household" in tags


def test_get_auto_tags_extracts_multi_and_brand():
    tags = get_auto_tags(
        {"power_cooling": 5.2},
        {
            "Тип кондиционера": "мульти-сплит система",
            "Бренд": "TCL",
        },
        title="Кондиционер TCL TAC-12",
    )

    assert "cat-multi" in tags
    assert "tcl" in tags


def test_detect_category_slug_for_semi_industrial():
    slug = detect_category_slug(
        metrics={},
        specs={"Тип внутреннего блока": "кассетный"},
        title="MDV кассетная сплит-система",
    )
    assert slug == "cat-industrial"


def test_detect_category_slug_for_universal_block_marker():
    slug = detect_category_slug(
        metrics={},
        specs={"Тип внутреннего блока": "универсальный"},
        title="Haier AC Universal",
    )
    assert slug == "cat-industrial"


def test_detect_category_slug_for_multi_inner_block():
    slug = detect_category_slug(
        metrics={},
        specs={"Тип": "внутренний блок", "indoor_type": "настенный"},
        title="Внутренний блок TCL BreezeIN 1.0",
    )
    assert slug == "cat-multi"


def test_extract_brand_slug_falls_back_to_title_first_brand_word():
    slug = extract_brand_slug(
        specs={"Тип кондиционера": "сплит-система"},
        title="Haier Coral DC-Inverter",
    )
    assert slug == "haier"


def test_extract_brand_name_skips_category_like_tokens():
    name = extract_brand_name(
        specs={"Тип кондиционера": "мульти-сплит система"},
        title="Мульти-сплит-система TCL Free Match",
    )
    assert name == "TCL"


def test_extract_brand_slug_rejects_invalid_service_tokens():
    slug = extract_brand_slug(
        specs={"Бренд": "Мульти-сплит-система"},
        title="Мульти-сплит-система внутренний блок",
    )
    assert slug is None
