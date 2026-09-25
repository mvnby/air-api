"""Approved installation grid stays exact across every tenant copy."""

from services.installation_grid_rollout import (
    _candidate_comparison, _validate_seed_against_installed_contract,
)
from services.installation_grid_seed import canonical_installation_grid


def _by_code():
    return {row.code: row for row in canonical_installation_grid()}


def test_seed_passes_published_book_contract():
    _validate_seed_against_installed_contract()


def test_grid_has_distinct_standard_and_prelaid_prices_without_phantom_route():
    rows = _by_code()
    assert len(rows) == 20
    assert len({row.code for row in rows.values()}) == 20
    expected = {
        "wall.small": (600, 300, 3, 50),
        "wall.middle": (750, 450, 3, 65),
        "wall.large": (960, 576, 3, 85),
        "console.small": (600, 300, 3, 50),
        "console.middle": (750, 450, 3, 65),
        "cassette": (1500, 900, 5, 85),
        "duct": (1500, 900, 5, 85),
        "floor_ceiling": (1500, 900, 5, 85),
        "column": (1500, 900, 5, 85),
        "multi": (500, 300, 3, 50),
    }
    for key, (standard_price, prelaid_price, route, extra_price) in expected.items():
        standard = rows[f"installation.{key}.standard.v20260925"]
        prelaid = rows[f"installation.{key}.prelaid_route.v20260925"]
        assert (standard.base_price, prelaid.base_price) == (standard_price, prelaid_price)
        assert standard.included_route_meters == route
        assert prelaid.included_route_meters == 0
        assert standard.included_holes == {"shared_pass_through": 1}
        assert prelaid.included_holes == {}
        assert next(rule.price for rule in standard.rules if rule.code == "route.extra_m") == extra_price
        assert all(rule.code != "route.extra_m" for rule in prelaid.rules)
        assert [(rule.code, rule.price) for rule in standard.rules if rule.code.startswith("hole.")] == [
            ("hole.through_thin.extra", 30), ("hole.through_thick.extra", 70),
        ]
        assert [(rule.code, rule.price) for rule in standard.rules if rule.code == "pump.package"] == [
            ("pump.package", 280),
        ]


def test_power_boundaries_and_unknown_large_console_fail_closed():
    rows = _by_code()
    small = rows["installation.wall.small.standard.v20260925"].match
    middle = rows["installation.wall.middle.standard.v20260925"].match
    large = rows["installation.wall.large.standard.v20260925"].match
    assert small["capacity_max_kw"] == "4.2" and small["capacity_max_inclusive"] is True
    assert middle["capacity_min_kw"] == "4.2" and middle["capacity_min_inclusive"] is False
    assert middle["capacity_max_kw"] == "8.0" and middle["capacity_max_inclusive"] is False
    assert large["capacity_min_kw"] == "8.0" and large["capacity_min_inclusive"] is True
    assert large["capacity_max_kw"] == "10.55" and large["capacity_max_inclusive"] is True
    assert not any("console.large" in code for code in rows)
    assert rows["installation.multi.standard.v20260925"].match["indoor_type"] is None
    assert rows["installation.multi.standard.v20260925"].match["product_kind"] == "multi_split_system"


def test_legacy_price_comparison_exposes_boundary_mismatch_instead_of_guessing():
    small = _candidate_comparison(category="Wall", power_range="07,09,12",
                                  old_base_price=500, old_extra_meter_price=40)
    assert small["new_candidates"] == [{
        "new_code": "installation.wall.small.standard.v20260925",
        "new_base_price": 600, "new_included_route_meters": 3,
        "new_extra_meter_price": 50,
    }]
    assert "not_equivalent" in small["coverage_status"]
    crossing = _candidate_comparison(category="Wall", power_range="18,24",
                                     old_base_price=700, old_extra_meter_price=60)
    assert crossing["new_candidates"] == []
    assert crossing["coverage_status"] == "unmapped_or_ambiguous_requires_review"
    too_large = _candidate_comparison(category="Wall", power_range="30,36",
                                      old_base_price=900, old_extra_meter_price=80)
    assert too_large["new_candidates"] == []
    ceiling = _candidate_comparison(category="Ceiling", power_range="All",
                                    old_base_price=1400, old_extra_meter_price=60)
    assert ceiling["new_candidates"][0]["new_base_price"] == 1500
    assert ceiling["new_candidates"][0]["new_extra_meter_price"] == 85
