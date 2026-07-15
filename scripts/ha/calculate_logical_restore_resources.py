#!/usr/bin/env python3
"""Calculate a bounded resource envelope for a logical PostgreSQL restore."""

from __future__ import annotations

import argparse
from dataclasses import dataclass


MIB = 1024**2
GIB = 1024**3

MAX_SQL_BYTES = 8 * GIB
MAX_DATA_TMPFS_BYTES = 10 * GIB
MAX_CONTAINER_MEMORY_BYTES = 12 * GIB
MAX_PRIMARY_CONTAINER_MEMORY_BYTES = 4 * GIB
PRIMARY_MEMORY_SHARE_DENOMINATOR = 4

DATA_TMPFS_FLOOR_BYTES = 512 * MIB
DATA_GROWTH_MULTIPLIER = 2
WAL_AND_INDEX_ALLOWANCE_BYTES = 256 * MIB
PROCESS_MEMORY_ALLOWANCE_BYTES = 256 * MIB
HOST_RESERVE_FLOOR_BYTES = 1 * GIB
ROUNDING_BYTES = 64 * MIB


class ResourceSizingError(ValueError):
    """Raised when the restore cannot fit the reviewed primary-host envelope."""


@dataclass(frozen=True)
class RestoreResources:
    data_tmpfs_bytes: int
    container_memory_bytes: int
    host_reserve_bytes: int
    required_available_bytes: int
    primary_container_limit_bytes: int


def _round_up(value: int, quantum: int = ROUNDING_BYTES) -> int:
    return ((value + quantum - 1) // quantum) * quantum


def calculate_resources(
    *, sql_bytes: int, live_database_bytes: int, host_total_bytes: int
) -> RestoreResources:
    for name, value in (
        ("sql_bytes", sql_bytes),
        ("live_database_bytes", live_database_bytes),
        ("host_total_bytes", host_total_bytes),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ResourceSizingError(f"{name} must be a positive integer")

    if sql_bytes > MAX_SQL_BYTES:
        raise ResourceSizingError("expanded SQL exceeds the absolute anti-bomb limit")

    base_bytes = max(sql_bytes, live_database_bytes)
    data_tmpfs_bytes = _round_up(
        max(
            DATA_TMPFS_FLOOR_BYTES,
            DATA_GROWTH_MULTIPLIER * base_bytes + WAL_AND_INDEX_ALLOWANCE_BYTES,
        )
    )
    container_memory_bytes = data_tmpfs_bytes + PROCESS_MEMORY_ALLOWANCE_BYTES
    host_reserve_bytes = max(
        HOST_RESERVE_FLOOR_BYTES,
        host_total_bytes // PRIMARY_MEMORY_SHARE_DENOMINATOR,
    )
    primary_container_limit_bytes = min(
        MAX_PRIMARY_CONTAINER_MEMORY_BYTES,
        host_total_bytes // PRIMARY_MEMORY_SHARE_DENOMINATOR,
    )

    if data_tmpfs_bytes > MAX_DATA_TMPFS_BYTES:
        raise ResourceSizingError("derived data tmpfs exceeds the absolute reviewed limit")
    if container_memory_bytes > MAX_CONTAINER_MEMORY_BYTES:
        raise ResourceSizingError("derived container memory exceeds the absolute reviewed limit")
    if container_memory_bytes > primary_container_limit_bytes:
        raise ResourceSizingError(
            "logical restore exceeds the reviewed primary-host memory share; "
            "use a dedicated restore host"
        )

    required_available_bytes = container_memory_bytes + host_reserve_bytes
    if required_available_bytes > host_total_bytes:
        raise ResourceSizingError(
            "logical restore cannot preserve the reviewed host memory reserve"
        )

    return RestoreResources(
        data_tmpfs_bytes=data_tmpfs_bytes,
        container_memory_bytes=container_memory_bytes,
        host_reserve_bytes=host_reserve_bytes,
        required_available_bytes=required_available_bytes,
        primary_container_limit_bytes=primary_container_limit_bytes,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql-bytes", type=int, required=True)
    parser.add_argument("--live-database-bytes", type=int, required=True)
    parser.add_argument("--host-total-bytes", type=int, required=True)
    args = parser.parse_args()

    try:
        resources = calculate_resources(
            sql_bytes=args.sql_bytes,
            live_database_bytes=args.live_database_bytes,
            host_total_bytes=args.host_total_bytes,
        )
    except ResourceSizingError as exc:
        parser.error(str(exc))

    print(
        resources.data_tmpfs_bytes,
        resources.container_memory_bytes,
        resources.host_reserve_bytes,
        resources.required_available_bytes,
        resources.primary_container_limit_bytes,
        sep="\t",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
