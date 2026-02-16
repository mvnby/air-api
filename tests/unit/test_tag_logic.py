from services.tag_logic import get_auto_tags


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
