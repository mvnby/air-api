import pytest

from models import Product, Tag
from services.installation_product_profile import build_installation_product_profile


@pytest.mark.parametrize(
    ("indoor_type", "expected_category"),
    [
        ("настенный", "wall"),
        ("кассетный", "cassette"),
        ("канальный", "duct"),
        ("напольно-потолочный", "ceiling"),
        ("потолочный", "ceiling"),
        ("floor_ceiling", "ceiling"),
        ("floor-ceiling", "ceiling"),
        ("колонный", "column"),
    ],
)
def test_profile_normalizes_canonical_equipment_types(indoor_type, expected_category):
    product = Product(
        title="Profile product",
        slug="profile-product",
        price=1000,
        product_kind="complete_split_system",
        specs={"type": "сплит-система", "indoor_type": indoor_type},
    )

    profile = build_installation_product_profile(product)

    assert profile.eligible is True
    assert profile.equipment_category == expected_category
    assert profile.reason is None


@pytest.mark.parametrize(
    "product_kind",
    ["indoor_unit", "outdoor_unit", "panel", "accessory", "consumable"],
)
def test_profile_rejects_ineligible_product_kinds_before_tags(product_kind):
    product = Product(
        title="Component",
        slug="component",
        price=1000,
        product_kind=product_kind,
        specs={"indoor_type": "канальный"},
    )
    product.tags.append(Tag(title="Канальный", slug="duct"))

    profile = build_installation_product_profile(product)

    assert profile.eligible is False
    assert profile.reason == "ineligible_product_kind"


def test_profile_allows_known_semi_industrial_complete_form_factor():
    product = Product(
        title="Semi-industrial",
        slug="semi-industrial",
        price=5000,
        specs={
            "type": "полупромышленный кондиционер",
            "indoor_type": "напольно-потолочный",
            "capacity_cooling_kw": "10,5 кВт",
        },
    )

    profile = build_installation_product_profile(product)

    assert profile.product_kind == "other"
    assert profile.eligible is True
    assert profile.equipment_category == "ceiling"
    assert profile.cooling_capacity_kw == 10.5


def test_profile_sends_multisplit_to_manual_quote_even_with_wall_indoor_type():
    product = Product(
        title="Multi",
        slug="multi",
        price=5000,
        specs={
            "type": "мульти-сплит-система",
            "indoor_type": "настенный",
            "capacity_cooling_kw": 5.3,
        },
    )

    profile = build_installation_product_profile(product)

    assert profile.product_kind == "other"
    assert profile.eligible is False
    assert profile.reason == "ineligible_product_kind"


def test_profile_uses_product_power_only_as_capacity_compatibility_fallback():
    product = Product(
        title="Legacy capacity",
        slug="legacy-capacity",
        price=1000,
        product_kind="complete_split_system",
        power_cooling=3.5,
        specs={"type": "сплит-система", "indoor_type": "настенный"},
    )

    profile = build_installation_product_profile(product)

    assert profile.cooling_capacity_kw == 3.5


def test_profile_does_not_hide_conflicting_canonical_types_with_tag_fallback():
    product = Product(
        title="Conflicting profile",
        slug="conflicting-profile",
        price=1000,
        product_kind="complete_split_system",
        specs={"type": "настенный", "indoor_type": "кассетный"},
    )
    product.tags.append(Tag(title="Настенный", slug="wall"))

    profile = build_installation_product_profile(product)

    assert profile.eligible is True
    assert profile.equipment_category is None
    assert profile.reason == "missing_equipment_type"
