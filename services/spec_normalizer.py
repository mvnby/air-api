import re
from typing import Any, Dict, List, Optional, Sequence

from services.tag_logic import extract_brand_name, extract_brand_slug

# 1. Маппинг (Русский -> Системный)
KEY_MAP = {
    # --- ОСНОВНОЕ ---
    "Тип кондиционера": "type",
    "Тип внутреннего блока": "indoor_type",
    "Режим работы": "modes",
    "Обслуживаемая площадь": "area_m2",
    "Цвет": "color",
    "Хладагент (фреон)": "freon_type",
    "Инверторная технология": "inverter",
    "Бренд": "brand",
    "Марка": "brand",
    "Производитель": "brand",
    "Серия": "series",
    "Линейка": "series",
    "Модельный ряд": "series",
    
    # --- УПРАВЛЕНИЕ ---
    "Wi-Fi": "wifi_ready",
    "Wi-Fi модуль": "wifi_ready",
    "Wi-Fi module": "wifi_ready",
    "Wi-Fi Ready": "wifi_ready",
    "Пульт дистанционного управления": "remote_control",
    "Таймер включения/выключения": "timer",
    "Регулировка направления воздушного потока": "airflow_direction",
    "Регулировка скорости вращения вентилятора": "fan_speed",
    "Авторестарт после пропадания питания": "autorestart",
    "Турбо-режим": "turbo_mode",
    "Режим «Сон»": "sleep_mode",
    "Осушение воздуха": "dehumidification",

    # --- МОЩНОСТЬ ---
    "Мощность охлаждения": "capacity_cooling_kw",
    "Мощность обогрева": "capacity_heating_kw",
    "Потребляемая мощность при охлаждении": "power_cons_cooling_kw",
    "Потребляемая мощность при обогреве": "power_cons_heating_kw",
    
    # --- ЭФФЕКТИВНОСТЬ ---
    "Энергоэффективность при охлаждении (EER)": "eer",
    "Энергоэффективность при обогреве (COP)": "cop",
    
    # --- ШУМ ---
    "Шум внутреннего блока": "noise_indoor",
    "Шум наружного блока": "noise_outdoor",
    
    # --- ГАБАРИТЫ ВНУТРЕННИЙ ---
    "Ширина внутреннего блока": "width_indoor",
    "Высота внутреннего блока": "height_indoor",
    "Глубина внутреннего блока": "depth_indoor",
    "Вес внутреннего блока": "weight_indoor",
    
    # --- ГАБАРИТЫ НАРУЖНЫЙ ---
    "Ширина наружного блока": "width_outdoor",
    "Высота наружного блока": "height_outdoor",
    "Глубина наружного блока": "depth_outdoor",
    "Вес наружного блока": "weight_outdoor",
    
    # --- МОНТАЖ ---
    "Максимальная длина магистрали": "pipe_max_length",
    "Перепад высот": "pipe_max_height",
    "Диаметр жидкостной трубы": "pipe_liquid",
    "Диаметр газовой трубы": "pipe_gas",
    
    # --- ТЕМПЕРАТУРЫ ---
    "Рабочая температура при охлаждении": "temp_range_cool",
    "Рабочая температура при обогреве": "temp_range_heat",
    
    "Максимальный расход воздуха внутреннего блока": "airflow_max",

    # --- ФИЛЬТРЫ И ДОП. ФУНКЦИИ ---
    "Приток свежего воздуха": "fresh_air",
    'Интеграция в "умный дом"': "smart_home_integration",
    "Голосовое управление": "voice_control",
    "Биофильтр": "bio_filter",
    "Плазменный фильтр": "plasma_filter",
    "Ионизатор": "ionizer",
    "Угольный фильтр": "carbon_filter",
    "Фотокаталитический фильтр": "photocatalytic_filter",
    "Электростатический фильтр": "electrostatic_filter",
    "Обеззараживание ультрафиолетом": "uv_sterilization"
}

def clean_value(key: str, val: Any, keep_units: bool = True) -> Any:
    if not isinstance(val, str):
        return val
        
    val_lower = val.lower().strip()

    # 1. Логика для Булевых (Да/Нет)
    # Сюда попадают: inverter, wifi_ready, remote_control и все режимы
    boolean_keys = [
        "inverter", "wifi_ready", "remote_control", "timer", 
        "autorestart", "turbo_mode", "sleep_mode", "dehumidification",
        "airflow_direction", "fan_speed",
        "smart_home_integration", "voice_control",
        "bio_filter", "plasma_filter", "ionizer", "carbon_filter",
        "photocatalytic_filter", "electrostatic_filter", "uv_sterilization",
        "fresh_air"
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

    if key in boolean_keys:
        if "да" in val_lower or "есть" in val_lower or "поддерживается" in val_lower:
            return True
        if "нет" in val_lower or "отсутствует" in val_lower:
            return False
        return val # Если там что-то сложное, оставляем как есть

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
        if "on/off" in text or "on off" in text or "on-off" in text or "onoff" in text:
            return "on_off"
        if "inverter" in text or "инвертор" in text:
            return "inverter"

    inverter_flag = _parse_bool(inverter_value)
    if inverter_flag is True:
        return "inverter"
    if inverter_flag is False:
        return "on_off"
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
        "check",
        "галоч",
        "true",
        "да",
        "есть",
        "✓",
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
        .replace("_", " ")
    )
    text = re.sub(r"\s+", " ", text)
    if "wifi" in text or "wi-fi" in text or "wi fi" in text:
        return "wifi_ready"
    return None


def _apply_wifi_state(
    specs: Dict[str, Any],
    wifi_tag_slugs: Optional[Sequence[str]] = None,
    strict_wifi_from_tags: bool = False,
) -> Dict[str, Any]:
    enriched = dict(specs)
    wifi_candidates = (
        enriched.get("wifi_ready"),
        enriched.get("wifi_module"),
        enriched.get("wi_fi"),
        enriched.get("wifi"),
    )
    wifi_kinds = [_classify_wifi_value(value) for value in wifi_candidates]
    wifi_kinds = [kind for kind in wifi_kinds if kind is not None]

    # Drop stale keys and rebuild consistently.
    for key in ("wifi_ready", "wifi-builtin", "wifi-ready", "__filter_wifi", "__filter_wifi_builtin"):
        if key in enriched:
            del enriched[key]

    tag_set = {slug.strip().lower() for slug in (wifi_tag_slugs or []) if slug}
    has_builtin_tag = "wifi-builtin" in tag_set
    has_ready_tag = "wifi-ready" in tag_set

    if has_builtin_tag:
        enriched["wifi_ready"] = True
        enriched["__filter_wifi"] = True
        enriched["__filter_wifi_builtin"] = True
        return enriched

    if has_ready_tag:
        enriched["wifi_ready"] = "ready"
        enriched["__filter_wifi"] = True
        enriched["__filter_wifi_builtin"] = False
        return enriched

    if strict_wifi_from_tags:
        enriched["wifi_ready"] = False
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
        enriched["__filter_wifi"] = True
        enriched["__filter_wifi_builtin"] = True
    elif wifi_kind == "ready":
        enriched["wifi_ready"] = "ready"
        enriched["__filter_wifi"] = True
        enriched["__filter_wifi_builtin"] = False
    else:
        enriched["wifi_ready"] = False
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
    new_specs = old_specs.copy()
    
    # Проходим по старым русским ключам
    for rus_key, sys_key in KEY_MAP.items():
        if rus_key in old_specs:
            raw_val = old_specs[rus_key]
            
            # Чистим / Конвертируем
            clean_val = clean_value(sys_key, raw_val, keep_units=keep_units)
            
            # Записываем новый ключ
            new_specs[sys_key] = clean_val
            
            # Удаляем старый (чтобы не было дублей)
            if rus_key in new_specs:
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
        new_specs[sys_key] = clean_value(sys_key, raw_val, keep_units=keep_units)

    if not str(new_specs.get("brand", "")).strip():
        inferred_brand = extract_brand_name(new_specs, title=title or "")
        if inferred_brand:
            new_specs["brand"] = inferred_brand

    brand_slug = extract_brand_slug(new_specs, title=title or "")
    if auto_tag_slugs is not None and brand_slug and brand_slug not in auto_tag_slugs:
        auto_tag_slugs.append(brand_slug)
            
    return enrich_filter_keys(
        new_specs,
        wifi_tag_slugs=wifi_tag_slugs,
        strict_wifi_from_tags=strict_wifi_from_tags,
    )
