"""Typed registry for catalog specifications.

The registry is intentionally independent from database models: parsers,
normalizers, manager UI and public catalog code can all use the same metadata.
The first rollout keeps the old flat specs JSON compatible while giving the
normalizer canonical aliases, units and value types.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from enum import Enum
import re
from typing import Any, Iterable, Mapping


class SpecValueType(str, Enum):
    TEXT = "text"
    BOOLEAN = "boolean"
    ENUM = "enum"
    QUANTITY = "quantity"
    RANGE = "range"
    NUMBER_LIST = "number_list"
    STATE = "state"
    DIMENSIONS = "dimensions"


class QuantityKind(str, Enum):
    POWER = "power"
    LENGTH = "length"
    WEIGHT = "weight"
    TEMPERATURE = "temperature"
    AIRFLOW = "airflow"
    NOISE = "noise"
    CURRENT = "current"
    AREA = "area"
    VOLUME_RATE = "volume_rate"
    ENERGY = "energy"
    REFRIGERANT_MASS = "refrigerant_mass"
    COUNT = "count"


@dataclass(frozen=True)
class SpecDefinition:
    key: str
    label: str
    value_type: SpecValueType
    quantity_kind: QuantityKind | None = None
    canonical_unit: str | None = None
    aliases: tuple[str, ...] = ()
    enum_values: tuple[str, ...] = ()
    description: str | None = None
    manager_note: str | None = None


def _spec(
    key: str,
    label: str,
    value_type: SpecValueType,
    *,
    quantity_kind: QuantityKind | None = None,
    canonical_unit: str | None = None,
    aliases: Iterable[str] = (),
    enum_values: Iterable[str] = (),
    description: str | None = None,
    manager_note: str | None = None,
) -> SpecDefinition:
    return SpecDefinition(
        key=key,
        label=label,
        value_type=value_type,
        quantity_kind=quantity_kind,
        canonical_unit=canonical_unit,
        aliases=tuple(aliases),
        enum_values=tuple(enum_values),
        description=description,
        manager_note=manager_note,
    )


SPEC_DEFINITIONS: Mapping[str, SpecDefinition] = {
    "type": _spec(
        "type",
        "Тип кондиционера",
        SpecValueType.ENUM,
        enum_values=(
            "сплит-система",
            "мульти-сплит-система",
            "внутренний блок",
            "наружный блок",
            "полупромышленный кондиционер",
        ),
    ),
    "indoor_type": _spec(
        "indoor_type",
        "Тип внутреннего блока",
        SpecValueType.ENUM,
        enum_values=("настенный", "кассетный", "канальный", "напольно-потолочный", "колонный"),
    ),
    "brand": _spec("brand", "Бренд", SpecValueType.TEXT),
    "series": _spec("series", "Серия", SpecValueType.TEXT),
    "model": _spec("model", "Модель", SpecValueType.TEXT),
    "model_indoor": _spec("model_indoor", "Модель внутреннего блока", SpecValueType.TEXT),
    "model_outdoor": _spec("model_outdoor", "Модель наружного блока", SpecValueType.TEXT),
    "sku": _spec("sku", "Артикул", SpecValueType.TEXT),
    "release_year": _spec("release_year", "Дата выхода на рынок", SpecValueType.TEXT, aliases=("Дата выхода на рынок",)),
    "inverter": _spec(
        "inverter",
        "Инвертор",
        SpecValueType.BOOLEAN,
        aliases=("Компрессор: Инверторный компрессор",),
    ),
    "wifi_state": _spec(
        "wifi_state",
        "Состояние Wi-Fi",
        SpecValueType.STATE,
        enum_values=("builtin", "ready", "none"),
        description=(
            "Единое состояние Wi-Fi: встроенный модуль, подготовка под отдельный модуль "
            "или отсутствие поддержки."
        ),
    ),
    "wifi_ready": _spec(
        "wifi_ready",
        "Wi-Fi Ready",
        SpecValueType.STATE,
        enum_values=("true", "ready", "false"),
        description="Совместимое поле Wi-Fi: true означает встроенный модуль, ready — модуль приобретается отдельно.",
    ),
    "wifi_builtin": _spec("wifi_builtin", "Wi-Fi встроенный", SpecValueType.BOOLEAN),
    "capacity_cooling_kw": _spec(
        "capacity_cooling_kw",
        "Мощность охлаждения",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.POWER,
        canonical_unit="kW",
        description=(
            "Номинальная холодопроизводительность. У инверторных моделей фактическая "
            "мощность может изменяться в диапазоне от минимальной до максимальной."
        ),
    ),
    "capacity_cooling_min_kw": _spec(
        "capacity_cooling_min_kw",
        "Минимальная мощность охлаждения",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.POWER,
        canonical_unit="kW",
        aliases=("Охлаждение минимум, Вт",),
    ),
    "capacity_cooling_max_kw": _spec(
        "capacity_cooling_max_kw",
        "Максимальная мощность охлаждения",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.POWER,
        canonical_unit="kW",
        aliases=("Охлаждение максимум, Вт",),
    ),
    "capacity_heating_kw": _spec(
        "capacity_heating_kw",
        "Мощность обогрева",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.POWER,
        canonical_unit="kW",
    ),
    "capacity_heating_min_kw": _spec(
        "capacity_heating_min_kw",
        "Минимальная мощность обогрева",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.POWER,
        canonical_unit="kW",
        aliases=("Нагрев минимум, Вт",),
    ),
    "capacity_heating_max_kw": _spec(
        "capacity_heating_max_kw",
        "Максимальная мощность обогрева",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.POWER,
        canonical_unit="kW",
        aliases=("Нагрев максимум, Вт",),
    ),
    "power_cons_cooling_kw": _spec(
        "power_cons_cooling_kw",
        "Потребляемая мощность при охлаждении",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.POWER,
        canonical_unit="kW",
        aliases=(
            "Номинальная потребляемая мощность (охлаждение), Вт",
            "Потребляемая мощность, номинальная (Охлаждение) кВт",
        ),
    ),
    "power_cons_heating_kw": _spec(
        "power_cons_heating_kw",
        "Потребляемая мощность при обогреве",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.POWER,
        canonical_unit="kW",
        aliases=(
            "Номинальная потребляемая мощность (нагрев), Вт",
            "Потребляемая мощность, номинальная (Нагрев) кВт",
        ),
    ),
    "area_m2": _spec("area_m2", "Площадь", SpecValueType.QUANTITY, quantity_kind=QuantityKind.AREA, canonical_unit="m2"),
    "temp_range_cool": _spec(
        "temp_range_cool",
        "Рабочий диапазон температур при охлаждении",
        SpecValueType.RANGE,
        quantity_kind=QuantityKind.TEMPERATURE,
        canonical_unit="C",
        aliases=(
            "min_temp_cool",
            "Гарантированный диапазон рабочих температур (С) Охлаждение",
            "Температура наружного воздуха при охлаждении",
        ),
    ),
    "temp_range_heat": _spec(
        "temp_range_heat",
        "Рабочий диапазон температур при обогреве",
        SpecValueType.RANGE,
        quantity_kind=QuantityKind.TEMPERATURE,
        canonical_unit="C",
        aliases=(
            "min_temp_heat",
            "Температура наружного воздуха при обогреве",
        ),
    ),
    "airflow_max": _spec(
        "airflow_max",
        "Расход воздуха внутреннего блока",
        SpecValueType.NUMBER_LIST,
        quantity_kind=QuantityKind.AIRFLOW,
        canonical_unit="m3/h",
        aliases=(
            "Внутренний блок: Расход воздуха (высокая скорость), м 3 /ч",
            "Внутренний блок: Расход воздуха, м 3 /ч",
            "Расход воздуха, м 3 /ч",
        ),
    ),
    "noise_indoor": _spec(
        "noise_indoor",
        "Шум внутреннего блока",
        SpecValueType.NUMBER_LIST,
        quantity_kind=QuantityKind.NOISE,
        canonical_unit="dB",
    ),
    "noise_outdoor": _spec(
        "noise_outdoor",
        "Шум наружного блока",
        SpecValueType.NUMBER_LIST,
        quantity_kind=QuantityKind.NOISE,
        canonical_unit="dB",
        aliases=("Наружный блок: Уровень звукового давления, дБ, А",),
    ),
    "refrigerant_charge_g": _spec(
        "refrigerant_charge_g",
        "Заводская заправка хладагента",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.REFRIGERANT_MASS,
        canonical_unit="g",
        aliases=(
            "Заправка хладагента, кг",
            "Заводская заправка хладагента, кг",
            "Заводская заправка хладагента R410a (до 5 м)",
        ),
    ),
    "dehumidification_l_h": _spec(
        "dehumidification_l_h",
        "Удаление влаги",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.VOLUME_RATE,
        canonical_unit="l/h",
        aliases=("Удаление влаги, л/ч",),
    ),
    "energy_class": _spec(
        "energy_class",
        "Класс энергоэффективности",
        SpecValueType.TEXT,
        aliases=("Класс энергоэффективности (охлаждение/нагрев)",),
    ),
    "eer": _spec(
        "eer",
        "EER",
        SpecValueType.QUANTITY,
        aliases=("Энергоэффективность EER/COP",),
    ),
    "multi_max_indoor_units": _spec(
        "multi_max_indoor_units",
        "Максимальное количество внутренних блоков",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.COUNT,
        aliases=(
            "Максимальное количество подключаемых внутренних блоков",
            "Макс. количество внутренних блоков, шт",
        ),
    ),
    "pipe_max_height": _spec(
        "pipe_max_height",
        "Максимальный перепад высот",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.LENGTH,
        canonical_unit="m",
        aliases=("multi_max_height_diff",),
    ),
    "current_cooling_max_a": _spec(
        "current_cooling_max_a",
        "Максимальный рабочий ток при охлаждении",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.CURRENT,
        canonical_unit="A",
        aliases=("Максимальный уровень рабочего тока (охлаждение), А",),
    ),
    "multi_compat_mode": _spec(
        "multi_compat_mode",
        "Режим совместимости мульти-сплита",
        SpecValueType.ENUM,
        aliases=("multi_compat_mode",),
    ),
    "power_supply_voltage": _spec(
        "power_supply_voltage",
        "Напряжение питания",
        SpecValueType.TEXT,
        aliases=("Напряжение, В",),
    ),
    "power_supply_indoor": _spec(
        "power_supply_indoor",
        "Электропитание внутреннего блока",
        SpecValueType.TEXT,
        aliases=("Внутренний блок: Электропитание, Ф/В/Гц",),
    ),
    "power_supply_outdoor": _spec(
        "power_supply_outdoor",
        "Электропитание наружного блока",
        SpecValueType.TEXT,
        aliases=("Наружный блок: Электропитание, Ф/В/Гц",),
    ),
    "scop": _spec("scop", "SCOP", SpecValueType.QUANTITY, aliases=("SCOP", "scop")),
    "humidification": _spec("humidification", "Увлажнение воздуха", SpecValueType.BOOLEAN, aliases=("Увлажнение воздуха",)),
    "presence_sensor": _spec("presence_sensor", "Датчик присутствия", SpecValueType.BOOLEAN, aliases=("Датчик присутствия",)),
    "self_diagnosis": _spec("self_diagnosis", "Самодиагностика", SpecValueType.BOOLEAN, aliases=("Самодиагностика",)),
    "compressor_type": _spec("compressor_type", "Тип компрессора", SpecValueType.ENUM, aliases=("compressor_type",)),
    "cable_power": _spec("cable_power", "Кабель питания", SpecValueType.TEXT, aliases=("cable_power",)),
    "cable_interconnect": _spec("cable_interconnect", "Межблочный кабель", SpecValueType.TEXT, aliases=("cable_interconnect",)),
    "indoor_units_count": _spec(
        "indoor_units_count",
        "Количество внутренних блоков",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.COUNT,
        aliases=("Количество внутренних блоков",),
    ),
    "includes_indoor_unit": _spec("includes_indoor_unit", "Внутренний блок в комплекте", SpecValueType.BOOLEAN, aliases=("Внутренний блок",)),
    "includes_outdoor_unit": _spec("includes_outdoor_unit", "Наружный блок в комплекте", SpecValueType.BOOLEAN, aliases=("Наружный блок",)),
    "annual_energy_cooling_kwh": _spec(
        "annual_energy_cooling_kwh",
        "Годовое потребление энергии при охлаждении",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.ENERGY,
        canonical_unit="kWh/year",
        aliases=("Годовое потребление энергии (охлаждение), кВт/г.",),
    ),
    "annual_energy_heating_kwh": _spec(
        "annual_energy_heating_kwh",
        "Годовое потребление энергии при нагреве",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.ENERGY,
        canonical_unit="kWh/year",
        aliases=("Годовое потребление энергии (нагрев), кВт/г.",),
    ),
}


SPEC_DEFINITIONS = {
    **SPEC_DEFINITIONS,
    "airflow_direction": _spec("airflow_direction", "Регулировка направления потока", SpecValueType.BOOLEAN),
    "airflow_outdoor": _spec(
        "airflow_outdoor",
        "Расход воздуха наружного блока",
        SpecValueType.NUMBER_LIST,
        quantity_kind=QuantityKind.AIRFLOW,
        canonical_unit="m3/h",
    ),
    "autorestart": _spec("autorestart", "Авторестарт", SpecValueType.BOOLEAN),
    "availability": _spec("availability", "Наличие", SpecValueType.TEXT),
    "bio_filter": _spec("bio_filter", "Биофильтр", SpecValueType.BOOLEAN),
    "carbon_filter": _spec("carbon_filter", "Угольный фильтр", SpecValueType.BOOLEAN),
    "color": _spec("color", "Цвет", SpecValueType.TEXT),
    "compressor_brand": _spec(
        "compressor_brand",
        "Производитель компрессора",
        SpecValueType.ENUM,
        enum_values=("GMCC", "Toshiba", "Highly", "Panasonic", "Gree", "Mitsubishi"),
    ),
    "cop": _spec("cop", "COP", SpecValueType.QUANTITY),
    "country": _spec("country", "Страна производства", SpecValueType.TEXT),
    "current_cooling_nominal_a": _spec(
        "current_cooling_nominal_a",
        "Номинальный рабочий ток при охлаждении",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.CURRENT,
        canonical_unit="A",
    ),
    "current_heating_max_a": _spec(
        "current_heating_max_a",
        "Максимальный рабочий ток при обогреве",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.CURRENT,
        canonical_unit="A",
    ),
    "current_heating_nominal_a": _spec(
        "current_heating_nominal_a",
        "Номинальный рабочий ток при обогреве",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.CURRENT,
        canonical_unit="A",
    ),
    "dehumidification": _spec("dehumidification", "Режим осушения", SpecValueType.BOOLEAN),
    "depth_indoor": _spec(
        "depth_indoor",
        "Глубина внутреннего блока",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.LENGTH,
        canonical_unit="mm",
    ),
    "depth_outdoor": _spec(
        "depth_outdoor",
        "Глубина наружного блока",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.LENGTH,
        canonical_unit="mm",
    ),
    "dimensions_indoor_package_mm": _spec(
        "dimensions_indoor_package_mm",
        "Габариты внутреннего блока в упаковке",
        SpecValueType.TEXT,
        canonical_unit="mm",
    ),
    "dimensions_outdoor_package_mm": _spec(
        "dimensions_outdoor_package_mm",
        "Габариты наружного блока в упаковке",
        SpecValueType.TEXT,
        canonical_unit="mm",
    ),
    "drain_pipe_diameter": _spec(
        "drain_pipe_diameter",
        "Диаметр дренажной трубы",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.LENGTH,
        canonical_unit="mm",
    ),
    "electrostatic_filter": _spec("electrostatic_filter", "Электростатический фильтр", SpecValueType.BOOLEAN),
    "energy_class_cooling": _spec(
        "energy_class_cooling",
        "Класс энергоэффективности при охлаждении",
        SpecValueType.ENUM,
        enum_values=("A+++", "A++", "A+", "A", "B", "C", "D", "E"),
    ),
    "energy_class_heating": _spec(
        "energy_class_heating",
        "Класс энергоэффективности при обогреве",
        SpecValueType.ENUM,
        enum_values=("A+++", "A++", "A+", "A", "B", "C", "D", "E"),
    ),
    "fan_speed": _spec("fan_speed", "Регулировка скорости вентилятора", SpecValueType.BOOLEAN),
    "freon_type": _spec(
        "freon_type",
        "Хладагент",
        SpecValueType.ENUM,
        enum_values=("R32", "R410A", "R290", "R407C", "R134A"),
    ),
    "fresh_air": _spec("fresh_air", "Приток свежего воздуха", SpecValueType.BOOLEAN),
    "height_indoor": _spec(
        "height_indoor",
        "Высота внутреннего блока",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.LENGTH,
        canonical_unit="mm",
    ),
    "height_outdoor": _spec(
        "height_outdoor",
        "Высота наружного блока",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.LENGTH,
        canonical_unit="mm",
    ),
    "installation_orientation": _spec(
        "installation_orientation",
        "Ориентация установки",
        SpecValueType.ENUM,
        enum_values=("wall", "floor", "ceiling", "floor_ceiling", "cassette", "duct"),
    ),
    "inverter_type": _spec(
        "inverter_type",
        "Тип управления компрессором",
        SpecValueType.ENUM,
        enum_values=("inverter", "on_off", "full_dc"),
    ),
    "ionizer": _spec("ionizer", "Ионизатор", SpecValueType.BOOLEAN),
    "modes": _spec("modes", "Режимы работы", SpecValueType.TEXT),
    "multi_max_total_pipe_length": _spec(
        "multi_max_total_pipe_length",
        "Максимальная суммарная длина магистрали",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.LENGTH,
        canonical_unit="m",
    ),
    "photocatalytic_filter": _spec("photocatalytic_filter", "Фотокаталитический фильтр", SpecValueType.BOOLEAN),
    "pipe_gas": _spec(
        "pipe_gas",
        "Диаметр газовой трубы",
        SpecValueType.ENUM,
        enum_values=('1/4"', '3/8"', '1/2"', '5/8"', '3/4"'),
    ),
    "pipe_liquid": _spec(
        "pipe_liquid",
        "Диаметр жидкостной трубы",
        SpecValueType.ENUM,
        enum_values=('1/4"', '3/8"', '1/2"', '5/8"', '3/4"'),
    ),
    "pipe_max_length": _spec(
        "pipe_max_length",
        "Максимальная длина магистрали",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.LENGTH,
        canonical_unit="m",
    ),
    "plasma_filter": _spec("plasma_filter", "Плазменный фильтр", SpecValueType.BOOLEAN),
    "power_cons_cooling_max_kw": _spec(
        "power_cons_cooling_max_kw",
        "Максимальная потребляемая мощность при охлаждении",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.POWER,
        canonical_unit="kW",
    ),
    "power_cons_cooling_min_kw": _spec(
        "power_cons_cooling_min_kw",
        "Минимальная потребляемая мощность при охлаждении",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.POWER,
        canonical_unit="kW",
    ),
    "power_cons_heating_max_kw": _spec(
        "power_cons_heating_max_kw",
        "Максимальная потребляемая мощность при обогреве",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.POWER,
        canonical_unit="kW",
    ),
    "power_cons_heating_min_kw": _spec(
        "power_cons_heating_min_kw",
        "Минимальная потребляемая мощность при обогреве",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.POWER,
        canonical_unit="kW",
    ),
    "power_supply": _spec("power_supply", "Электропитание", SpecValueType.TEXT),
    "power_supply_location": _spec(
        "power_supply_location",
        "Подключение питания",
        SpecValueType.ENUM,
        enum_values=("indoor", "outdoor", "left", "right", "any"),
    ),
    "refrigerant_additional_g_m": _spec(
        "refrigerant_additional_g_m",
        "Дополнительная заправка хладагента",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.REFRIGERANT_MASS,
        canonical_unit="g/m",
    ),
    "remote_control": _spec("remote_control", "Пульт ДУ", SpecValueType.BOOLEAN),
    "seer": _spec("seer", "SEER", SpecValueType.QUANTITY),
    "self_cleaning": _spec("self_cleaning", "Самоочистка", SpecValueType.BOOLEAN),
    "sku_list": _spec("sku_list", "Артикулы товара", SpecValueType.TEXT),
    "sleep_mode": _spec("sleep_mode", "Ночной режим", SpecValueType.BOOLEAN),
    "smart_home_integration": _spec("smart_home_integration", "Интеграция в умный дом", SpecValueType.BOOLEAN),
    "timer": _spec("timer", "Таймер", SpecValueType.BOOLEAN),
    "turbo_mode": _spec("turbo_mode", "Турбо-режим", SpecValueType.BOOLEAN),
    "uv_sterilization": _spec("uv_sterilization", "Ультрафиолетовое обеззараживание", SpecValueType.BOOLEAN),
    "voice_control": _spec("voice_control", "Голосовое управление", SpecValueType.BOOLEAN),
    "warranty_months": _spec(
        "warranty_months",
        "Гарантия",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.COUNT,
        canonical_unit="month",
    ),
    "weight_indoor": _spec(
        "weight_indoor",
        "Вес внутреннего блока",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.WEIGHT,
        canonical_unit="kg",
    ),
    "weight_indoor_package": _spec(
        "weight_indoor_package",
        "Вес внутреннего блока в упаковке",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.WEIGHT,
        canonical_unit="kg",
    ),
    "weight_outdoor": _spec(
        "weight_outdoor",
        "Вес наружного блока",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.WEIGHT,
        canonical_unit="kg",
    ),
    "weight_outdoor_package": _spec(
        "weight_outdoor_package",
        "Вес наружного блока в упаковке",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.WEIGHT,
        canonical_unit="kg",
    ),
    "width_indoor": _spec(
        "width_indoor",
        "Ширина внутреннего блока",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.LENGTH,
        canonical_unit="mm",
    ),
    "width_outdoor": _spec(
        "width_outdoor",
        "Ширина наружного блока",
        SpecValueType.QUANTITY,
        quantity_kind=QuantityKind.LENGTH,
        canonical_unit="mm",
    ),
    "winter_kit": _spec("winter_kit", "Зимний комплект", SpecValueType.TEXT),
}


REGISTRY_HELP_TEXTS: Mapping[str, tuple[str | None, str | None]] = {
    "type": ("Общий тип системы: бытовая сплит-система, мульти-сплит или отдельный блок.", None),
    "indoor_type": (
        "Форм-фактор внутреннего блока. Используется для фильтров полупромышленных и мульти-сплит систем.",
        None,
    ),
    "inverter": (
        "Инверторный компрессор плавно меняет производительность и обычно точнее держит температуру.",
        "Не путать с маркетинговыми режимами энергосбережения: здесь фиксируется именно тип управления компрессором.",
    ),
    "wifi_ready": (
        "Совместимое поле Wi-Fi: встроенный модуль, подготовка под модуль или отсутствие поддержки.",
        "Для новой логики предпочтительнее смотреть wifi_state и wifi_builtin.",
    ),
    "capacity_cooling_kw": (
        "Номинальная холодопроизводительность. У инверторных моделей фактическая мощность может плавать в диапазоне min/max.",
        None,
    ),
    "capacity_heating_kw": (
        "Номинальная теплопроизводительность. При низкой наружной температуре реальная мощность может снижаться.",
        None,
    ),
    "capacity_cooling_min_kw": ("Минимальная холодопроизводительность инвертора в устойчивом режиме.", None),
    "capacity_cooling_max_kw": ("Максимальная холодопроизводительность, которую модель может кратковременно или штатно выдать.", None),
    "capacity_heating_min_kw": ("Минимальная теплопроизводительность инвертора в устойчивом режиме.", None),
    "capacity_heating_max_kw": ("Максимальная теплопроизводительность, обычно важна при подборе на холодный период.", None),
    "power_cons_cooling_kw": (
        "Номинальная электрическая мощность потребления в режиме охлаждения, не путать с холодопроизводительностью.",
        None,
    ),
    "power_cons_heating_kw": (
        "Номинальная электрическая мощность потребления в режиме обогрева, не равна теплопроизводительности.",
        None,
    ),
    "area_m2": (
        "Рекомендованная площадь помещения. Это ориентир для подбора, а не замена теплотехнического расчета.",
        None,
    ),
    "temp_range_cool": ("Допустимый диапазон наружной температуры для работы в режиме охлаждения.", None),
    "temp_range_heat": ("Допустимый диапазон наружной температуры для работы в режиме обогрева.", None),
    "airflow_max": (
        "Расход воздуха внутреннего блока. Может быть одним числом или списком по скоростям вентилятора.",
        None,
    ),
    "noise_indoor": (
        "Уровень шума внутреннего блока. Часто поставщики дают список значений по скоростям вентилятора.",
        None,
    ),
    "noise_outdoor": ("Уровень шума наружного блока, обычно важен для плотной городской застройки.", None),
    "energy_class": ("Класс энергоэффективности, если источник не разделяет охлаждение и обогрев.", None),
    "energy_class_cooling": ("Класс энергоэффективности в режиме охлаждения.", None),
    "energy_class_heating": ("Класс энергоэффективности в режиме обогрева.", None),
    "eer": (
        "Коэффициент эффективности охлаждения: отношение холодопроизводительности к потребляемой мощности.",
        None,
    ),
    "cop": (
        "Коэффициент эффективности обогрева: отношение теплопроизводительности к потребляемой мощности.",
        None,
    ),
    "seer": ("Сезонный коэффициент эффективности охлаждения по методике производителя/стандарта.", None),
    "scop": ("Сезонный коэффициент эффективности обогрева по методике производителя/стандарта.", None),
    "pipe_max_length": ("Максимально допустимая длина трассы между блоками.", None),
    "pipe_max_height": ("Максимально допустимый перепад высот между внутренним и наружным блоком.", None),
    "multi_max_total_pipe_length": ("Максимальная суммарная длина трасс для мульти-сплит системы.", None),
    "pipe_liquid": ("Диаметр жидкостной фреоновой трубы, обычно указывается в дюймах.", None),
    "pipe_gas": ("Диаметр газовой фреоновой трубы, обычно указывается в дюймах.", None),
    "freon_type": ("Тип хладагента: например R32, R410A или другой.", None),
    "refrigerant_charge_g": (
        "Заводская заправка хладагента. Используется для оценки монтажа и дозаправки трассы.",
        None,
    ),
    "refrigerant_additional_g_m": (
        "Норма дополнительной заправки хладагента на каждый метр сверх базовой длины трассы.",
        None,
    ),
    "dehumidification_l_h": ("Производительность осушения воздуха в литрах в час.", None),
    "width_indoor": ("Ширина внутреннего блока без упаковки.", None),
    "height_indoor": ("Высота внутреннего блока без упаковки.", None),
    "depth_indoor": ("Глубина внутреннего блока без упаковки.", None),
    "width_outdoor": ("Ширина наружного блока без упаковки.", None),
    "height_outdoor": ("Высота наружного блока без упаковки.", None),
    "depth_outdoor": ("Глубина наружного блока без упаковки.", None),
    "weight_indoor": ("Вес внутреннего блока без упаковки.", None),
    "weight_outdoor": ("Вес наружного блока без упаковки.", None),
    "current_cooling_max_a": ("Максимальный рабочий ток в режиме охлаждения.", None),
    "current_heating_max_a": ("Максимальный рабочий ток в режиме обогрева.", None),
    "power_supply": ("Общее описание электропитания: фаза, напряжение и частота.", None),
    "power_supply_location": ("Где подключается питание: к внутреннему или наружному блоку, либо сторона подключения.", None),
    "warranty_months": ("Гарантийный срок в месяцах.", None),
    "airflow_direction": ("Наличие регулировки направления воздушного потока.", None),
    "airflow_outdoor": ("Расход воздуха наружного блока, если поставщик указывает его отдельно.", None),
    "annual_energy_cooling_kwh": ("Расчетное годовое потребление электроэнергии в режиме охлаждения.", None),
    "annual_energy_heating_kwh": ("Расчетное годовое потребление электроэнергии в режиме обогрева.", None),
    "autorestart": ("Автоматический перезапуск после пропадания и восстановления питания.", None),
    "availability": ("Текстовый статус наличия из источника или менеджера.", None),
    "bio_filter": ("Наличие биофильтра или аналогичного фильтрующего элемента.", None),
    "brand": ("Производитель или бренд товара.", None),
    "cable_interconnect": ("Рекомендуемый или требуемый межблочный кабель.", None),
    "cable_power": ("Рекомендуемый или требуемый кабель питания.", None),
    "carbon_filter": ("Наличие угольного фильтра.", None),
    "color": ("Основной цвет корпуса или блока.", None),
    "compressor_brand": ("Производитель компрессора, если источник указывает его отдельно.", None),
    "compressor_type": ("Тип компрессора или схема управления компрессором.", None),
    "country": ("Страна производства или сборки по данным источника.", None),
    "current_cooling_nominal_a": ("Номинальный рабочий ток в режиме охлаждения.", None),
    "current_heating_nominal_a": ("Номинальный рабочий ток в режиме обогрева.", None),
    "dehumidification": ("Наличие режима осушения воздуха.", None),
    "dimensions_indoor_package_mm": ("Габариты внутреннего блока в упаковке.", None),
    "dimensions_outdoor_package_mm": ("Габариты наружного блока в упаковке.", None),
    "drain_pipe_diameter": ("Диаметр дренажной трубы или патрубка.", None),
    "electrostatic_filter": ("Наличие электростатического фильтра.", None),
    "fan_speed": ("Наличие регулировки скорости вентилятора.", None),
    "fresh_air": ("Наличие функции или канала притока свежего воздуха.", None),
    "humidification": ("Наличие функции увлажнения воздуха.", None),
    "includes_indoor_unit": ("Признак, что внутренний блок входит в комплект поставки.", None),
    "includes_outdoor_unit": ("Признак, что наружный блок входит в комплект поставки.", None),
    "indoor_units_count": ("Количество внутренних блоков в комплекте или системе.", None),
    "installation_orientation": ("Допустимая ориентация установки блока.", None),
    "inverter_type": ("Уточнение типа инверторного или неинверторного управления компрессором.", None),
    "ionizer": ("Наличие ионизатора воздуха.", None),
    "model": ("Модель товара в каталоге или источнике.", None),
    "model_indoor": ("Модель внутреннего блока.", None),
    "model_outdoor": ("Модель наружного блока.", None),
    "modes": ("Перечень режимов работы: охлаждение, обогрев, осушение, вентиляция и другие.", None),
    "multi_compat_mode": ("Режим или правило совместимости для мульти-сплит системы.", None),
    "multi_max_indoor_units": ("Максимальное количество внутренних блоков, подключаемых к наружному блоку.", None),
    "photocatalytic_filter": ("Наличие фотокаталитического фильтра.", None),
    "plasma_filter": ("Наличие плазменного фильтра или плазменной очистки.", None),
    "power_cons_cooling_max_kw": ("Максимальная электрическая мощность потребления при охлаждении.", None),
    "power_cons_cooling_min_kw": ("Минимальная электрическая мощность потребления при охлаждении.", None),
    "power_cons_heating_max_kw": ("Максимальная электрическая мощность потребления при обогреве.", None),
    "power_cons_heating_min_kw": ("Минимальная электрическая мощность потребления при обогреве.", None),
    "power_supply_indoor": ("Электропитание внутреннего блока, если оно указано отдельно.", None),
    "power_supply_outdoor": ("Электропитание наружного блока, если оно указано отдельно.", None),
    "power_supply_voltage": ("Напряжение или параметры питающей сети.", None),
    "presence_sensor": ("Наличие датчика присутствия или движения.", None),
    "release_year": ("Дата выхода модели на рынок по данным источника.", None),
    "remote_control": ("Наличие пульта дистанционного управления в комплекте.", None),
    "self_cleaning": ("Наличие функции самоочистки внутреннего блока или теплообменника.", None),
    "self_diagnosis": ("Наличие функции самодиагностики ошибок.", None),
    "series": ("Серия или линейка модели.", None),
    "sku": ("Артикул товара.", None),
    "sku_list": ("Список артикулов, если комплект или источник содержит несколько позиций.", None),
    "sleep_mode": ("Наличие ночного режима или режима сна.", None),
    "smart_home_integration": ("Наличие интеграции с умным домом или внешними системами управления.", None),
    "timer": ("Наличие таймера включения или выключения.", None),
    "turbo_mode": ("Наличие турбо-режима для быстрого охлаждения или обогрева.", None),
    "uv_sterilization": ("Наличие ультрафиолетового обеззараживания.", None),
    "voice_control": ("Наличие голосового управления.", None),
    "weight_indoor_package": ("Вес внутреннего блока в упаковке.", None),
    "weight_outdoor_package": ("Вес наружного блока в упаковке.", None),
    "wifi_builtin": ("Признак встроенного Wi-Fi модуля.", None),
    "winter_kit": ("Сведения о зимнем комплекте или низкотемпературном исполнении.", None),
}

SPEC_DEFINITIONS = {
    key: replace(
        spec,
        description=REGISTRY_HELP_TEXTS.get(key, (None, None))[0] or spec.description,
        manager_note=REGISTRY_HELP_TEXTS.get(key, (None, None))[1] or spec.manager_note,
    )
    for key, spec in SPEC_DEFINITIONS.items()
}


REGISTRY_LEGACY_ALIASES_BY_KEY: Mapping[str, tuple[str, ...]] = {
    'airflow_direction': (
        'Регулировка направления воздушного потока',
    ),
    'airflow_max': (
        'Максимальный расход воздуха внутреннего блока',
        'Расход воздуха (высокая скорость), м 3 /ч',
        'Расход воздуха внутреннего блока',
        'Внутренний блок: Расход воздуха (высокая скорость), м 3 /ч',
        'Внутренний блок: Расход воздуха, м 3 /ч',
        'Расход воздуха, м 3 /ч',
    ),
    'airflow_outdoor': (
        'Расход воздуха наружного блока',
    ),
    'annual_energy_cooling_kwh': (
        'Годовое потребление энергии (охлаждение), кВт/г.',
    ),
    'annual_energy_heating_kwh': (
        'Годовое потребление энергии (нагрев), кВт/г.',
    ),
    'area_m2': (
        'Обслуживаемая площадь',
        'Обслуживаемая площадь, кв.м',
        'Площадь охлаждения',
        'Площадь помещения',
        'Обслуживаемая площадь до',
        'Обслуживаемая площадь до, м2',
        'Рекомендуемая максимальная площадь помещения',
        'Рекомендованная площадь, м 2',
    ),
    'autorestart': (
        'Авторестарт после пропадания питания',
        'Авторестарт',
    ),
    'availability': (
        'Наличие',
    ),
    'bio_filter': (
        'Биофильтр',
    ),
    'brand': (
        'Бренд',
        'Марка',
        'Производитель',
    ),
    'cable_interconnect': (
        'cable_interconnect',
    ),
    'cable_power': (
        'cable_power',
    ),
    'capacity_cooling_kw': (
        'Мощность охлаждения',
        'Мощность охлаждения, кВт',
        'Мощность охлаждения (Мин/Ном/Макс), кВт',
        'Мощность в режиме охлаждения',
        'Мощность в режиме охлаждения, кВт',
        'Холодопроизводительность',
        'Охлаждение, кВт',
    ),
    'capacity_cooling_max_kw': (
        'Охлаждение максимум, кВт',
        'Охлаждение максимум, Вт',
    ),
    'capacity_cooling_min_kw': (
        'Охлаждение минимум, кВт',
        'Охлаждение минимум, Вт',
    ),
    'capacity_heating_kw': (
        'Мощность обогрева',
        'Мощность обогрева, кВт',
        'Мощность нагрева (Мин/Ном/Макс), кВт',
        'Мощность в режиме обогрева',
        'Мощность в режиме обогрева, кВт',
        'Теплопроизводительность',
        'Нагрев, кВт',
    ),
    'capacity_heating_max_kw': (
        'Нагрев максимум, кВт',
        'Нагрев максимум, Вт',
    ),
    'capacity_heating_min_kw': (
        'Нагрев минимум, кВт',
        'Нагрев минимум, Вт',
    ),
    'carbon_filter': (
        'Угольный фильтр',
    ),
    'color': (
        'Цвет',
        'Цвет корпуса',
    ),
    'compressor_brand': (
        'Производитель компрессора',
        'Компрессор: Производитель компрессора',
    ),
    'compressor_type': (
        'compressor_type',
    ),
    'cop': (
        'Энергоэффективность при обогреве (COP)',
        'COP',
        'Энергоэффективность SCOP/COP',
        'COP (коэффициент / класс)',
    ),
    'country': (
        'Страна производства',
    ),
    'current_cooling_max_a': (
        'Максимальный рабочий ток, охлаждение',
        'Максимальный уровень рабочего тока (охлаждение), А',
    ),
    'current_cooling_nominal_a': (
        'Номинальный уровень рабочего тока (охлаждение), А',
    ),
    'current_heating_max_a': (
        'Максимальный рабочий ток, обогрев',
    ),
    'current_heating_nominal_a': (
        'Номинальный уровень рабочего тока (нагрев), А',
    ),
    'dehumidification': (
        'Осушение воздуха',
        'Режим осушения воздуха',
    ),
    'dehumidification_l_h': (
        'Осушение',
        'Удаление влаги, л/ч',
    ),
    'depth_indoor': (
        'Глубина внутреннего блока',
    ),
    'depth_outdoor': (
        'Глубина наружного блока',
    ),
    'dimensions_indoor_package_mm': (
        'Внутренний блок: Габаритные размеры в упаковке (Ш/Г/В), мм',
        'Размеры внутреннего блока в упаковке (Ш х В х Г)',
    ),
    'dimensions_outdoor_package_mm': (
        'Наружный блок: Габаритные размеры в упаковке (Ш/Г/В), мм',
        'Размеры наружного блока в упаковке (Ш х В х Г)',
        'Габаритные размеры в упаковке (Ш/Г/В), мм',
    ),
    'drain_pipe_diameter': (
        'Диаметр дренажной трубы: мм (дюйм)',
    ),
    'eer': (
        'Энергоэффективность при охлаждении (EER)',
        'EER',
        'EER/COP',
        'Коэффициент энергоэффективности (EER / COP)',
        'Энергоэффективность SEER/EER',
        'EER (коэффициент / класс)',
        'Энергоэффективность EER/COP',
    ),
    'electrostatic_filter': (
        'Электростатический фильтр',
    ),
    'energy_class': (
        'Класс энергоэффективности',
        'Класс эффективности',
        'Класс энергоэффективности (Холод / Тепло)',
        'Класс энергоэффективности (охлаждение/нагрев)',
    ),
    'energy_class_cooling': (
        'Класс энергоэффективности при охлаждении',
        'Энергоэффективность при охлаждении',
    ),
    'energy_class_heating': (
        'Класс энергоэффективности при обогреве',
        'Энергоэффективность при обогреве',
    ),
    'fan_speed': (
        'Регулировка скорости вращения вентилятора',
        'Регулятор скорости вращения вентилятора',
    ),
    'freon_type': (
        'Хладагент (фреон)',
        'Хладагент',
        'Тип хладагента',
        'Марка используемого хладагента',
    ),
    'fresh_air': (
        'Приток свежего воздуха',
    ),
    'height_indoor': (
        'Высота внутреннего блока',
    ),
    'height_outdoor': (
        'Высота наружного блока',
    ),
    'humidification': (
        'Увлажнение воздуха',
    ),
    'includes_indoor_unit': (
        'Внутренний блок',
    ),
    'includes_outdoor_unit': (
        'Наружный блок',
    ),
    'indoor_type': (
        'Тип внутреннего блока',
    ),
    'indoor_units_count': (
        'Количество внутренних блоков',
    ),
    'installation_orientation': (
        'Установка',
    ),
    'inverter': (
        'Тип системы',
        'Инверторная технология',
        'Инверторный',
        'Инверторное управление',
        'Инверторное управление мощностью',
        'Инверторный компрессор',
        'Неинверторный компрессор',
        'Компрессор: Неинверторный компрессор',
        'Компрессор: Инверторный компрессор',
    ),
    'inverter_type': (
        'Тип управления компрессором',
    ),
    'ionizer': (
        'Ионизатор',
        'Ионизация',
    ),
    'model': (
        'Модель',
    ),
    'model_indoor': (
        'Модель внутреннего блока',
    ),
    'model_outdoor': (
        'Модель наружного блока',
    ),
    'modes': (
        'Режим работы',
        'Режимы работы',
    ),
    'multi_compat_mode': (
        'multi_compat_mode',
    ),
    'multi_max_indoor_units': (
        'Максимальное количество внутренних блоков',
        'Максимальное количество подключаемых внутренних блоков',
        'Макс. количество внутренних блоков, шт',
    ),
    'multi_max_total_pipe_length': (
        'Максимальная суммарная длина магистрали',
    ),
    'noise_indoor': (
        'Шум внутреннего блока',
        'Шум внутреннего блока, дБ',
        'Уровень шума внутреннего блока',
        'Уровень шума (макс), дБ',
        'Уровень звукового давления [дБ(А)], Выс/Ср/Низ/Сверх',
        'Уровень шума в режиме ОХЛАЖДЕНИЯ (Тих / Низ / Ср /Макс), дБ',
        'Уровень шума в режиме НАГРЕВА (Низ / Ср / Макс), дБ',
        'Внутренний блок: Уровень звукового давления [дБ(А)], Выс/Ср/Низ/Сверх',
        'Уровень звукового давления внутреннего блока',
    ),
    'noise_outdoor': (
        'Шум наружного блока',
        'Шум наружного блока, дБ',
        'Шум внешнего блока',
        'Шум внешнего блока, дБ',
        'Уровень шума наружного блока',
        'Уровень шума наружного блока, дБ',
        'Уровень звукового давления, дБ, А',
        'Уровень звукового давления (высокая скорость), дБ, А',
        'Наружный блок: Уровень звукового давления (высокая скорость), дБ, А',
        'Уровень звукового давления наружного блока',
        'Наружный блок: Уровень звукового давления, дБ, А',
    ),
    'photocatalytic_filter': (
        'Фотокаталитический фильтр',
    ),
    'pipe_gas': (
        'Диаметр газовой трубы',
        'Диаметр газовой линии, мм',
        'Диаметр труб газообразного хладагента, мм',
    ),
    'pipe_liquid': (
        'Диаметр жидкостной трубы',
        'Диаметр жидкостной линии, мм',
        'Диаметр труб жидкого хладагента, мм',
    ),
    'pipe_max_height': (
        'Перепад высот',
        'Перепад высот, м',
        'Максимальный перепад высот',
        'multi_max_height_diff',
    ),
    'pipe_max_length': (
        'Максимальная длина магистрали',
        'Максимальная длина коммуникаций',
        'Максимальная длина коммуникаций, м',
        'Максимальная длина фреонопровода',
        'Макс. длина трассы',
        'Макс. длина трубопроводов без дополнительной заправки, м',
        'Максимальная длина/перепад высот, м',
        'Максимальная длина/перепад высот, при использовании только в режиме охлаждения, м',
    ),
    'plasma_filter': (
        'Плазменный фильтр',
    ),
    'power_cons_cooling_kw': (
        'Потребляемая мощность при охлаждении',
        'Потребляемая мощность при охлаждении, кВт',
        'Потребляемая мощность, охлаждение',
        'Потребление электроэнергии в режиме охлаждения (Мин / Ном / Макс), кВт',
        'Номинальная потребляемая мощность (охлаждение), кВт',
        'Номинальная потребляемая мощность (охлаждение), Вт',
        'Потребляемая мощность, номинальная (Охлаждение) кВт',
    ),
    'power_cons_cooling_max_kw': (
        'Максимальная потребляемая мощность (охлаждение), кВт',
    ),
    'power_cons_cooling_min_kw': (
        'Минимальная потребляемая мощность (охлаждение), кВт',
    ),
    'power_cons_heating_kw': (
        'Потребляемая мощность при обогреве',
        'Потребляемая мощность при обогреве, кВт',
        'Потребляемая мощность, обогрев',
        'Потребление электроэнергии в режиме нагрева (Мин / Ном / Макс), кВт',
        'Номинальная потребляемая мощность (нагрев), кВт',
        'Номинальная потребляемая мощность (нагрев), Вт',
        'Потребляемая мощность, номинальная (Нагрев) кВт',
    ),
    'power_cons_heating_max_kw': (
        'Максимальная потребляемая мощность (нагрев), кВт',
    ),
    'power_cons_heating_min_kw': (
        'Минимальная потребляемая мощность (нагрев), кВт',
    ),
    'power_supply': (
        'Электропитание',
        'Электропитание, Ф/В/Гц',
        'Электропитание (Ø / В / Гц)',
    ),
    'power_supply_indoor': (
        'Внутренний блок: Электропитание, Ф/В/Гц',
    ),
    'power_supply_location': (
        'Подача питания',
        'Подключение питания',
        'Сторона подключения',
    ),
    'power_supply_outdoor': (
        'Наружный блок: Электропитание, Ф/В/Гц',
    ),
    'power_supply_voltage': (
        'Параметры питающей сети',
        'Напряжение, В',
    ),
    'presence_sensor': (
        'Датчик присутствия',
    ),
    'refrigerant_additional_g_m': (
        'Дополнительная заправка (г/м)',
        'Дополнительная заправка хладагента',
    ),
    'refrigerant_charge_g': (
        'Заводская заправка хладагента',
        'Вес заправляемого хладагента, г',
        'Заправка хладагента, кг',
        'Заводская заправка хладагента, кг',
        'Заводская заправка хладагента R410a (до 5 м)',
    ),
    'release_year': (
        'Дата выхода на рынок',
    ),
    'remote_control': (
        'Пульт дистанционного управления',
        'Пульт ДУ',
        'Пульт',
        'Пульт управления',
        'Пульт управления в комплекте',
        'Внутренний блок: Пульт управления',
    ),
    'scop': (
        'SCOP',
        'scop',
    ),
    'seer': (
        'SEER (коэффициент/класс)',
    ),
    'self_cleaning': (
        'Самоочистка',
        'Автоочистка теплообменника',
    ),
    'self_diagnosis': (
        'Самодиагностика',
    ),
    'series': (
        'Серия',
        'Линейка',
        'Модельный ряд',
    ),
    'sku': (
        'Артикул',
        'Артикул товара',
    ),
    'sku_list': (
        'Артикулы товара',
    ),
    'sleep_mode': (
        'Режим «Сон»',
        'Ночной режим',
    ),
    'smart_home_integration': (
        'Интеграция в "умный дом"',
    ),
    'temp_range_cool': (
        'Рабочая температура при охлаждении',
        'Рабочий диапазон температур при охлаждении',
        'Рабочий диапазон температур при охлаждении,°C',
        'Рабочий диапазон температур при охлаждении, °C',
        'Гарантированный диапазон рабочих t° наружного воздуха, охлаждение',
        'Охлаждение, °С',
        'min_temp_cool',
        'Гарантированный диапазон рабочих температур (С) Охлаждение',
        'Температура наружного воздуха при охлаждении',
    ),
    'temp_range_heat': (
        'Рабочая температура при обогреве',
        'Рабочий диапазон температур при обогреве',
        'Рабочий диапазон температур при обогреве,°C',
        'Рабочий диапазон температур при обогреве, °C',
        'Гарантированный диапазон рабочих t° наружного воздуха, обогрев',
        'Нагрев, °С',
        'Минимальная температура наружного воздуха',
        'Мин. температура (обогрев)',
        'min_temp_heat',
        'Температура наружного воздуха при обогреве',
    ),
    'timer': (
        'Таймер включения/выключения',
        'Таймер',
    ),
    'turbo_mode': (
        'Турбо-режим',
        'Турбо режим',
    ),
    'type': (
        'Тип',
        'Тип кондиционера',
    ),
    'uv_sterilization': (
        'Обеззараживание ультрафиолетом',
    ),
    'voice_control': (
        'Голосовое управление',
    ),
    'warranty_months': (
        'Гарантия',
    ),
    'weight_indoor': (
        'Вес внутреннего блока',
        'Вес внутреннего блока, кг',
        'Чистый вес / Вес в упаковке, кг',
        'Внутренний блок: Чистый вес / Вес в упаковке, кг',
        'Внутренний блок без упаковки, кг',
        'Вес внутреннего блока без упаковки',
    ),
    'weight_indoor_package': (
        'Вес внутреннего блока в упаковке',
    ),
    'weight_outdoor': (
        'Вес наружного блока',
        'Вес наружного блока, кг',
        'Вес внешнего блока',
        'Вес внешнего блока, кг',
        'Чистый вес / вес в упаковке, кг',
        'Наружный блок: Чистый вес / вес в упаковке, кг',
        'Наружный блок: Чистый вес / Вес в упаковке, кг',
        'Наружный блок без упаковки, кг',
        'Вес наружного блока без упаковки',
    ),
    'weight_outdoor_package': (
        'Вес наружного блока в упаковке',
    ),
    'width_indoor': (
        'Ширина внутреннего блока',
    ),
    'width_outdoor': (
        'Ширина наружного блока',
    ),
    'wifi_ready': (
        'Wi-Fi',
        'Wi-Fi модуль',
        'Wi-Fi module',
        'Wi-Fi Ready',
        'Вайфай',
        'Wi-Fi управление',
    ),
    'winter_kit': (
        'Зимний комплект',
    ),
}


def _flatten_aliases(aliases_by_key: Mapping[str, Iterable[str]]) -> dict[str, str]:
    flattened: dict[str, str] = {}
    for key, aliases in aliases_by_key.items():
        if key not in SPEC_DEFINITIONS:
            raise RuntimeError(f"Spec alias group points to unknown spec key: {key}")
        for alias in aliases:
            current = flattened.get(alias)
            if current is not None and current != key:
                raise RuntimeError(f"Spec alias conflict for {alias!r}: {current!r} vs {key!r}")
            flattened[alias] = key
    return flattened


_SPEC_ALIASES_BY_KEY: dict[str, tuple[str, ...]] = {
    spec.key: spec.aliases for spec in SPEC_DEFINITIONS.values() if spec.aliases
}

REGISTRY_KEY_MAP: dict[str, str] = _flatten_aliases({
    **REGISTRY_LEGACY_ALIASES_BY_KEY,
    **{
        key: tuple(dict.fromkeys((*REGISTRY_LEGACY_ALIASES_BY_KEY.get(key, ()), *aliases)))
        for key, aliases in _SPEC_ALIASES_BY_KEY.items()
    },
})


def _aliases_for_key(key: str) -> list[str]:
    aliases = REGISTRY_LEGACY_ALIASES_BY_KEY.get(key, ())
    spec_aliases = SPEC_DEFINITIONS[key].aliases if key in SPEC_DEFINITIONS else ()
    return list(dict.fromkeys((*aliases, *spec_aliases)))

REGISTRY_DIMENSIONS_MAP: dict[str, tuple[str, str, str]] = {
    "Габариты внутреннего блока (ШхВхГ)": ("width_indoor", "height_indoor", "depth_indoor"),
    "Габариты внутреннего блока (ШхВхГ), мм": ("width_indoor", "height_indoor", "depth_indoor"),
    "Габариты наружного блока (ШхВхГ)": ("width_outdoor", "height_outdoor", "depth_outdoor"),
    "Габариты наружного блока (ШхВхГ), мм": ("width_outdoor", "height_outdoor", "depth_outdoor"),
    "Габариты внешнего блока (ШхВхГ)": ("width_outdoor", "height_outdoor", "depth_outdoor"),
    "Габариты внешнего блока (ШхВхГ), мм": ("width_outdoor", "height_outdoor", "depth_outdoor"),
    "Габариты мм": ("width_indoor", "height_indoor", "depth_indoor"),
    "Габаритные размеры без упаковки (Ш/Г/В), мм": ("width_indoor", "depth_indoor", "height_indoor"),
    "Внутренний блок: Габаритные размеры без упаковки (Ш/Г/В), мм": ("width_indoor", "depth_indoor", "height_indoor"),
    "Наружный блок: Габаритные размеры без упаковки (Ш/Г/В), мм": ("width_outdoor", "depth_outdoor", "height_outdoor"),
    "Внутренний блок без упаковки (Ш × В × Г), мм": ("width_indoor", "height_indoor", "depth_indoor"),
    "Наружный блок без упаковки (Ш × В × Г), мм": ("width_outdoor", "height_outdoor", "depth_outdoor"),
    "Размеры внутреннего блока без упаковки (Ш х В х Г)": ("width_indoor", "height_indoor", "depth_indoor"),
    "Размеры наружного блока без упаковки (Ш х В х Г)": ("width_outdoor", "height_outdoor", "depth_outdoor"),
    "Размеры внутреннего блока без упаковки (Ш x В x Г)": ("width_indoor", "height_indoor", "depth_indoor"),
    "Размеры наружного блока без упаковки (Ш x В x Г)": ("width_outdoor", "height_outdoor", "depth_outdoor"),
}

REGISTRY_UNORDERED_DIMENSION_KEYS: frozenset[str] = frozenset(
    {
        "Размеры внутреннего блока без упаковки (Ш х В х Г)",
        "Размеры наружного блока без упаковки (Ш х В х Г)",
        "Размеры внутреннего блока без упаковки (Ш x В x Г)",
        "Размеры наружного блока без упаковки (Ш x В x Г)",
    }
)


_NOMINAL_FROM_TRIPLET_KEYS = {
    "capacity_cooling_kw",
    "capacity_heating_kw",
    "power_cons_cooling_kw",
    "power_cons_heating_kw",
}

_TRIPLET_COMPANION_KEYS = {
    "capacity_cooling_kw": ("capacity_cooling_min_kw", "capacity_cooling_max_kw"),
    "capacity_heating_kw": ("capacity_heating_min_kw", "capacity_heating_max_kw"),
    "power_cons_cooling_kw": ("power_cons_cooling_min_kw", "power_cons_cooling_max_kw"),
    "power_cons_heating_kw": ("power_cons_heating_min_kw", "power_cons_heating_max_kw"),
}


def get_spec_definition(key: str) -> SpecDefinition | None:
    return SPEC_DEFINITIONS.get(key)


def get_specs_registry_payload() -> dict[str, Any]:
    items = []
    for spec in sorted(SPEC_DEFINITIONS.values(), key=lambda item: item.key):
        items.append(
            {
                "key": spec.key,
                "label": spec.label,
                "value_type": spec.value_type.value,
                "quantity_kind": spec.quantity_kind.value if spec.quantity_kind else None,
                "canonical_unit": spec.canonical_unit,
                "aliases": _aliases_for_key(spec.key),
                "enum_values": list(spec.enum_values),
                "description": spec.description,
                "manager_note": spec.manager_note,
            }
        )
    return {"items": items, "total": len(items)}


def _normalize_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f").rstrip("0").rstrip(".")


def _to_json_number(value: Decimal) -> int | float:
    text = _normalize_decimal(value)
    if "." not in text:
        return int(text)
    return float(text)


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _extract_numbers(value: Any) -> list[Decimal]:
    if value is None:
        return []
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float, Decimal)):
        return [Decimal(str(value))]

    text = str(value).replace("−", "-").replace("—", "-").replace("\xa0", " ")
    numbers: list[Decimal] = []
    for match in re.findall(r"[-+]?\d+(?:[.,]\d+)?", text):
        parsed = _to_decimal(match)
        if parsed is not None:
            numbers.append(parsed)
    return numbers


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().casefold()
    if text in {"true", "1", "yes", "да", "есть", "поддерживается", "+", "✓", "✔"}:
        return True
    if text in {"false", "0", "no", "нет", "отсутствует", "none"}:
        return False
    return None


def _text_for_unit_detection(value: Any, source_key: str | None = None) -> str:
    text = f"{source_key or ''} {value or ''}".casefold()
    return text.replace("\xa0", " ")


def _has_kw(text: str) -> bool:
    return bool(re.search(r"(?:квт|kw|kW)", text, re.IGNORECASE))


def _has_watt(text: str) -> bool:
    if _has_kw(text):
        return False
    return bool(re.search(r"(?:\bвт\b|\bw\b|ватт)", text, re.IGNORECASE))


def _has_kg(text: str) -> bool:
    return "кг" in text or re.search(r"\bkg\b", text) is not None


def _has_gram(text: str) -> bool:
    return (
        re.search(r"(^|[^a-zа-я])г([^a-zа-я]|$)", text) is not None
        or re.search(r"\bg\b", text) is not None
        or "грамм" in text
    )


def _has_month(text: str) -> bool:
    return bool(re.search(r"(?:мес|месяц|месяцев|месяца|month)", text))


def _has_year(text: str) -> bool:
    return bool(re.search(r"(?:год|года|лет|year)", text))


def _convert_quantity(
    number: Decimal,
    *,
    spec: SpecDefinition,
    value: Any,
    source_key: str | None,
) -> Decimal:
    detection_text = _text_for_unit_detection(value, source_key)

    if spec.quantity_kind == QuantityKind.POWER and spec.canonical_unit == "kW":
        if "btu" in detection_text:
            return number * Decimal("0.00029307107")
        if _has_watt(detection_text) and abs(number) >= 100:
            return number / Decimal("1000")
        return number

    if spec.quantity_kind == QuantityKind.REFRIGERANT_MASS and spec.canonical_unit == "g":
        has_kg = _has_kg(detection_text)
        has_g = _has_gram(detection_text)
        if has_kg and not has_g:
            return number * Decimal("1000")
        return number

    if spec.quantity_kind == QuantityKind.WEIGHT and spec.canonical_unit == "kg":
        value_text = _text_for_unit_detection(value)
        source_text = _text_for_unit_detection(None, source_key)
        value_has_g = _has_gram(value_text)
        value_has_kg = _has_kg(value_text)
        source_has_g = _has_gram(source_text)
        source_has_kg = _has_kg(source_text)
        if (value_has_g and not value_has_kg) or (source_has_g and not source_has_kg):
            return number / Decimal("1000")
        return number

    if spec.quantity_kind == QuantityKind.LENGTH:
        if spec.canonical_unit == "m":
            if "мм" in detection_text or re.search(r"\bmm\b", detection_text):
                return number / Decimal("1000")
            if "см" in detection_text or re.search(r"\bcm\b", detection_text):
                return number / Decimal("100")
        if spec.canonical_unit == "mm":
            if re.search(r"(?<![а-я])м(?![а-я])", detection_text) or re.search(r"\bm\b", detection_text):
                return number * Decimal("1000")
            if "см" in detection_text or re.search(r"\bcm\b", detection_text):
                return number * Decimal("10")

    if spec.quantity_kind == QuantityKind.COUNT and spec.canonical_unit == "month":
        if _has_year(detection_text) and not _has_month(detection_text):
            return number * Decimal("12")
        return number

    return number


def normalize_registered_value(
    key: str,
    value: Any,
    *,
    source_key: str | None = None,
) -> Any | None:
    """Normalize a value according to the typed registry.

    Returns None when the registry has no numeric conversion for the key, so
    the legacy normalizer can continue with its existing rules.
    """

    spec = get_spec_definition(key)
    if spec is None or spec.value_type not in {SpecValueType.QUANTITY, SpecValueType.NUMBER_LIST}:
        return None

    detection_text = _text_for_unit_detection(value, source_key)
    has_explicit_conversion_unit = False
    if spec.quantity_kind == QuantityKind.POWER and spec.canonical_unit == "kW":
        has_explicit_conversion_unit = _has_watt(detection_text) or "btu" in detection_text
    elif spec.quantity_kind == QuantityKind.REFRIGERANT_MASS and spec.canonical_unit == "g":
        has_explicit_conversion_unit = (
            _has_kg(detection_text)
            or _has_gram(detection_text)
        )
    elif spec.quantity_kind == QuantityKind.WEIGHT and spec.canonical_unit == "kg":
        has_explicit_conversion_unit = _has_gram(detection_text)
    elif spec.quantity_kind == QuantityKind.LENGTH:
        has_explicit_conversion_unit = (
            "мм" in detection_text
            or "см" in detection_text
            or re.search(r"(?<![а-я])м(?![а-я])", detection_text) is not None
            or re.search(r"\b(?:mm|cm|m)\b", detection_text) is not None
        )
    elif spec.quantity_kind == QuantityKind.COUNT and spec.canonical_unit == "month":
        has_explicit_conversion_unit = _has_month(detection_text) or _has_year(detection_text)

    if not has_explicit_conversion_unit:
        return None

    numbers = _extract_numbers(value)
    if not numbers:
        return None

    if spec.value_type == SpecValueType.NUMBER_LIST and len(numbers) > 1:
        converted = [
            _normalize_decimal(_convert_quantity(number, spec=spec, value=value, source_key=source_key))
            for number in numbers
        ]
        return " / ".join(converted)

    selected = numbers[0]
    if key in _NOMINAL_FROM_TRIPLET_KEYS and len(numbers) >= 3 and "/" in str(value):
        selected = numbers[1]
    if key == "area_m2" and len(numbers) > 1 and any(token in str(value).casefold() for token in ("-", "до", "~")):
        selected = max(numbers)

    converted = _convert_quantity(selected, spec=spec, value=value, source_key=source_key)
    return _normalize_decimal(converted)


def _base_typed_payload(spec: SpecDefinition, raw_value: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": spec.value_type.value}
    if spec.quantity_kind:
        payload["kind"] = spec.quantity_kind.value
    if spec.canonical_unit:
        payload["unit"] = spec.canonical_unit
    if raw_value is not None:
        payload["raw"] = raw_value
    return payload


def _build_quantity_payload(
    spec: SpecDefinition,
    value: Any,
    *,
    source_key: str | None = None,
) -> dict[str, Any] | None:
    numbers = _extract_numbers(value)
    if not numbers:
        return None

    selected = numbers[0]
    if spec.key in _NOMINAL_FROM_TRIPLET_KEYS and len(numbers) >= 3 and "/" in str(value):
        selected = numbers[1]

    converted = _convert_quantity(selected, spec=spec, value=value, source_key=source_key)
    payload = _base_typed_payload(spec, value)
    payload["value"] = _to_json_number(converted)
    return payload


def _build_number_list_payload(spec: SpecDefinition, value: Any) -> dict[str, Any] | None:
    numbers = _extract_numbers(value)
    if not numbers:
        return None
    values = [
        _to_json_number(_convert_quantity(number, spec=spec, value=value, source_key=spec.key))
        for number in numbers
    ]
    payload = _base_typed_payload(spec, value)
    payload["values"] = values
    payload["min"] = min(values)
    payload["max"] = max(values)
    return payload


def _build_range_payload(spec: SpecDefinition, value: Any) -> dict[str, Any] | None:
    numbers = _extract_numbers(value)
    if not numbers:
        return None
    values = [
        _to_json_number(_convert_quantity(number, spec=spec, value=value, source_key=spec.key))
        for number in numbers
    ]
    payload = _base_typed_payload(spec, value)
    payload["values"] = values
    if len(values) == 1:
        text = str(value).casefold()
        if "до" in text:
            payload["max"] = values[0]
        else:
            payload["min"] = values[0]
    else:
        payload["min"] = min(values)
        payload["max"] = max(values)
    return payload


def _build_scalar_payload(spec: SpecDefinition, value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    payload = _base_typed_payload(spec, value)
    if spec.value_type == SpecValueType.BOOLEAN:
        parsed = _parse_bool(value)
        if parsed is None:
            return None
        payload["value"] = parsed
        return payload
    if spec.value_type in {SpecValueType.ENUM, SpecValueType.STATE, SpecValueType.TEXT}:
        text = str(value).strip()
        if not text:
            return None
        if spec.key == "indoor_type":
            normalized = text.casefold().replace("ё", "е")
            if "каналь" in normalized or "duct" in normalized:
                text = "duct"
            elif "кассет" in normalized or "cassette" in normalized:
                text = "cassette"
            elif (
                "напольно" in normalized
                or "подпотолоч" in normalized
                or "потолоч" in normalized
                or "универсальн" in normalized
                or "floor-ceiling" in normalized
                or "floor ceiling" in normalized
            ):
                text = "floor_ceiling"
            elif "колон" in normalized or "column" in normalized or "console" in normalized:
                text = "column"
        payload["value"] = text
        return payload
    return None


def build_typed_specs(specs: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Build a machine-readable typed layer from normalized flat specs.

    The returned structure is designed to live under ``__typed_specs`` while
    legacy flat keys remain the public compatibility layer.
    """

    typed: dict[str, dict[str, Any]] = {}
    for key, raw_value in specs.items():
        if str(key).startswith("__"):
            continue
        spec = get_spec_definition(str(key))
        if not spec:
            continue

        payload: dict[str, Any] | None
        if spec.value_type == SpecValueType.QUANTITY:
            payload = _build_quantity_payload(spec, raw_value)
        elif spec.value_type == SpecValueType.NUMBER_LIST:
            payload = _build_number_list_payload(spec, raw_value)
        elif spec.value_type == SpecValueType.RANGE:
            payload = _build_range_payload(spec, raw_value)
        else:
            payload = _build_scalar_payload(spec, raw_value)

        if payload:
            typed[spec.key] = payload

    for nominal_key, (min_key, max_key) in _TRIPLET_COMPANION_KEYS.items():
        nominal_payload = typed.get(nominal_key)
        if not nominal_payload:
            continue
        for source_key, target_key in ((min_key, "min"), (max_key, "max")):
            source_payload = typed.get(source_key)
            if source_payload and "value" in source_payload:
                nominal_payload[target_key] = source_payload["value"]
        if "value" in nominal_payload:
            nominal_payload["nominal"] = nominal_payload["value"]

    return typed
