import re
from typing import Any, Dict, List, Optional, Sequence

from services.tag_logic import extract_brand_name, extract_brand_slug, is_invalid_brand_name

# 1. Маппинг (Русский -> Системный)
KEY_MAP = {
    # --- ОСНОВНОЕ ---
    "Тип": "type",
    "Тип кондиционера": "type",
    "Тип системы": "inverter",
    "Тип внутреннего блока": "indoor_type",
    "Режим работы": "modes",
    "Режимы работы": "modes",
    "Обслуживаемая площадь": "area_m2",
    "Обслуживаемая площадь, кв.м": "area_m2",
    "Площадь охлаждения": "area_m2",
    "Площадь помещения": "area_m2",
    "Цвет": "color",
    "Хладагент (фреон)": "freon_type",
    "Хладагент": "freon_type",
    "Тип хладагента": "freon_type",
    "Инверторная технология": "inverter",
    "Инверторный": "inverter",
    "Инверторное управление": "inverter",
    "Инверторное управление мощностью": "inverter",
    "Инверторный компрессор": "inverter",
    "Бренд": "brand",
    "Марка": "brand",
    "Производитель": "brand",
    "Наличие": "availability",
    "Серия": "series",
    "Линейка": "series",
    "Модельный ряд": "series",
    
    # --- УПРАВЛЕНИЕ ---
    "Wi-Fi": "wifi_ready",
    "Wi-Fi модуль": "wifi_ready",
    "Wi-Fi module": "wifi_ready",
    "Wi-Fi Ready": "wifi_ready",
    "Пульт дистанционного управления": "remote_control",
    "Пульт ДУ": "remote_control",
    "Пульт": "remote_control",
    "Пульт управления": "remote_control",
    "Таймер включения/выключения": "timer",
    "Таймер": "timer",
    "Регулировка направления воздушного потока": "airflow_direction",
    "Регулировка скорости вращения вентилятора": "fan_speed",
    "Регулятор скорости вращения вентилятора": "fan_speed",
    "Авторестарт после пропадания питания": "autorestart",
    "Авторестарт": "autorestart",
    "Турбо-режим": "turbo_mode",
    "Турбо режим": "turbo_mode",
    "Режим «Сон»": "sleep_mode",
    "Ночной режим": "sleep_mode",
    "Осушение воздуха": "dehumidification",
    "Осушение": "dehumidification",
    "Режим осушения воздуха": "dehumidification",

    # --- МОЩНОСТЬ ---
    "Мощность охлаждения": "capacity_cooling_kw",
    "Мощность охлаждения, кВт": "capacity_cooling_kw",
    "Мощность охлаждения (Мин/Ном/Макс), кВт": "capacity_cooling_kw",
    "Мощность в режиме охлаждения": "capacity_cooling_kw",
    "Мощность в режиме охлаждения, кВт": "capacity_cooling_kw",
    "Холодопроизводительность": "capacity_cooling_kw",
    "Охлаждение, кВт": "capacity_cooling_kw",
    "Охлаждение минимум, кВт": "capacity_cooling_min_kw",
    "Охлаждение максимум, кВт": "capacity_cooling_max_kw",
    "Мощность обогрева": "capacity_heating_kw",
    "Мощность обогрева, кВт": "capacity_heating_kw",
    "Мощность нагрева (Мин/Ном/Макс), кВт": "capacity_heating_kw",
    "Мощность в режиме обогрева": "capacity_heating_kw",
    "Мощность в режиме обогрева, кВт": "capacity_heating_kw",
    "Теплопроизводительность": "capacity_heating_kw",
    "Нагрев, кВт": "capacity_heating_kw",
    "Нагрев минимум, кВт": "capacity_heating_min_kw",
    "Нагрев максимум, кВт": "capacity_heating_max_kw",
    "Потребляемая мощность при охлаждении": "power_cons_cooling_kw",
    "Потребляемая мощность при охлаждении, кВт": "power_cons_cooling_kw",
    "Потребление электроэнергии в режиме охлаждения (Мин / Ном / Макс), кВт": "power_cons_cooling_kw",
    "Номинальная потребляемая мощность (охлаждение), кВт": "power_cons_cooling_kw",
    "Минимальная потребляемая мощность (охлаждение), кВт": "power_cons_cooling_min_kw",
    "Максимальная потребляемая мощность (охлаждение), кВт": "power_cons_cooling_max_kw",
    "Потребляемая мощность при обогреве": "power_cons_heating_kw",
    "Потребляемая мощность при обогреве, кВт": "power_cons_heating_kw",
    "Потребление электроэнергии в режиме нагрева (Мин / Ном / Макс), кВт": "power_cons_heating_kw",
    "Номинальная потребляемая мощность (нагрев), кВт": "power_cons_heating_kw",
    "Минимальная потребляемая мощность (нагрев), кВт": "power_cons_heating_min_kw",
    "Максимальная потребляемая мощность (нагрев), кВт": "power_cons_heating_max_kw",
    
    # --- ЭФФЕКТИВНОСТЬ ---
    "Энергоэффективность при охлаждении (EER)": "eer",
    "EER": "eer",
    "Энергоэффективность при обогреве (COP)": "cop",
    "COP": "cop",
    "Класс энергоэффективности": "energy_class",
    "Класс энергоэффективности при охлаждении": "energy_class_cooling",
    "Класс энергоэффективности при обогреве": "energy_class_heating",
    
    # --- ШУМ ---
    "Шум внутреннего блока": "noise_indoor",
    "Шум внутреннего блока, дБ": "noise_indoor",
    "Уровень шума внутреннего блока": "noise_indoor",
    "Уровень шума (макс), дБ": "noise_indoor",
    "Уровень звукового давления [дБ(А)], Выс/Ср/Низ/Сверх": "noise_indoor",
    "Уровень шума в режиме ОХЛАЖДЕНИЯ (Тих / Низ / Ср /Макс), дБ": "noise_indoor",
    "Уровень шума в режиме НАГРЕВА (Низ / Ср / Макс), дБ": "noise_indoor",
    "Шум наружного блока": "noise_outdoor",
    "Шум наружного блока, дБ": "noise_outdoor",
    "Шум внешнего блока": "noise_outdoor",
    "Шум внешнего блока, дБ": "noise_outdoor",
    "Уровень шума наружного блока": "noise_outdoor",
    "Уровень шума наружного блока, дБ": "noise_outdoor",
    "Уровень звукового давления, дБ, А": "noise_outdoor",
    
    # --- ГАБАРИТЫ ВНУТРЕННИЙ ---
    "Ширина внутреннего блока": "width_indoor",
    "Высота внутреннего блока": "height_indoor",
    "Глубина внутреннего блока": "depth_indoor",
    "Вес внутреннего блока": "weight_indoor",
    "Вес внутреннего блока, кг": "weight_indoor",
    "Чистый вес / Вес в упаковке, кг": "weight_indoor",
    "Внутренний блок без упаковки, кг": "weight_indoor",
    
    # --- ГАБАРИТЫ НАРУЖНЫЙ ---
    "Ширина наружного блока": "width_outdoor",
    "Высота наружного блока": "height_outdoor",
    "Глубина наружного блока": "depth_outdoor",
    "Вес наружного блока": "weight_outdoor",
    "Вес наружного блока, кг": "weight_outdoor",
    "Вес внешнего блока": "weight_outdoor",
    "Вес внешнего блока, кг": "weight_outdoor",
    "Чистый вес / вес в упаковке, кг": "weight_outdoor",
    "Наружный блок без упаковки, кг": "weight_outdoor",
    
    # --- МОНТАЖ ---
    "Максимальная длина магистрали": "pipe_max_length",
    "Максимальная длина коммуникаций": "pipe_max_length",
    "Максимальная длина коммуникаций, м": "pipe_max_length",
    "Макс. длина трассы": "pipe_max_length",
    "Макс. длина трубопроводов без дополнительной заправки, м": "pipe_max_length",
    "Перепад высот": "pipe_max_height",
    "Перепад высот, м": "pipe_max_height",
    "Максимальная длина/перепад высот, м": "pipe_max_length",
    "Максимальная длина/перепад высот, при использовании только в режиме охлаждения, м": "pipe_max_length",
    "Максимальный перепад высот": "multi_max_height_diff",
    "Максимальное количество внутренних блоков": "multi_max_indoor_units",
    "Максимальная суммарная длина магистрали": "multi_max_total_pipe_length",
    "Диаметр жидкостной трубы": "pipe_liquid",
    "Диаметр жидкостной линии, мм": "pipe_liquid",
    "Диаметр газовой трубы": "pipe_gas",
    "Диаметр газовой линии, мм": "pipe_gas",
    
    # --- ТЕМПЕРАТУРЫ ---
    "Рабочая температура при охлаждении": "temp_range_cool",
    "Рабочий диапазон температур при охлаждении": "temp_range_cool",
    "Рабочий диапазон температур при охлаждении,°C": "temp_range_cool",
    "Рабочий диапазон температур при охлаждении, °C": "temp_range_cool",
    "Охлаждение, °С": "temp_range_cool",
    "Рабочая температура при обогреве": "temp_range_heat",
    "Рабочий диапазон температур при обогреве": "temp_range_heat",
    "Рабочий диапазон температур при обогреве,°C": "temp_range_heat",
    "Рабочий диапазон температур при обогреве, °C": "temp_range_heat",
    "Нагрев, °С": "temp_range_heat",
    "Минимальная температура наружного воздуха": "temp_range_heat",
    "Мин. температура (обогрев)": "temp_range_heat",
    
    # --- ПЛОЩАДЬ (с единицами) ---
    "Обслуживаемая площадь до": "area_m2",
    "Обслуживаемая площадь до, м2": "area_m2",
    "Рекомендуемая максимальная площадь помещения": "area_m2",
    "Рекомендованная площадь, м 2": "area_m2",
    
    # --- ЭНЕРГОЭФФЕКТИВНОСТЬ (без скобок) ---
    "Энергоэффективность при охлаждении": "energy_class_cooling",
    "Энергоэффективность при обогреве": "energy_class_heating",
    "Класс эффективности": "energy_class",
    "Класс энергоэффективности (Холод / Тепло)": "energy_class",
    "Коэффициент энергоэффективности (EER / COP)": "eer",
    "Энергоэффективность SEER/EER": "eer",
    "Энергоэффективность SCOP/COP": "cop",
    
    "Максимальный расход воздуха внутреннего блока": "airflow_max",
    "Расход воздуха (высокая скорость), м 3 /ч": "airflow_max",

    # --- ФИЛЬТРЫ И ДОП. ФУНКЦИИ ---
    "Приток свежего воздуха": "fresh_air",
    'Интеграция в "умный дом"': "smart_home_integration",
    "Голосовое управление": "voice_control",
    "Биофильтр": "bio_filter",
    "Плазменный фильтр": "plasma_filter",
    "Ионизатор": "ionizer",
    "Ионизация": "ionizer",
    "Угольный фильтр": "carbon_filter",
    "Фотокаталитический фильтр": "photocatalytic_filter",
    "Электростатический фильтр": "electrostatic_filter",
    "Обеззараживание ультрафиолетом": "uv_sterilization",
    "Самоочистка": "self_cleaning",
    "Автоочистка теплообменника": "self_cleaning",
    "Wi-Fi управление": "wifi_ready",
    "Марка используемого хладагента": "freon_type",
    "Производитель компрессора": "compressor_brand",
    "Номинальный уровень рабочего тока (охлаждение), А": "current_cooling_nominal_a",
    "Номинальный уровень рабочего тока (нагрев), А": "current_heating_nominal_a",
    "Дополнительная заправка (г/м)": "refrigerant_additional_g_m",
    "Вес заправляемого хладагента, г": "refrigerant_charge_g",
    "Артикулы товара": "sku_list",
    "Подача питания": "power_supply_location",
    "Подключение питания": "power_supply_location",
    "Электропитание, Ф/В/Гц": "power_supply",
    "Электропитание (Ø / В / Гц)": "power_supply",
    "Модель": "model",
    "Цена источника": "source_price_rub",
    "Курс RUB/BYN (импорт)": "source_fx_rub_byn",
    "Габаритные размеры в упаковке (Ш/Г/В), мм": "dimensions_outdoor_package_mm",
}

# Composite dimension keys: "940×1250×340" → split into width/height/depth
# Maps raw key patterns → (width_key, height_key, depth_key)
_DIMENSIONS_MAP = {
    "Габариты внутреннего блока (ШхВхГ)": ("width_indoor", "height_indoor", "depth_indoor"),
    "Габариты внутреннего блока (ШхВхГ), мм": ("width_indoor", "height_indoor", "depth_indoor"),
    "Габариты наружного блока (ШхВхГ)": ("width_outdoor", "height_outdoor", "depth_outdoor"),
    "Габариты наружного блока (ШхВхГ), мм": ("width_outdoor", "height_outdoor", "depth_outdoor"),
    "Габариты внешнего блока (ШхВхГ)": ("width_outdoor", "height_outdoor", "depth_outdoor"),
    "Габариты внешнего блока (ШхВхГ), мм": ("width_outdoor", "height_outdoor", "depth_outdoor"),
    "Габариты мм": ("width_indoor", "height_indoor", "depth_indoor"),
    # Haierproff uses width/depth/height order (Ш/Г/В).
    "Габаритные размеры без упаковки (Ш/Г/В), мм": ("width_outdoor", "depth_outdoor", "height_outdoor"),
    "Внутренний блок без упаковки (Ш × В × Г), мм": ("width_indoor", "height_indoor", "depth_indoor"),
    "Наружный блок без упаковки (Ш × В × Г), мм": ("width_outdoor", "height_outdoor", "depth_outdoor"),
}

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
    "source_price_rub",
    "source_fx_rub_byn",
}


def _split_dimensions(specs: Dict[str, Any]) -> Dict[str, Any]:
    """Split composite dimension values like '940×1250×340' into
    individual width/height/depth keys.

    Handles various separators: ×, x, X, *, х (cyrillic).
    """
    result = dict(specs)
    for raw_key, (w_key, h_key, d_key) in _DIMENSIONS_MAP.items():
        val = result.pop(raw_key, None)
        if val is None:
            continue
        text = str(val).strip()
        # Normalize separators
        text = re.sub(r"[×xX*х]", "×", text)
        parts = [p.strip() for p in text.split("×") if p.strip()]
        nums = []
        for p in parts:
            m = re.search(r"(\d+(?:[.,]\d+)?)", p)
            if m:
                nums.append(m.group(1).replace(",", "."))
        if len(nums) >= 3:
            result.setdefault(w_key, nums[0])
            result.setdefault(h_key, nums[1])
            result.setdefault(d_key, nums[2])
        elif len(nums) == 1:
            # Single value — keep as-is under width key
            result.setdefault(w_key, nums[0])
    return result


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
        if key == "inverter":
            if "инвертор" in val_lower or "inverter" in val_lower:
                return True
            if "неинвертор" in val_lower or "on/off" in val_lower or "on off" in val_lower:
                return False
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
                    return normalized[1]
            if key == "area_m2" and ("-" in val or "до" in val_lower or "~" in val):
                # For ranges use upper bound as recommended/max area.
                try:
                    return str(max(float(n) for n in normalized)).rstrip("0").rstrip(".")
                except ValueError:
                    pass
            return normalized[0]

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
            or "floor-ceiling" in text
            or "floor ceiling" in text
        ):
            return "floor_ceiling"
        if "колонн" in text or "column" in text or "console" in text:
            return "column"
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
            
    return enrich_filter_keys(
        new_specs,
        wifi_tag_slugs=wifi_tag_slugs,
        strict_wifi_from_tags=strict_wifi_from_tags,
    )
