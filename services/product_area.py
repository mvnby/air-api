"""Canonical product-area access backed by ``specs.area_m2``."""

from __future__ import annotations

import re
from typing import Any, Mapping


CANONICAL_AREA_KEY = "area_m2"
LEGACY_AREA_KEYS = ("recommended_area_m2",)


def parse_area_m2(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        matches = re.findall(r"\d+(?:[.,]\d+)?", str(value))
        if not matches:
            return None
        number = max(float(item.replace(",", ".")) for item in matches)
    return number if number > 0 else None


def area_from_specs(specs: Mapping[str, Any] | None) -> float | None:
    if not isinstance(specs, Mapping):
        return None
    return parse_area_m2(specs.get(CANONICAL_AREA_KEY))


def canonicalize_area_specs(
    specs: Mapping[str, Any] | None,
    *,
    fallback_area: Any = None,
) -> dict[str, Any]:
    result = dict(specs or {})
    canonical = parse_area_m2(result.get(CANONICAL_AREA_KEY))
    if canonical is None:
        for key in LEGACY_AREA_KEYS:
            canonical = parse_area_m2(result.get(key))
            if canonical is not None:
                break
    if canonical is None:
        canonical = parse_area_m2(fallback_area)

    for key in LEGACY_AREA_KEYS:
        result.pop(key, None)
    if canonical is not None:
        result[CANONICAL_AREA_KEY] = _compact_number(canonical)
    else:
        result.pop(CANONICAL_AREA_KEY, None)
    return result


def _compact_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value
