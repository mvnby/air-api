"""Shared cooling-capacity helpers used by tariff matching and presentation."""

from __future__ import annotations

import re

from models.product_constants import BTU_MAPPING


BTU_TO_KW_MAP = {
    7: 2.1,
    9: 2.6,
    12: 3.5,
    18: 5.3,
    24: 7.0,
    30: 8.8,
    36: 10.5,
    42: 12.3,
    48: 14.0,
    60: 17.6,
}

LEGACY_AREA_TAG_TO_BTU_CLASS = {
    "area-20": 7,
    "area-25": 9,
    "area-35": 12,
    "area-50": 18,
    "area-70": 24,
    "area-80": 30,
    "area-100": 36,
}


def _btu_power_bounds(btu_class: int) -> tuple[float, float] | None:
    mapping = BTU_MAPPING.get(str(btu_class)) or BTU_MAPPING.get(f"{btu_class:02d}")
    if mapping is not None:
        lower, upper = mapping["power"]
        return float(lower), float(upper)
    nominal = BTU_TO_KW_MAP.get(btu_class)
    if nominal is None:
        return None
    return nominal, nominal


def power_range_capacity_bounds(power_range: str) -> tuple[float, float] | None:
    """Return covered kW bounds for legacy BTU/area-tag tariff selectors."""

    normalized = str(power_range or "").strip().lower()
    if not normalized or normalized == "all":
        return None

    if "kw" in normalized or "квт" in normalized:
        numbers = [
            float(token.replace(",", "."))
            for token in re.findall(r"\d+(?:[.,]\d+)?", normalized)
        ]
        if not numbers:
            return None
        if len(numbers) == 1 and any(
            marker in normalized for marker in ("до", "up to", "<=")
        ):
            return 0.0, numbers[0]
        return min(numbers), max(numbers)

    area_tags = re.findall(r"area-\d+", normalized)
    if area_tags:
        btu_classes = [
            LEGACY_AREA_TAG_TO_BTU_CLASS[tag]
            for tag in area_tags
            if tag in LEGACY_AREA_TAG_TO_BTU_CLASS
        ]
    else:
        btu_classes = [
            int(token)
            for token in re.findall(r"(?<![\d.])\d{1,2}(?![\d.])", normalized)
            if int(token) in BTU_TO_KW_MAP
        ]

    bounds = [
        bound for item in btu_classes if (bound := _btu_power_bounds(item)) is not None
    ]
    if not bounds:
        return None
    return min(bound[0] for bound in bounds), max(bound[1] for bound in bounds)
