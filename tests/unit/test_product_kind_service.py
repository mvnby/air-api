from services.product_kind_service import ProductKindService


def test_product_kind_derives_only_from_explicit_component_flags():
    assert ProductKindService.derive_from_specs(
        {
            "includes_indoor_unit": True,
            "includes_outdoor_unit": "да",
        }
    ) == "complete_split_system"
    assert ProductKindService.derive_from_specs(
        {
            "includes_indoor_unit": "да",
            "includes_outdoor_unit": "нет",
        }
    ) == "indoor_unit"
    assert ProductKindService.derive_from_specs(
        {
            "includes_indoor_unit": False,
            "includes_outdoor_unit": True,
        }
    ) == "outdoor_unit"


def test_product_kind_derives_from_canonical_system_type():
    assert ProductKindService.derive_from_specs(
        {"type": "сплит-система"},
    ) == "complete_split_system"
    assert ProductKindService.derive_from_specs(
        {"type": "внутренний блок"},
    ) == "indoor_unit"
    assert ProductKindService.derive_from_specs(
        {"type": "наружный блок"},
    ) == "outdoor_unit"


def test_product_kind_requires_confirmed_components_for_semi_industrial_splits():
    assert ProductKindService.derive_from_specs(
        {
            "type": "мобильный",
            "includes_indoor_unit": True,
            "includes_outdoor_unit": False,
        },
    ) == "other"
    assert ProductKindService.derive_from_specs(
        {
            "type": "полупромышленный кондиционер",
            "includes_indoor_unit": True,
            "includes_outdoor_unit": True,
            "indoor_units_count": 1,
        },
    ) == "complete_split_system"
    assert ProductKindService.derive_from_specs(
        {"type": "полупромышленный кондиционер", "includes_indoor_unit": True},
    ) == "other"
    assert ProductKindService.derive_from_specs(
        {"type": "полупромышленный кондиционер", "includes_indoor_unit": True, "includes_outdoor_unit": True, "indoor_units_count": 2},
    ) == "other"
    assert ProductKindService.resolve(
        "other",
        specs={"type": "полупромышленный кондиционер", "includes_indoor_unit": True, "includes_outdoor_unit": True},
    ) == "other"


def test_product_kind_reads_confirmed_typed_component_flags():
    assert ProductKindService.derive_from_specs(
        {
            "__typed_specs": {
                "includes_indoor_unit": {"type": "boolean", "value": True},
                "includes_outdoor_unit": {"type": "boolean", "raw": "да"},
            }
        },
    ) == "complete_split_system"


def test_product_kind_does_not_guess_from_title_or_partial_data():
    assert ProductKindService.derive_from_specs(
        {
            "title": "Сплит-система",
            "includes_indoor_unit": True,
        }
    ) == "unknown"


def test_product_kind_resolve_prefers_confirmed_specs_over_unknown():
    assert ProductKindService.resolve(
        "unknown",
        specs={
            "includes_indoor_unit": True,
            "includes_outdoor_unit": True,
        },
    ) == "complete_split_system"


def test_product_kind_resolve_keeps_explicit_kind_and_uses_fallback():
    assert ProductKindService.resolve(
        "accessory",
        specs={
            "includes_indoor_unit": True,
            "includes_outdoor_unit": True,
        },
    ) == "accessory"
    assert ProductKindService.resolve(
        None,
        specs={},
        fallback="outdoor_unit",
    ) == "outdoor_unit"
