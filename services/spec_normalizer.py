import re
from typing import Any, Dict, List

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
    
    # --- УПРАВЛЕНИЕ ---
    "Wi-Fi": "wifi_ready",
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
        "photocatalytic_filter", "electrostatic_filter", "uv_sterilization"
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


def enrich_filter_keys(specs: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(specs)

    # Always rebuild internal filter keys on each pass to avoid stale values.
    for key in list(enriched.keys()):
        if key.startswith("__filter_"):
            del enriched[key]

    heat_numbers = _parse_numbers(enriched.get("temp_range_heat"))
    if heat_numbers:
        enriched["__filter_min_heat"] = min(heat_numbers)

    wifi_kind = _classify_wifi_value(enriched.get("wifi_ready"))
    if wifi_kind == "builtin":
        enriched["wifi-builtin"] = True
        enriched["__filter_wifi"] = True
        enriched["__filter_wifi_builtin"] = True
    elif wifi_kind == "ready":
        enriched["wifi-ready"] = True
        enriched["__filter_wifi"] = True
        enriched["__filter_wifi_builtin"] = False
    elif wifi_kind == "none":
        enriched["__filter_wifi"] = False
        enriched["__filter_wifi_builtin"] = False

    noise_numbers = _parse_numbers(enriched.get("noise_indoor"))
    if noise_numbers:
        enriched["__filter_noise_min"] = min(noise_numbers)

    return enriched

def normalize_specs(specs: Dict[str, Any], keep_units: bool = True) -> Dict[str, Any]:
    """
    Normalizes a dictionary of specifications:
    1. Maps Russian keys to System keys (using KEY_MAP).
    2. Cleans/Converts values (using clean_value).
    
    Returns a NEW dictionary with normalized specs.
    """
    if not specs:
        return {}
        
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
            
    return enrich_filter_keys(new_specs)
