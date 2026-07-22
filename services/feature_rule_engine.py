from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from models import FeatureRule


_MISSING = object()


def get_spec_value(specs: Mapping[str, Any], spec_key: str) -> Any:
    direct = specs.get(spec_key, _MISSING)
    if direct is not _MISSING:
        return direct

    current: Any = specs
    for part in spec_key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            current = _MISSING
            break
        current = current[part]
    if current is not _MISSING:
        return current

    typed = specs.get("__typed_specs")
    if isinstance(typed, Mapping):
        typed_value = typed.get(spec_key, _MISSING)
        if isinstance(typed_value, Mapping):
            if "value" in typed_value:
                return typed_value["value"]
            if "min" in typed_value and "max" not in typed_value:
                return typed_value["min"]
        if typed_value is not _MISSING:
            return typed_value
    return _MISSING


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _normalized(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().casefold()
    return value


def matches_rule(specs: Mapping[str, Any], rule: FeatureRule) -> bool:
    actual = get_spec_value(specs, rule.spec_key)
    exists = actual is not _MISSING and actual is not None and actual != ""
    if rule.operator == "exists":
        expected = True if rule.target_value is None else bool(rule.target_value)
        return exists is expected
    if not exists:
        return False

    target = rule.target_value
    if rule.operator == "eq":
        return _normalized(actual) == _normalized(target)
    if rule.operator == "neq":
        return _normalized(actual) != _normalized(target)
    if rule.operator in {"gt", "gte", "lt", "lte"}:
        left, right = _number(actual), _number(target)
        if left is None or right is None:
            return False
        return {
            "gt": left > right,
            "gte": left >= right,
            "lt": left < right,
            "lte": left <= right,
        }[rule.operator]
    if rule.operator == "in":
        return any(_normalized(actual) == _normalized(item) for item in (target or []))
    if rule.operator == "contains":
        if isinstance(actual, (list, tuple, set)):
            return any(_normalized(item) == _normalized(target) for item in actual)
        return str(target).casefold() in str(actual).casefold()
    return False


def matches_all_rules(specs: Mapping[str, Any], rules: list[FeatureRule]) -> bool:
    active = sorted((rule for rule in rules if rule.is_active), key=lambda item: (item.sort_order, item.id or 0))
    return bool(active) and all(matches_rule(specs, rule) for rule in active)


def describe_rules(rules: list[FeatureRule]) -> str | None:
    active = sorted((rule for rule in rules if rule.is_active), key=lambda item: (item.sort_order, item.id or 0))
    if not active:
        return None
    return " AND ".join(
        f"{rule.spec_key} {rule.operator} {rule.target_value!r}"
        for rule in active
    )
