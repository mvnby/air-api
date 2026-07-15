from __future__ import annotations

import pytest

from scripts.ha.calculate_logical_restore_resources import (
    GIB,
    MIB,
    ResourceSizingError,
    calculate_resources,
)


def test_current_database_uses_a_small_bounded_primary_share():
    resources = calculate_resources(
        sql_bytes=20 * MIB,
        live_database_bytes=62 * MIB,
        host_total_bytes=3900 * MIB,
    )

    assert resources.data_tmpfs_bytes == 512 * MIB
    assert resources.container_memory_bytes == 768 * MIB
    assert resources.host_reserve_bytes == GIB
    assert resources.required_available_bytes == 1792 * MIB
    assert resources.primary_container_limit_bytes == 975 * MIB


def test_sizing_rounds_up_from_the_larger_live_database():
    resources = calculate_resources(
        sql_bytes=700 * MIB,
        live_database_bytes=900 * MIB,
        host_total_bytes=16 * GIB,
    )

    assert resources.data_tmpfs_bytes == 2112 * MIB
    assert resources.container_memory_bytes == 2368 * MIB
    assert resources.host_reserve_bytes == 4 * GIB
    assert resources.required_available_bytes == 6464 * MIB
    assert resources.primary_container_limit_bytes == 4 * GIB


@pytest.mark.parametrize(
    ("sql_bytes", "live_database_bytes", "host_total_bytes"),
    (
        (0, 1, 1),
        (1, 0, 1),
        (1, 1, 0),
        (-1, 1, 1),
        (True, 1, 1),
    ),
)
def test_sizing_rejects_invalid_inputs(
    sql_bytes: int, live_database_bytes: int, host_total_bytes: int
):
    with pytest.raises(ResourceSizingError):
        calculate_resources(
            sql_bytes=sql_bytes,
            live_database_bytes=live_database_bytes,
            host_total_bytes=host_total_bytes,
        )


def test_absolute_sql_cap_remains_independent_from_runtime_sizing():
    with pytest.raises(ResourceSizingError, match="anti-bomb"):
        calculate_resources(
            sql_bytes=8 * GIB + 1,
            live_database_bytes=62 * MIB,
            host_total_bytes=64 * GIB,
        )


def test_large_restore_is_routed_away_from_the_primary():
    with pytest.raises(ResourceSizingError, match="dedicated restore host"):
        calculate_resources(
            sql_bytes=2 * GIB,
            live_database_bytes=2 * GIB,
            host_total_bytes=16 * GIB,
        )


def test_tiny_host_cannot_preserve_the_minimum_reserve():
    with pytest.raises(ResourceSizingError, match="primary-host memory share"):
        calculate_resources(
            sql_bytes=20 * MIB,
            live_database_bytes=62 * MIB,
            host_total_bytes=2 * GIB,
        )
