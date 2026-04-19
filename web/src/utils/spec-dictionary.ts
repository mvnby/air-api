export interface SpecDefinition {
    label: string;
    unit?: string;
    type?: 'boolean' | 'string' | 'number';
    group?: string;
}

export const SPEC_DICT: Record<string, SpecDefinition> = {
    // Basic
    brand: { label: "Бренд" },
    series: { label: "Серия" },
    release_year: { label: "Год выхода", unit: "г." },
    type: { label: "Тип кондиционера" },
    indoor_type: { label: "Тип внутреннего блока" },
    modes: { label: "Режимы работы" },
    color: { label: "Цвет" },
    wifi_ready: { label: "Wi-Fi", type: "boolean" },
    inverter: { label: "Инвертор", type: "boolean" },
    country: { label: "Страна производства" },
    indoor_units_count: { label: "Кол-во внутренних блоков" },

    // Controls & Modes
    remote_control: { label: "Пульт ДУ", type: "boolean" },
    timer: { label: "Таймер", type: "boolean" },
    airflow_direction: { label: "Регулировка направления потока", type: "boolean" },
    fan_speed: { label: "Регулировка скорости вентилятора", type: "boolean" },
    autorestart: { label: "Авторестарт", type: "boolean" },
    turbo_mode: { label: "Турбо-режим", type: "boolean" },
    sleep_mode: { label: "Режим «Сон»", type: "boolean" },
    dehumidification: { label: "Осушение воздуха", type: "boolean" },

    // Performance
    capacity_cooling_kw: { label: "Мощность охлаждения", unit: "кВт" },
    capacity_heating_kw: { label: "Мощность обогрева", unit: "кВт" },
    area_m2: { label: "Площадь", unit: "м²" },
    power_cons_cooling_kw: { label: "Потр. мощность (охлаждение)", unit: "кВт" },
    power_cons_heating_kw: { label: "Потр. мощность (обогрев)", unit: "кВт" },
    energy_class: { label: "Класс энергоэффективности" },
    energy_class_cooling: { label: "Класс энергоэффективности (охлаждение)" },
    energy_class_heating: { label: "Класс энергоэффективности (обогрев)" },
    seer: { label: "SEER" },
    scop: { label: "SCOP" },
    eer: { label: "EER" },
    cop: { label: "COP" },
    airflow_max: { label: "Расход воздуха", unit: "м³/ч" },

    // Pipes & Installation
    temp_range_cool: { label: "Раб. темп. (охлаждение)", unit: "°C" },
    temp_range_heat: { label: "Раб. темп. (обогрев)", unit: "°C" },

    // Dimensions & Noise
    noise_indoor: { label: "Шум (внутренний)", unit: "дБ" },
    noise_outdoor: { label: "Шум (наружный)", unit: "дБ" },
    width_indoor: { label: "Ширина (внутр)", unit: "мм" },
    height_indoor: { label: "Высота (внутр)", unit: "мм" },
    depth_indoor: { label: "Глубина (внутр)", unit: "мм" },
    width_outdoor: { label: "Ширина (наруж)", unit: "мм" },
    height_outdoor: { label: "Высота (наруж)", unit: "мм" },
    depth_outdoor: { label: "Глубина (наруж)", unit: "мм" },
    weight_indoor: { label: "Вес (внутр)", unit: "кг" },
    weight_outdoor: { label: "Вес (наруж)", unit: "кг" },

    // MDV specific
    model_indoor: { label: "Модель вн. блока" },
    model_outdoor: { label: "Модель нар. блока" },
    // --- МОНТАЖ (Самое вкусное для монтажников) ---
    cable_power: { label: "Кабель питания", group: "installation" },
    cable_interconnect: { label: "Межблочный кабель", group: "installation" },
    power_supply_location: { label: "Подключение питания", group: "installation" },

    pipe_liquid: { label: "Диаметр трубок (жидкость)", group: "installation" },
    pipe_gas: { label: "Диаметр трубок (газ)", group: "installation" },
    pipe_max_length: { label: "Макс. длина трассы", unit: "м", group: "installation" },
    pipe_max_height: { label: "Макс. перепад высот", unit: "м", group: "installation" },

    // --- ТЕХНОЛОГИИ ---
    compressor_brand: { label: "Компрессор", group: "tech" },
    compressor_type: { label: "Тип компрессора", group: "tech" },
    freon_type: { label: "Фреон", group: "tech" },
    power_supply: { label: "Электропитание", group: "installation" },

    // --- ДЛЯ ПРОФИ (Диапазоны) ---
    // Можно вывести, если хочется, или использовать только для фильтров
    min_temp_cool: { label: "Мин. t° охлаждения", group: "performance" },
    min_temp_heat: { label: "Мин. t° обогрева", group: "performance" },

    // Номиналы мы обычно не выводим отдельно, если есть общий range, 
    // но если хочешь показать мин-макс потребление:
    power_cons_cooling_min_kw: { label: "Потр. охлаждение (мин)", group: "energy" },
    power_cons_cooling_max_kw: { label: "Потр. охлаждение (макс)", group: "energy" },

    // --- ПРЕМИУМ ФУНКЦИИ ---
    self_cleaning: { label: "Самоочистка", type: "boolean", group: "tech" },
    fresh_air: { label: "Приток свежего воздуха", type: "boolean", group: "tech" },
    smart_home_integration: { label: "Умный дом", type: "boolean", group: "tech" },
    voice_control: { label: "Голосовое управление", type: "boolean", group: "tech" },

    // Filters
    bio_filter: { label: "Биофильтр", type: "boolean", group: "tech" },
    plasma_filter: { label: "Плазменный фильтр", type: "boolean", group: "tech" },
    ionizer: { label: "Ионизатор", type: "boolean", group: "tech" },
    carbon_filter: { label: "Угольный фильтр", type: "boolean", group: "tech" },
    photocatalytic_filter: { label: "Фотокаталитический фильтр", type: "boolean", group: "tech" },
    electrostatic_filter: { label: "Электростатический фильтр", type: "boolean", group: "tech" },
    uv_sterilization: { label: "УФ-стерилизация", type: "boolean", group: "tech" },
};

type PublicSpecGroup = {
    id: string;
    title: string;
    keys: string[];
};

const PUBLIC_SPEC_GROUPS: PublicSpecGroup[] = [
    {
        id: "general",
        title: "Общие характеристики",
        keys: ["brand", "series", "type", "indoor_type", "color", "release_year"],
    },
    {
        id: "purpose",
        title: "Режимы и назначение",
        keys: ["modes", "area_m2", "min_temp_heat"],
    },
    {
        id: "performance",
        title: "Производительность и энергоэффективность",
        keys: [
            "capacity_cooling_kw",
            "capacity_heating_kw",
            "power_cons_cooling_kw",
            "power_cons_heating_kw",
            "energy_class",
            "energy_class_cooling",
            "energy_class_heating",
            "seer",
            "scop",
            "eer",
            "cop",
            "inverter",
            "airflow_max",
        ],
    },
    {
        id: "ranges",
        title: "Рабочие диапазоны",
        keys: ["temp_range_cool", "temp_range_heat"],
    },
    {
        id: "control",
        title: "Управление и функции",
        keys: [
            "wifi_ready",
            "remote_control",
            "timer",
            "autorestart",
            "turbo_mode",
            "sleep_mode",
            "dehumidification",
            "self_cleaning",
            "airflow_direction",
            "fan_speed",
            "smart_home_integration",
            "voice_control",
        ],
    },
    {
        id: "air_quality",
        title: "Фильтрация и качество воздуха",
        keys: [
            "fresh_air",
            "bio_filter",
            "plasma_filter",
            "ionizer",
            "carbon_filter",
            "photocatalytic_filter",
            "electrostatic_filter",
            "uv_sterilization",
        ],
    },
    {
        id: "noise",
        title: "Шум",
        keys: ["noise_indoor", "noise_outdoor"],
    },
    {
        id: "installation",
        title: "Монтаж и магистраль",
        keys: [
            "pipe_liquid",
            "pipe_gas",
            "pipe_max_length",
            "pipe_max_height",
            "freon_type",
            "compressor_brand",
            "power_supply_location",
            "power_supply",
        ],
    },
    {
        id: "dimensions",
        title: "Габариты и вес",
        keys: [
            "width_indoor",
            "height_indoor",
            "depth_indoor",
            "weight_indoor",
            "width_outdoor",
            "height_outdoor",
            "depth_outdoor",
            "weight_outdoor",
        ],
    },
];

const HIDE_FALSE_BOOLEAN_KEYS = new Set([
    "remote_control",
    "timer",
    "autorestart",
    "turbo_mode",
    "sleep_mode",
    "dehumidification",
    "self_cleaning",
    "airflow_direction",
    "fan_speed",
    "smart_home_integration",
    "voice_control",
    "fresh_air",
    "bio_filter",
    "plasma_filter",
    "ionizer",
    "carbon_filter",
    "photocatalytic_filter",
    "electrostatic_filter",
    "uv_sterilization",
]);

/**
 * Normalize unit string to handle variations (e.g., м2 → м², m2 → м²)
 * @param text - Text to normalize
 * @returns Normalized text
 */
function normalizeUnits(text: string): string {
    return text
        .replace(/м2/gi, 'м²')   // м2 → м²
        .replace(/m2/gi, 'м²')   // m2 → м²
        .replace(/м3/gi, 'м³')   // м3 → м³
        .replace(/m3/gi, 'м³')   // m3 → м³
        .replace(/куб\.?\s*м\/ч/gi, 'м³/ч');  // куб → м³
}

/**
 * Format a spec value based on the dictionary
 * @param key - The spec key (English)
 * @param value - The raw value (can be number, string with/without units, or boolean)
 * @returns Formatted spec object with label and formatted value, or null if key not in dictionary
 */
export function formatSpec(key: string, value: any): { label: string; value: string } | null {
    const spec = SPEC_DICT[key];

    // Return null for unknown keys (hide them)
    if (!spec) {
        return null;
    }

    let formattedValue: string;

    // Handle boolean values
    if (spec.type === 'boolean') {
        const raw = String(value ?? '').trim().toLowerCase();
        const isTrue =
            value === true ||
            raw === 'true' ||
            raw === '1' ||
            raw === 'да' ||
            raw === 'yes' ||
            raw === 'есть';

        if (key === 'wifi_ready') {
            if (isTrue) {
                formattedValue = 'Да';
            } else if (raw === 'ready' || raw === 'опция' || raw === 'optional') {
                formattedValue = 'Опция';
            } else {
                formattedValue = 'Нет';
            }
        } else {
            formattedValue = isTrue ? 'Да' : 'Нет';
        }

        // Optional: hide false values by returning null
        // if (!isTrue) return null;
    }
    // Handle other types
    else {
        // Convert to string if needed
        formattedValue = String(value ?? '').trim();

        // Skip empty or dash values
        if (!formattedValue || formattedValue === '-') {
            return null;
        }

        // Normalize units in the value (e.g., "25 м2" → "25 м²")
        formattedValue = normalizeUnits(formattedValue);

        // Handle unit appending (crucial for hybrid data!)
        if (spec.unit) {
            // Normalize the dictionary unit as well
            const normalizedUnit = normalizeUnits(spec.unit);

            // Escape special regex characters in unit (e.g., ² → \\²)
            const escapedUnit = normalizedUnit.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

            // Check if unit already exists in value (case-insensitive)
            const unitRegex = new RegExp(escapedUnit, 'i');

            if (!unitRegex.test(formattedValue)) {
                // Unit not found, append it
                formattedValue = `${formattedValue} ${normalizedUnit}`;
            }
            // else: unit already exists, don't append
        }
    }

    return {
        label: spec.label,
        value: formattedValue
    };
}

export function formatPublicSpecsGrouped(specs: Record<string, any>) {
    const groups: Array<{
        id: string;
        title: string;
        items: Array<{ key: string; label: string; value: string }>;
    }> = [];

    for (const group of PUBLIC_SPEC_GROUPS) {
        const items: Array<{ key: string; label: string; value: string }> = [];
        for (const key of group.keys) {
            const formatted = formatSpec(key, specs[key]);
            if (!formatted) continue;
            if (HIDE_FALSE_BOOLEAN_KEYS.has(key) && formatted.value === 'Нет') continue;
            items.push({ key, label: formatted.label, value: formatted.value });
        }
        if (items.length > 0) {
            groups.push({
                id: group.id,
                title: group.title,
                items,
            });
        }
    }

    return groups;
}

/**
 * Format all specs from a raw specs object
 * @param specs - Raw specs object from API
 * @returns Array of formatted specs (only known keys)
 */
export function formatAllSpecs(specs: Record<string, any>) {
    const result: Array<{ label: string; value: string; group: string }> = [];
    const processedKeys = new Set<string>();

    // 1. Сначала проходим по нашему "Золотому стандарту" (Словарь)
    for (const [key, def] of Object.entries(SPEC_DICT)) {
        // Вызываем твой умный форматер!
        // Он сам добавит 'кВт', сам сделает 'Да/Нет'
        const formatted = formatSpec(key, specs[key]);

        if (formatted) {
            result.push({
                label: formatted.label,
                value: formatted.value,
                group: def.group || "main"
            });
            processedKeys.add(key);
        }
    }

    // 2. Теперь собираем "Legacy" (то, чего нет в словаре)
    for (const [key, value] of Object.entries(specs)) {
        if (processedKeys.has(key)) continue;

        // Фильтр служебных полей
        if (['inverter', 'model_indoor', 'model_outdoor', 'id', 'slug'].includes(key)) continue;

        if (value !== undefined && value !== null && value !== "") {
            // Для Legacy полей у нас нет словаря, поэтому выводим как есть.
            // Но если вдруг там true/false, можно тоже красиво обработать:
            let displayValue = String(value);
            if (value === true) displayValue = "Да";
            if (value === false) displayValue = "Нет";

            result.push({
                label: key,
                value: displayValue,
                group: "main"
            });
        }
    }
    return result;
}
