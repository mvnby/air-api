"""Pure installation eligibility and equipment-profile resolution."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Mapping

from models import Product
from services.product_kind_service import ProductKindService


INELIGIBLE_PRODUCT_KINDS = {
    "indoor_unit",
    "outdoor_unit",
    "panel",
    "accessory",
    "consumable",
}

EQUIPMENT_CATEGORY_ALIASES = {
    "wall": "wall",
    "настенный": "wall",
    "cassette": "cassette",
    "кассетный": "cassette",
    "duct": "duct",
    "канальный": "duct",
    "ceiling": "ceiling",
    "потолочный": "ceiling",
    "напольно потолочный": "ceiling",
    "floor ceiling": "ceiling",
    "column": "column",
    "колонный": "column",
}

TYPE_TAG_CATEGORIES = {
    "wall": "wall",
    "cassette": "cassette",
    "duct": "duct",
    "ceiling": "ceiling",
    "floor-ceiling": "ceiling",
    "floor_ceiling": "ceiling",
    "column": "column",
}

SEMI_INDUSTRIAL_SYSTEM_TYPES = {
    "полупромышленный кондиционер",
}


@dataclass(frozen=True)
class InstallationProductProfile:
    product_kind: str
    equipment_category: str | None
    cooling_capacity_kw: float | None
    eligible: bool
    reason: str | None
    tag_slugs: frozenset[str]


def _normalize(value: Any) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"[_-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _spec_value(specs: Mapping[str, Any], key: str) -> Any:
    if specs.get(key) is not None:
        return specs[key]
    typed = specs.get("__typed_specs")
    if not isinstance(typed, Mapping):
        return None
    entry = typed.get(key)
    if not isinstance(entry, Mapping):
        return None
    if entry.get("value") is not None:
        return entry["value"]
    return entry.get("raw")


def _positive_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(value).strip())
    if match is None:
        return None
    try:
        parsed = float(match.group(0).replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def _equipment_category_from_specs(specs: Mapping[str, Any]) -> tuple[str | None, bool]:
    categories = {
        category
        for key in ("type", "indoor_type")
        if (
            category := EQUIPMENT_CATEGORY_ALIASES.get(
                _normalize(_spec_value(specs, key))
            )
        )
        is not None
    }
    if len(categories) > 1:
        return None, True
    return next(iter(categories), None), False


def _equipment_category_from_tags(tag_slugs: frozenset[str]) -> str | None:
    categories = {
        category
        for slug in tag_slugs
        if (category := TYPE_TAG_CATEGORIES.get(slug)) is not None
    }
    if len(categories) != 1:
        return None
    return next(iter(categories))


def build_installation_product_profile(product: Product) -> InstallationProductProfile:
    specs = product.specs if isinstance(product.specs, Mapping) else {}
    tag_slugs = frozenset(
        str(getattr(tag, "slug", "")).strip().lower()
        for tag in (getattr(product, "tags", None) or [])
        if str(getattr(tag, "slug", "")).strip()
    )

    try:
        product_kind = ProductKindService.resolve(
            product.product_kind, specs=dict(specs)
        )
    except ValueError:
        product_kind = "unknown"

    specs_category, conflicting_specs = _equipment_category_from_specs(specs)
    equipment_category = specs_category
    if equipment_category is None and not conflicting_specs:
        equipment_category = _equipment_category_from_tags(tag_slugs)

    capacity = _positive_float(_spec_value(specs, "capacity_cooling_kw"))
    if capacity is None:
        capacity = _positive_float(product.power_cooling)

    system_type = _normalize(_spec_value(specs, "type"))
    eligible = product_kind == "complete_split_system"
    if product_kind == "other" and system_type in SEMI_INDUSTRIAL_SYSTEM_TYPES:
        eligible = True

    if product_kind in INELIGIBLE_PRODUCT_KINDS or not eligible:
        return InstallationProductProfile(
            product_kind=product_kind,
            equipment_category=equipment_category,
            cooling_capacity_kw=capacity,
            eligible=False,
            reason="ineligible_product_kind",
            tag_slugs=tag_slugs,
        )
    if equipment_category is None:
        return InstallationProductProfile(
            product_kind=product_kind,
            equipment_category=None,
            cooling_capacity_kw=capacity,
            eligible=True,
            reason="missing_equipment_type",
            tag_slugs=tag_slugs,
        )
    return InstallationProductProfile(
        product_kind=product_kind,
        equipment_category=equipment_category,
        cooling_capacity_kw=capacity,
        eligible=True,
        reason=None,
        tag_slugs=tag_slugs,
    )
