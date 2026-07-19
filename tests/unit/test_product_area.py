from services.product_area import (
    area_from_specs,
    canonicalize_area_specs,
    parse_area_m2,
)


def test_area_from_specs_uses_only_canonical_key() -> None:
    assert area_from_specs({"area_m2": "50"}) == 50
    assert area_from_specs({"recommended_area_m2": 70}) is None


def test_canonicalize_area_specs_collapses_legacy_alias() -> None:
    result = canonicalize_area_specs({"recommended_area_m2": "70", "brand": "TCL"})

    assert result == {"area_m2": 70, "brand": "TCL"}


def test_canonical_area_wins_over_legacy_values() -> None:
    result = canonicalize_area_specs(
        {"area_m2": "50", "recommended_area_m2": "35"},
        fallback_area=20,
    )

    assert result == {"area_m2": 50}


def test_decimal_area_is_preserved() -> None:
    assert parse_area_m2("20,5 м²") == 20.5
    assert canonicalize_area_specs({"area_m2": "20.5"})["area_m2"] == 20.5
