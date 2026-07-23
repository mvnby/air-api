import re
from typing import Any


KNOWN_PRODUCT_KINDS = {
    "unknown",
    "complete_split_system",
    "indoor_unit",
    "outdoor_unit",
    "panel",
    "accessory",
    "consumable",
    "other",
}

PRODUCT_KIND_BY_SYSTEM_TYPE = {
    "сплит-система": "complete_split_system",
    "внутренний блок": "indoor_unit",
    "наружный блок": "outdoor_unit",
    "мобильный": "other",
    "мульти-сплит-система": "other",
    "полупромышленный кондиционер": "other",
}


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes", "да", "есть", "в комплекте"}:
        return True
    if normalized in {"false", "0", "no", "нет", "не входит"}:
        return False
    return None


def _spec_value(values: dict[str, Any], key: str) -> Any:
    if values.get(key) is not None:
        return values[key]
    typed = values.get("__typed_specs")
    if not isinstance(typed, dict):
        return None
    entry = typed.get(key)
    if not isinstance(entry, dict):
        return None
    if entry.get("value") is not None:
        return entry["value"]
    return entry.get("raw")


def _kind_from_system_type(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace("ё", "е")
    normalized = normalized.replace("—", "-")
    normalized = re.sub(r"\s+", " ", normalized)
    return PRODUCT_KIND_BY_SYSTEM_TYPE.get(normalized)


class ProductKindService:
    @staticmethod
    def derive_from_specs(specs: dict[str, Any] | None) -> str:
        values = specs or {}
        system_type_kind = _kind_from_system_type(_spec_value(values, "type"))
        if system_type_kind is not None:
            return system_type_kind

        includes_indoor = _as_bool(_spec_value(values, "includes_indoor_unit"))
        includes_outdoor = _as_bool(_spec_value(values, "includes_outdoor_unit"))
        if includes_indoor is True and includes_outdoor is True:
            return "complete_split_system"
        if includes_indoor is True and includes_outdoor is False:
            return "indoor_unit"
        if includes_indoor is False and includes_outdoor is True:
            return "outdoor_unit"
        return "unknown"

    @staticmethod
    def normalize_explicit(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized not in KNOWN_PRODUCT_KINDS:
            raise ValueError("Неизвестный канонический тип товара.")
        return normalized

    @staticmethod
    def resolve(
        value: Any,
        *,
        specs: dict[str, Any] | None,
        fallback: str | None = None,
    ) -> str:
        explicit = ProductKindService.normalize_explicit(value)
        if explicit not in {None, "unknown"}:
            return explicit
        derived = ProductKindService.derive_from_specs(specs)
        if derived != "unknown":
            return derived
        if fallback in KNOWN_PRODUCT_KINDS:
            return str(fallback)
        return explicit or "unknown"
