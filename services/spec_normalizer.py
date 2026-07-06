import re
from typing import Any, Dict, List, Optional, Sequence

from services.spec_registry import (
    REGISTRY_DIMENSIONS_MAP,
    REGISTRY_KEY_MAP,
    REGISTRY_UNORDERED_DIMENSION_KEYS,
    build_typed_specs,
    normalize_registered_value,
)
from services.tag_logic import extract_brand_name, extract_brand_slug, is_invalid_brand_name

_TRIPLET_SPEC_KEYS = {
    "capacity_cooling_kw": ("capacity_cooling_min_kw", "capacity_cooling_max_kw"),
    "capacity_heating_kw": ("capacity_heating_min_kw", "capacity_heating_max_kw"),
    "power_cons_cooling_kw": ("power_cons_cooling_min_kw", "power_cons_cooling_max_kw"),
    "power_cons_heating_kw": ("power_cons_heating_min_kw", "power_cons_heating_max_kw"),
}

# Registry-backed alias projection. Keep the public KEY_MAP name for scripts/tests.
KEY_MAP: Dict[str, str] = dict(REGISTRY_KEY_MAP)

# Composite dimension keys: "940×1250×340" → split into width/height/depth.
_DIMENSIONS_MAP = dict(REGISTRY_DIMENSIONS_MAP)
_UNORDERED_WIDTH_HEIGHT_DIMENSION_KEYS = set(REGISTRY_UNORDERED_DIMENSION_KEYS)

_PREFERRED_NUMERIC_KEYS = {
    "capacity_cooling_kw",
    "capacity_heating_kw",
    "power_cons_cooling_kw",
    "power_cons_heating_kw",
    "power_cons_cooling_min_kw",
    "power_cons_cooling_max_kw",
    "power_cons_heating_min_kw",
    "power_cons_heating_max_kw",
    "area_m2",
    "weight_indoor",
    "weight_outdoor",
    "weight_indoor_package",
    "weight_outdoor_package",
    "dehumidification_l_h",
    "current_cooling_max_a",
    "current_heating_max_a",
    "current_cooling_nominal_a",
    "current_heating_nominal_a",
    "warranty_months",
    "drain_pipe_diameter",
    "pipe_max_length",
    "pipe_max_height",
    "multi_max_total_pipe_length",
}
_POWER_KW_KEYS = {
    "capacity_cooling_kw",
    "capacity_heating_kw",
    "capacity_cooling_min_kw",
    "capacity_cooling_max_kw",
    "capacity_heating_min_kw",
    "capacity_heating_max_kw",
    "power_cons_cooling_kw",
    "power_cons_heating_kw",
    "power_cons_cooling_min_kw",
    "power_cons_cooling_max_kw",
    "power_cons_heating_min_kw",
    "power_cons_heating_max_kw",
}
_MAX_FROM_RANGE_NUMERIC_KEYS = {
    "area_m2",
    "pipe_max_length",
    "pipe_max_height",
    "multi_max_total_pipe_length",
}

_DROPPED_SPEC_KEYS = {
    "source_price_rub",
    "source_fx_rub_byn",
    "Цена источника",
    "Курс RUB/BYN (импорт)",
    "Категория поставщика",
    "ID предложения Severcon",
    "URL поставщика",
}


def _split_dimensions(specs: Dict[str, Any]) -> Dict[str, Any]:
    """Split composite dimension values like '940×1250×340' into
    individual width/height/depth keys.

    Handles various separators: ×, x, X, *, х (cyrillic), ?.
    """
    result = dict(specs)
    for raw_key, (w_key, h_key, d_key) in _DIMENSIONS_MAP.items():
        val = result.pop(raw_key, None)
        if val is None:
            continue
        text = str(val).strip()
        # Normalize separators
        text = re.sub(r"[×xX*х?？]", "×", text)
        parts = [p.strip() for p in text.split("×") if p.strip()]
        nums = []
        for p in parts:
            m = re.search(r"(\d[\d\s]*(?:[.,]\d+)?)", p)
            if m:
                raw_number = m.group(1).replace(" ", "").replace(",", ".")
                if re.fullmatch(r"\d{1,2}\.\d{3}", raw_number):
                    raw_number = raw_number.replace(".", "")
                nums.append(raw_number)
        if len(nums) >= 3:
            if raw_key in _UNORDERED_WIDTH_HEIGHT_DIMENSION_KEYS:
                first = float(nums[0])
                second = float(nums[1])
                width = max(first, second)
                height = min(first, second)
                result.setdefault(w_key, str(width).rstrip("0").rstrip("."))
                result.setdefault(h_key, str(height).rstrip("0").rstrip("."))
                result.setdefault(d_key, nums[2])
                continue
            result.setdefault(w_key, nums[0])
            result.setdefault(h_key, nums[1])
            result.setdefault(d_key, nums[2])
        elif len(nums) == 1:
            # Single value — keep as-is under width key
            result.setdefault(w_key, nums[0])
    return result


def clean_value(key: str, val: Any, keep_units: bool = True, source_key: str | None = None) -> Any:
    if not isinstance(val, str):
        return val
        
    val_lower = val.lower().strip()

    registered_value = normalize_registered_value(key, val, source_key=source_key)
    if registered_value is not None:
        return registered_value

    if key in {"pipe_liquid", "pipe_gas"}:
        # Convert common metric diameters to canonical inch fractions for UI/filter selects.
        normalized = val.replace(",", ".")
        if "/" in normalized and '"' in normalized:
            return normalized.strip()
        match = re.search(r"(\d+(?:\.\d+)?)", normalized)
        if not match:
            return val.strip()
        try:
            mm = float(match.group(1))
        except ValueError:
            return val.strip()
        mm_to_inch = {
            6.35: '1/4"',
            9.52: '3/8"',
            12.70: '1/2"',
            15.88: '5/8"',
            19.05: '3/4"',
        }
        nearest = min(mm_to_inch.keys(), key=lambda k: abs(k - mm))
        if abs(nearest - mm) <= 0.25:
            return mm_to_inch[nearest]
        return match.group(1)

    if key == "compressor_brand":
        text = re.sub(r"\s+", " ", val).strip()
        lowered = text.lower().replace("ё", "е")
        canonical = {
            "gmcc": "GMCC",
            "toshiba": "Toshiba",
            "highly": "Highly",
            "panasonic": "Panasonic",
            "gree": "Gree",
        }
        for token, normalized in canonical.items():
            if token in lowered:
                return normalized
        return text

    if key == "airflow_max":
        numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)?", val)
        if numbers:
            parsed = [float(number.replace(",", ".")) for number in numbers]
            source_text = f"{source_key or ''} {val}".lower().replace("\xa0", " ")
            looks_like_m3_per_min = (
                "м³" in source_text
                and "/ч" not in source_text
                and "/ч" not in source_text.replace(" ", "")
                and max(parsed) <= 100
            )
            if looks_like_m3_per_min:
                return " / ".join(f"{number * 60:.6f}".rstrip("0").rstrip(".") for number in parsed)
        return re.sub(r"\s+", " ", val).strip()

    if key in {"dimensions_indoor_package_mm", "dimensions_outdoor_package_mm"}:
        text = val.replace("?", "×").replace("？", "×")
        text = re.sub(r"[xXх]", "×", text)
        text = re.sub(r"\s*×\s*", " × ", text)
        return re.sub(r"\s+", " ", text).strip()

    # 1. Логика для Булевых (Да/Нет)
    # Сюда попадают: inverter, wifi_ready, remote_control и все режимы
    boolean_keys = [
        "inverter", "wifi_ready", "remote_control", "timer", 
        "autorestart", "turbo_mode", "sleep_mode", "dehumidification",
        "airflow_direction", "fan_speed",
        "smart_home_integration", "voice_control",
        "bio_filter", "plasma_filter", "ionizer", "carbon_filter",
        "photocatalytic_filter", "electrostatic_filter", "uv_sterilization",
        "fresh_air", "humidification", "presence_sensor", "self_diagnosis",
        "includes_indoor_unit", "includes_outdoor_unit",
    ]
    
    if key == "wifi_ready":
        wifi_kind = _classify_wifi_value(val)
        if wifi_kind == "builtin":
            return True
        if wifi_kind == "ready":
            return "ready"
        if wifi_kind == "none":
            return False
        return val

    if key == "indoor_type":
        text = val_lower.replace("—", "-")
        text = re.sub(r"\s+", " ", text)
        if "каналь" in text:
            return "канальный"
        if "кассет" in text:
            return "кассетный"
        if (
            "напольно" in text
            or "подпотолоч" in text
            or "потолоч" in text
            or "универсальн" in text
            or "floor-ceiling" in text
            or "floor ceiling" in text
        ):
            return "напольно-потолочный"
        if "колон" in text or "console" in text or "column" in text:
            return "колонный"
        if "настенн" in text or "wall" in text:
            return "настенный"
        return text

    if key == "remote_control":
        no_markers = ("нет", "отсутств", "нету", "no")
        if any(marker in val_lower for marker in no_markers):
            return False
        return True

    if key in boolean_keys:
        if key == "inverter":
            if "неинвертор" in val_lower or "on/off" in val_lower or "on off" in val_lower:
                return False
            if "инвертор" in val_lower or "inverter" in val_lower:
                return True
        if val_lower in {"+", "✓", "✔"}:
            return True
        if "да" in val_lower or "есть" in val_lower or "поддерживается" in val_lower:
            return True
        if "нет" in val_lower or "отсутствует" in val_lower:
            return False
        return val # Если там что-то сложное, оставляем как есть

    # Some sources provide ranges like "0.89 / 2.5 / 3.7" (min/nom/max).
    # Keep nominal values in core numeric fields for consistent UI/filtering.
    if key in _PREFERRED_NUMERIC_KEYS:
        numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)?", val)
        if numbers:
            normalized = [n.replace(",", ".") for n in numbers]
            if key in {"capacity_cooling_kw", "capacity_heating_kw", "power_cons_cooling_kw", "power_cons_heating_kw"} and "/" in val:
                # For min/nom/max triplets pick nominal (middle) value.
                if len(normalized) >= 3:
                    selected = normalized[1]
                else:
                    selected = normalized[0]
            elif key in _MAX_FROM_RANGE_NUMERIC_KEYS and ("-" in val or "/" in val or "до" in val_lower or "~" in val):
                # For ranges use upper bound as recommended/max area.
                try:
                    selected = str(max(float(n) for n in normalized)).rstrip("0").rstrip(".")
                except ValueError:
                    selected = normalized[0]
            else:
                selected = normalized[0]

            if key in _POWER_KW_KEYS:
                try:
                    number = float(selected)
                except ValueError:
                    return selected
                # Some supplier pages label values as kW but still publish watt-scale
                # numbers, e.g. "210 / 2164 / 2500" for power consumption.
                if abs(number) >= 100:
                    return f"{number / 1000:.6f}".rstrip("0").rstrip(".")
            return selected

    # 2. Чистка чисел (Только если keep_units = False)
    if not keep_units:
        numeric_keys = [
            "capacity_", "power_cons_", "width_", "height_", "depth_", "weight_", 
            "pipe_max_", "eer", "cop"
        ]
        is_numeric = any(k in key for k in numeric_keys)
        
        if is_numeric:
            # Агрессивная чистка: "2.5 кВт" -> "2.5"
            clean = val.replace(" ", "").replace("кВт", "").replace("мм", "").replace("кг", "").replace("м2", "").replace("м", "")
            clean = clean.replace(",", ".")
            try:
                # Try converting to float if it looks like a number
                return float(clean)
            except ValueError:
                return clean

    # Если keep_units = True, просто убираем лишние пробелы и меняем запятые на точки (для красоты)
    if isinstance(val, str):
        # Меняем "2,5" на "2.5", но оставляем "кВт"
        # Аккуратно: заменяем запятую только если она между цифрами
        val = re.sub(r'(\d),(\d)', r'\1.\2', val)
        return val.strip()

    return val


def _parse_numbers(value: Any) -> List[int]:
    if value is None:
        return []
    if isinstance(value, (int, float)):
        return [int(value)]

    text = str(value).replace("−", "-").replace("—", "-")
    matches = re.findall(r"[-+]?\d+(?:[.,]\d+)?", text)
    numbers: List[int] = []
    for match in matches:
        normalized = match.replace(",", ".")
        try:
            numbers.append(int(float(normalized)))
        except ValueError:
            continue
    return numbers


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None

    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "да", "есть", "поддерживается"}:
        return True
    if text in {"false", "0", "no", "нет", "отсутствует"}:
        return False
    return None


def _normalize_compressor_type(value: Any, inverter_value: Any) -> str | None:
    text = str(value or "").strip().lower().replace("ё", "е")
    text = text.replace("—", "-")
    text = re.sub(r"\s+", " ", text)

    if text:
        if "full dc" in text or "full-dc" in text or "dc inverter" in text:
            return "full_dc"
        if (
            "неинвертор" in text
            or "on/off" in text
            or "on off" in text
            or "on-off" in text
            or "onoff" in text
        ):
            return "on_off"
        if "inverter" in text or "инвертор" in text:
            return "inverter"

    inverter_flag = _parse_bool(inverter_value)
    if inverter_flag is True:
        return "inverter"
    if inverter_flag is False:
        return "on_off"
    return None


def _normalize_indoor_type_kind(*values: Any) -> str | None:
    for raw in values:
        text = str(raw or "").strip().lower().replace("ё", "е")
        if not text:
            continue
        text = text.replace("—", "-")
        text = re.sub(r"\s+", " ", text)

        if "каналь" in text or "duct" in text:
            return "duct"
        if "кассет" in text or "cassette" in text:
            return "cassette"
        if (
            "напольно" in text
            or "подпотолоч" in text
            or "потолоч" in text
            or "универсальн" in text
            or "floor-ceiling" in text
            or "floor ceiling" in text
        ):
            return "floor_ceiling"
        if "колонн" in text or "column" in text or "console" in text:
            return "column"
    return None


def _normalize_system_type(type_value: Any, indoor_type_value: Any) -> str | None:
    type_text = str(type_value or "").strip().lower().replace("ё", "е")
    indoor_text = str(indoor_type_value or "").strip().lower().replace("ё", "е")
    type_text = type_text.replace("—", "-")
    indoor_text = indoor_text.replace("—", "-")
    type_text = re.sub(r"\s+", " ", type_text)
    indoor_text = re.sub(r"\s+", " ", indoor_text)
    combined = f"{type_text} {indoor_text}".strip()
    if not combined:
        return None

    if "наружн" in combined and "блок" in combined:
        return "наружный блок"
    if "внутренн" in combined and "блок" in combined:
        return "внутренний блок"
    if "мульти" in combined:
        return "мульти-сплит-система"

    industrial_markers = (
        "полупром",
        "полупромышлен",
        "промышлен",
        "кассет",
        "каналь",
        "колон",
        "напольно",
        "подпотолоч",
        "потолоч",
        "универсальн",
        "floor-ceiling",
        "floor ceiling",
    )
    if any(marker in combined for marker in industrial_markers):
        return "полупромышленный кондиционер"

    if "сплит" in combined or "кондиционер" in combined:
        return "сплит-система"

    if "настенн" in combined:
        return "сплит-система"

    return None


def _classify_wifi_value(value: Any) -> str | None:
    if isinstance(value, bool):
        return "builtin" if value else "none"
    if value is None:
        return None

    text = str(value).strip().lower().replace("ё", "е")
    text = text.replace("—", "-")

    none_markers = (
        "не поддерж",
        "отсутств",
        "нет",
    )
    if any(marker in text for marker in none_markers):
        return "none"

    ready_markers = (
        "приобрета",
        "отдельно",
        "опцион",
        "опци",
        "ready",
        "модул",
        "поддержива",
    )
    if any(marker in text for marker in ready_markers):
        return "ready"

    builtin_markers = (
        "встро",
        "built-in",
        "built in",
        "builtin",
        "check",
        "галоч",
        "true",
        "да",
        "есть",
        "✓",
        "+",
    )
    if any(marker in text for marker in builtin_markers):
        return "builtin"

    return None


def _resolve_dynamic_system_key(key: Any) -> str | None:
    text = str(key or "").strip().lower().replace("ё", "е")
    text = (
        text.replace("‑", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("⁰", "°")
        .replace("_", " ")
    )
    text = re.sub(r"\s+", " ", text)
    if "wifi" in text or "wi-fi" in text or "wi fi" in text:
        return "wifi_ready"
    if "для работы в режиме охлаждения" in text:
        return "temp_range_cool"
    if "для работы в режиме нагрева" in text or "для работы в режиме обогрева" in text:
        return "temp_range_heat"
    if "диаметр труб жидкого хладагента" in text:
        return "pipe_liquid"
    if "диаметр труб газообразного хладагента" in text:
        return "pipe_gas"
    return None


def _apply_wifi_state(
    specs: Dict[str, Any],
    wifi_tag_slugs: Optional[Sequence[str]] = None,
    strict_wifi_from_tags: bool = False,
) -> Dict[str, Any]:
    enriched = dict(specs)
    wifi_candidates = (
        enriched.get("wifi_ready"),
        enriched.get("wifi_builtin"),
        enriched.get("wifi_state"),
        enriched.get("wifi_module"),
        enriched.get("wi_fi"),
        enriched.get("wifi"),
    )
    wifi_kinds = [_classify_wifi_value(value) for value in wifi_candidates]
    wifi_kinds = [kind for kind in wifi_kinds if kind is not None]
    explicit_builtin_flag = _parse_bool(enriched.get("wifi_builtin"))
    explicit_ready_flag = _parse_bool(enriched.get("wifi_ready"))
    if explicit_builtin_flag is False and explicit_ready_flag is True:
        wifi_kinds = [kind for kind in wifi_kinds if kind != "builtin"]
        wifi_kinds.append("ready")

    # Drop stale keys and rebuild consistently.
    for key in (
        "wifi_ready",
        "wifi_builtin",
        "wifi_state",
        "wifi-builtin",
        "wifi-ready",
        "__filter_wifi",
        "__filter_wifi_builtin",
    ):
        if key in enriched:
            del enriched[key]

    tag_set = {slug.strip().lower() for slug in (wifi_tag_slugs or []) if slug}
    has_builtin_tag = "wifi-builtin" in tag_set
    has_ready_tag = "wifi-ready" in tag_set

    if has_builtin_tag:
        enriched["wifi_ready"] = True
        enriched["wifi_builtin"] = True
        enriched["wifi_state"] = "builtin"
        enriched["__filter_wifi"] = True
        enriched["__filter_wifi_builtin"] = True
        return enriched

    if has_ready_tag:
        enriched["wifi_ready"] = "ready"
        enriched["wifi_builtin"] = False
        enriched["wifi_state"] = "ready"
        enriched["__filter_wifi"] = True
        enriched["__filter_wifi_builtin"] = False
        return enriched

    if strict_wifi_from_tags:
        enriched["wifi_ready"] = False
        enriched["wifi_builtin"] = False
        enriched["wifi_state"] = "none"
        enriched["__filter_wifi"] = False
        enriched["__filter_wifi_builtin"] = False
        return enriched

    wifi_kind = None
    if "builtin" in wifi_kinds:
        wifi_kind = "builtin"
    elif "ready" in wifi_kinds:
        wifi_kind = "ready"
    elif "none" in wifi_kinds:
        wifi_kind = "none"

    if wifi_kind == "builtin":
        enriched["wifi_ready"] = True
        enriched["wifi_builtin"] = True
        enriched["wifi_state"] = "builtin"
        enriched["__filter_wifi"] = True
        enriched["__filter_wifi_builtin"] = True
    elif wifi_kind == "ready":
        enriched["wifi_ready"] = "ready"
        enriched["wifi_builtin"] = False
        enriched["wifi_state"] = "ready"
        enriched["__filter_wifi"] = True
        enriched["__filter_wifi_builtin"] = False
    else:
        enriched["wifi_ready"] = False
        enriched["wifi_builtin"] = False
        enriched["wifi_state"] = "none"
        enriched["__filter_wifi"] = False
        enriched["__filter_wifi_builtin"] = False

    return enriched


def enrich_filter_keys(
    specs: Dict[str, Any],
    wifi_tag_slugs: Optional[Sequence[str]] = None,
    strict_wifi_from_tags: bool = False,
) -> Dict[str, Any]:
    enriched = dict(specs)

    # Always rebuild internal filter keys on each pass to avoid stale values.
    for key in list(enriched.keys()):
        if key.startswith("__filter_"):
            del enriched[key]
    enriched.pop("compressor_type_norm", None)

    heat_numbers = _parse_numbers(enriched.get("temp_range_heat"))
    if heat_numbers:
        enriched["__filter_min_heat"] = min(heat_numbers)

    enriched = _apply_wifi_state(
        enriched,
        wifi_tag_slugs=wifi_tag_slugs,
        strict_wifi_from_tags=strict_wifi_from_tags,
    )

    noise_numbers = _parse_numbers(enriched.get("noise_indoor"))
    if noise_numbers:
        enriched["__filter_noise_min"] = min(noise_numbers)

    compressor_type_norm = _normalize_compressor_type(
        enriched.get("inverter_type"),
        enriched.get("inverter"),
    )
    if compressor_type_norm:
        enriched["compressor_type_norm"] = compressor_type_norm

    indoor_type_kind = _normalize_indoor_type_kind(
        enriched.get("indoor_type"),
        enriched.get("type"),
    )
    if indoor_type_kind:
        enriched["__filter_indoor_type"] = indoor_type_kind

    return enriched

def normalize_specs(
    specs: Dict[str, Any],
    keep_units: bool = True,
    wifi_tag_slugs: Optional[Sequence[str]] = None,
    strict_wifi_from_tags: bool = False,
    title: Optional[str] = None,
    auto_tag_slugs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Normalizes a dictionary of specifications:
    1. Maps Russian keys to System keys (using KEY_MAP).
    2. Cleans/Converts values (using clean_value).
    
    Returns a NEW dictionary with normalized specs.
    """
    if specs is None:
        return enrich_filter_keys(
            {},
            wifi_tag_slugs=wifi_tag_slugs,
            strict_wifi_from_tags=strict_wifi_from_tags,
        )
    if not isinstance(specs, dict):
        specs = {}
        
    old_specs = specs.copy()

    # Split composite dimension keys ("Габариты ... (ШхВхГ)" → width/height/depth)
    old_specs = _split_dimensions(old_specs)

    new_specs = old_specs.copy()
    
    # Проходим по старым русским ключам
    for rus_key, sys_key in KEY_MAP.items():
        if rus_key in old_specs:
            raw_val = old_specs[rus_key]

            # Explicit split keys with two metrics in one source value.
            rus_key_l = rus_key.lower().replace("ё", "е")
            if "eer/cop" in rus_key_l:
                numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)?", str(raw_val))
                if numbers:
                    new_specs["eer"] = numbers[0].replace(",", ".")
                    if len(numbers) > 1:
                        new_specs["cop"] = numbers[1].replace(",", ".")
                if rus_key != sys_key and rus_key in new_specs:
                    del new_specs[rus_key]
                continue
            if "seer/eer" in rus_key_l:
                numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)?", str(raw_val))
                if numbers:
                    new_specs["seer"] = numbers[0].replace(",", ".")
                    if len(numbers) > 1:
                        new_specs["eer"] = numbers[1].replace(",", ".")
                if rus_key != sys_key and rus_key in new_specs:
                    del new_specs[rus_key]
                continue
            if "scop/cop" in rus_key_l:
                numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)?", str(raw_val))
                if numbers:
                    new_specs["scop"] = numbers[0].replace(",", ".")
                    if len(numbers) > 1:
                        new_specs["cop"] = numbers[1].replace(",", ".")
                if rus_key != sys_key and rus_key in new_specs:
                    del new_specs[rus_key]
                continue

            if (
                sys_key in {"current_cooling_nominal_a", "current_heating_nominal_a"}
                and "рабочий ток" in rus_key_l
                and "ном" in rus_key_l
                and "макс" in rus_key_l
            ):
                numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)?", str(raw_val))
                if numbers:
                    max_key = (
                        "current_cooling_max_a"
                        if sys_key == "current_cooling_nominal_a"
                        else "current_heating_max_a"
                    )
                    new_specs[sys_key] = clean_value(
                        sys_key,
                        numbers[0].replace(",", "."),
                        keep_units=keep_units,
                        source_key=rus_key,
                    )
                    new_specs[max_key] = clean_value(
                        max_key,
                        numbers[-1].replace(",", "."),
                        keep_units=keep_units,
                        source_key=rus_key,
                    )
                if rus_key != sys_key and rus_key in new_specs:
                    del new_specs[rus_key]
                continue

            if sys_key in {"eer", "cop", "seer", "scop"} and "класс" in rus_key_l and "/" in str(raw_val):
                numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)?", str(raw_val))
                if numbers:
                    new_specs[sys_key] = numbers[0].replace(",", ".")
                class_match = re.search(r"/\s*([A-Za-zА-Яа-я][+\-]*)", str(raw_val))
                if class_match:
                    energy_class = (
                        class_match.group(1)
                        .strip()
                        .replace("А", "A")
                        .replace("а", "A")
                    )
                    if sys_key in {"eer", "seer"}:
                        new_specs["energy_class_cooling"] = energy_class
                    else:
                        new_specs["energy_class_heating"] = energy_class
                if rus_key != sys_key and rus_key in new_specs:
                    del new_specs[rus_key]
                continue

            if sys_key == "energy_class" and "/" in str(raw_val) and (
                "охлаждение" in rus_key_l or "холод" in rus_key_l or "охл" in rus_key_l
            ):
                classes = [
                    item.strip().replace("А", "A").replace("а", "A")
                    for item in re.split(r"\s*/\s*", str(raw_val))
                    if item.strip()
                ]
                if classes:
                    new_specs["energy_class_cooling"] = classes[0]
                    if len(classes) > 1:
                        new_specs["energy_class_heating"] = classes[1]
                if rus_key != sys_key and rus_key in new_specs:
                    del new_specs[rus_key]
                continue

            # Special rule: source key explicitly states "non-inverter".
            if "неинвертор" in rus_key_l and sys_key == "inverter":
                parsed = _parse_bool(raw_val)
                if parsed is True:
                    new_specs[sys_key] = False
                elif parsed is False:
                    new_specs[sys_key] = True
                else:
                    new_specs[sys_key] = clean_value(sys_key, raw_val, keep_units=keep_units)
                if rus_key != sys_key and rus_key in new_specs:
                    del new_specs[rus_key]
                continue

            # Чистим / Конвертируем
            triplet_target = _TRIPLET_SPEC_KEYS.get(sys_key)
            triplet_numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)?", str(raw_val))
            if triplet_target and len(triplet_numbers) >= 3 and "/" in str(raw_val):
                min_key, max_key = triplet_target
                new_specs[min_key] = clean_value(
                    min_key,
                    triplet_numbers[0].replace(",", "."),
                    keep_units=keep_units,
                    source_key=rus_key,
                )
                new_specs[max_key] = clean_value(
                    max_key,
                    triplet_numbers[2].replace(",", "."),
                    keep_units=keep_units,
                    source_key=rus_key,
                )
            clean_val = clean_value(sys_key, raw_val, keep_units=keep_units, source_key=rus_key)

            # Записываем новый ключ
            new_specs[sys_key] = clean_val

            # Удаляем старый (чтобы не было дублей)
            if rus_key != sys_key and rus_key in new_specs:
                del new_specs[rus_key]
                
    # Also attempt to clean values for keys that are ALREADY system keys
    # (Just to be safe, e.g. if we re-run normalization)
    for sys_key in KEY_MAP.values():
        if sys_key in new_specs:
             new_specs[sys_key] = clean_value(sys_key, new_specs[sys_key], keep_units=keep_units)

    for raw_key, raw_val in old_specs.items():
        if raw_key in KEY_MAP or not isinstance(raw_key, str):
            continue
        sys_key = _resolve_dynamic_system_key(raw_key)
        if not sys_key or sys_key in new_specs:
            continue
        new_specs[sys_key] = clean_value(sys_key, raw_val, keep_units=keep_units, source_key=raw_key)
        if raw_key in new_specs:
            del new_specs[raw_key]

    # Source price/rate are import internals; never persist in product specs.
    for dropped_key in _DROPPED_SPEC_KEYS:
        new_specs.pop(dropped_key, None)

    normalized_type = _normalize_system_type(
        new_specs.get("type"),
        new_specs.get("indoor_type"),
    )
    if normalized_type:
        new_specs["type"] = normalized_type

    current_brand = str(new_specs.get("brand", "")).strip()
    if not current_brand or is_invalid_brand_name(current_brand):
        inferred_brand = extract_brand_name(new_specs, title=title or "")
        if inferred_brand:
            new_specs["brand"] = inferred_brand
        elif current_brand and is_invalid_brand_name(current_brand):
            new_specs.pop("brand", None)

    brand_slug = extract_brand_slug(new_specs, title=title or "")
    if auto_tag_slugs is not None and brand_slug and brand_slug not in auto_tag_slugs:
        auto_tag_slugs.append(brand_slug)
            
    enriched_specs = enrich_filter_keys(
        new_specs,
        wifi_tag_slugs=wifi_tag_slugs,
        strict_wifi_from_tags=strict_wifi_from_tags,
    )
    typed_specs = build_typed_specs(enriched_specs)
    if typed_specs:
        enriched_specs["__typed_specs"] = typed_specs
    return enriched_specs
