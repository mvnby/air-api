import pytest

from models import InstallationRate, Product, Tag
from services.installation_pricing_service import InstallationPricingService


def _product(
    *,
    product_kind: str = "complete_split_system",
    system_type: str = "сплит-система",
    indoor_type: str | None = None,
    capacity_kw: float | None = None,
    area_m2: float | None = None,
    power_cooling: float | None = None,
    tag_slugs: tuple[str, ...] = (),
    title: str = "Installation matcher product",
) -> Product:
    specs = {"type": system_type}
    if indoor_type is not None:
        specs["indoor_type"] = indoor_type
    if capacity_kw is not None:
        specs["capacity_cooling_kw"] = capacity_kw
    if area_m2 is not None:
        specs["area_m2"] = area_m2
    product = Product(
        title=title,
        slug="installation-matcher-product",
        price=2000,
        product_kind=product_kind,
        power_cooling=power_cooling,
        specs=specs,
    )
    for index, slug in enumerate(tag_slugs):
        product.tags.append(Tag(title=f"Tag {index}", slug=slug))
    return product


def _rate(
    category: str,
    power_range: str = "All",
    *,
    is_fixed: bool = True,
) -> InstallationRate:
    return InstallationRate(
        category=category,
        power_range=power_range,
        base_price=1000,
        extra_pipe_price=50,
        included_pipe_meters=3,
        is_fixed=is_fixed,
    )


def test_floor_ceiling_specs_without_type_tag_never_fall_back_to_wall():
    product = _product(
        product_kind="other",
        system_type="полупромышленный кондиционер",
        indoor_type="напольно-потолочный",
        capacity_kw=10.5,
    )

    match = InstallationPricingService.resolve_product_rate(
        product,
        [_rate("Wall", "30-36")],
    )

    assert match.profile.equipment_category == "ceiling"
    assert match.rate is None
    assert match.reason == "no_matching_rate"


def test_floor_ceiling_specs_choose_exact_ceiling_before_combined_rate():
    product = _product(
        product_kind="other",
        system_type="полупромышленный кондиционер",
        indoor_type="напольно-потолочный",
        capacity_kw=10.5,
    )
    combined = _rate("Cassette/Ceiling", is_fixed=False)
    ceiling = _rate("Ceiling", "30-36")

    match = InstallationPricingService.resolve_product_rate(
        product, [combined, ceiling]
    )

    assert match.rate is ceiling
    assert match.reason is None


@pytest.mark.parametrize(
    ("indoor_type", "inapplicable_category"),
    [
        ("кассетный", "Ceiling"),
        ("напольно-потолочный", "Cassette"),
    ],
)
def test_cassette_and_ceiling_exact_rates_are_not_interchangeable(
    indoor_type,
    inapplicable_category,
):
    product = _product(indoor_type=indoor_type)

    match = InstallationPricingService.resolve_product_rate(
        product,
        [_rate(inapplicable_category)],
    )

    assert match.rate is None
    assert match.reason == "no_matching_rate"


def test_legacy_combined_non_fixed_rate_remains_manual_quote_candidate():
    product = _product(indoor_type="кассетный")
    combined = _rate("Cassette/Ceiling", is_fixed=False)

    match = InstallationPricingService.resolve_product_rate(product, [combined])

    assert match.rate is combined
    assert match.reason == "rate_requires_manual_quote"


@pytest.mark.parametrize("indoor_type", ["кассетный", "напольно-потолочный"])
def test_legacy_combined_fixed_rate_is_not_an_exact_total(indoor_type):
    product = _product(indoor_type=indoor_type)

    match = InstallationPricingService.resolve_product_rate(
        product,
        [_rate("Cassette/Ceiling", is_fixed=True)],
    )

    assert match.rate is None
    assert match.reason == "no_matching_rate"


@pytest.mark.parametrize("product_kind", ["indoor_unit", "outdoor_unit"])
def test_separate_blocks_never_receive_complete_system_installation(product_kind):
    product = _product(
        product_kind=product_kind,
        indoor_type="канальный",
        tag_slugs=("duct",),
    )

    match = InstallationPricingService.resolve_product_rate(
        product,
        [_rate("Duct")],
    )

    assert match.rate is None
    assert match.reason == "ineligible_product_kind"


def test_unknown_product_does_not_use_title_or_wall_tag_as_eligibility_fallback():
    product = _product(
        product_kind="unknown",
        system_type="",
        tag_slugs=("wall",),
        title="Настенная сплит-система 12",
    )

    match = InstallationPricingService.resolve_product_rate(
        product,
        [_rate("Wall", "07-12")],
    )

    assert match.rate is None
    assert match.reason == "ineligible_product_kind"


def test_wall_complete_system_uses_canonical_capacity():
    product = _product(indoor_type="настенный", capacity_kw=5.3)
    small = _rate("Wall", "07-12")
    medium = _rate("Wall", "18-24")

    assert (
        InstallationPricingService.match_product_rate(product, [small, medium])
        is medium
    )


def test_wall_exact_power_tag_has_priority_over_numeric_capacity():
    product = _product(
        indoor_type="настенный",
        capacity_kw=5.3,
        tag_slugs=("area-35",),
    )
    small = _rate("Wall", "area-20, area-25, area-35")
    medium = _rate("Wall", "area-50, area-70")

    assert (
        InstallationPricingService.match_product_rate(product, [medium, small]) is small
    )


def test_wall_uses_product_power_as_compatibility_fallback():
    product = _product(indoor_type="настенный", power_cooling=3.5)
    expected = _rate("Wall", "07-12")

    assert (
        InstallationPricingService.match_product_rate(product, [expected]) is expected
    )


def test_wall_without_capacity_requires_manual_quote():
    product = _product(indoor_type="настенный", area_m2=35)

    match = InstallationPricingService.resolve_product_rate(
        product,
        [_rate("Wall", "07-12")],
    )

    assert match.rate is None
    assert match.reason == "missing_cooling_capacity"


@pytest.mark.parametrize("area_m2", [20, 111])
def test_area_does_not_affect_wall_rate_selection(area_m2):
    product = _product(
        indoor_type="настенный",
        capacity_kw=3.5,
        area_m2=area_m2,
    )
    expected = _rate("Wall", "07-12")
    larger = _rate("Wall", "18-24")

    assert (
        InstallationPricingService.match_product_rate(product, [expected, larger])
        is expected
    )


def test_capacity_above_covered_ranges_does_not_use_last_wall_rate():
    product = _product(indoor_type="настенный", capacity_kw=14.0, area_m2=111)
    rates = [
        _rate("Wall", "07-12"),
        _rate("Wall", "18-24"),
        _rate("Wall", "30-36"),
    ]

    match = InstallationPricingService.resolve_product_rate(product, rates)

    assert match.rate is None
    assert match.reason == "no_matching_rate"
