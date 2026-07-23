from __future__ import annotations

from typing import Any

from models import Product
from services.product_response_mapper import resolve_public_stock_state


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _wifi_state(specs: dict[str, Any]) -> str | None:
    direct = specs.get("wifi_state")
    if direct is not None:
        return str(direct).strip().lower()
    typed = specs.get("__typed_specs") or {}
    value = (typed.get("wifi_state") or {}).get("value")
    return str(value).strip().lower() if value is not None else None


def _feature_ids(product: Product) -> set[int]:
    return {
        int(feature.id)
        for feature in product.__dict__.get("_resolved_features", [])
        if getattr(feature, "id", None) is not None
    }


class ProductCollectionRuleMatcher:
    @staticmethod
    def matches(
        product: Product,
        *,
        rule_config: dict[str, Any],
        supply_metrics: dict[str, Any],
    ) -> bool:
        specs = product.specs or {}
        product_kinds = set(rule_config.get("product_kinds") or [])
        if product_kinds and product.product_kind not in product_kinds:
            return False

        price = int(product.price or 0)
        if rule_config.get("min_price") is not None and price < int(rule_config["min_price"]):
            return False
        if rule_config.get("max_price") is not None and price > int(rule_config["max_price"]):
            return False

        area = _as_number(specs.get("area_m2"))
        if rule_config.get("min_area_m2") is not None and (
            area is None or area < float(rule_config["min_area_m2"])
        ):
            return False
        if rule_config.get("max_area_m2") is not None and (
            area is None or area > float(rule_config["max_area_m2"])
        ):
            return False

        noise = _as_number(specs.get("__filter_noise_min"))
        if rule_config.get("max_noise_min_db") is not None and (
            noise is None or noise > float(rule_config["max_noise_min_db"])
        ):
            return False

        heating_min = _as_number(specs.get("__filter_min_heat"))
        if rule_config.get("max_heating_min_c") is not None and (
            heating_min is None
            or heating_min > float(rule_config["max_heating_min_c"])
        ):
            return False

        if (
            rule_config.get("is_inverter") is not None
            and product.is_inverter != bool(rule_config["is_inverter"])
        ):
            return False

        wifi_states = set(rule_config.get("wifi_states") or [])
        if wifi_states and _wifi_state(specs) not in wifi_states:
            return False

        brand_ids = {int(value) for value in rule_config.get("brand_ids") or []}
        if brand_ids and int(product.brand_id or 0) not in brand_ids:
            return False

        series_ids = {int(value) for value in rule_config.get("series_ids") or []}
        if series_ids and int(product.series_id or 0) not in series_ids:
            return False

        colors = {str(value).strip().casefold() for value in rule_config.get("colors") or []}
        if colors and str(specs.get("color") or "").strip().casefold() not in colors:
            return False

        feature_ids = {int(value) for value in rule_config.get("feature_ids") or []}
        if feature_ids and not feature_ids.issubset(_feature_ids(product)):
            return False

        public_stock_states = set(rule_config.get("public_stock_states") or [])
        stock_state, _, _ = resolve_public_stock_state(
            supply_metrics.get("availability_status")
        )
        return not public_stock_states or stock_state in public_stock_states
