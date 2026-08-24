import pytest

from services.cooling_capacity import power_range_capacity_bounds


@pytest.mark.parametrize(
    ("power_range", "expected"),
    [
        ("07-12", (2.0, 4.0)),
        ("18-24", (5.0, 8.0)),
        ("30-36", (8.8, 11.0)),
        ("area-20, area-25, area-35", (2.0, 4.0)),
        ("до 3,5 кВт", (0.0, 3.5)),
        ("All", None),
    ],
)
def test_power_range_capacity_bounds(power_range, expected):
    assert power_range_capacity_bounds(power_range) == expected
