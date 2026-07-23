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


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes", "да", "есть", "в комплекте"}:
        return True
    if normalized in {"false", "0", "no", "нет", "не входит"}:
        return False
    return None


class ProductKindService:
    @staticmethod
    def derive_from_specs(specs: dict[str, Any] | None) -> str:
        values = specs or {}
        includes_indoor = _as_bool(values.get("includes_indoor_unit"))
        includes_outdoor = _as_bool(values.get("includes_outdoor_unit"))
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
