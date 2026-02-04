export interface SpecDefinition {
    label: string;
    unit?: string;
    type?: 'boolean' | 'string' | 'number';
    group?: string;
}

export const SPEC_DICT: Record<string, SpecDefinition> = {
    // Basic
    release_year: { label: "Год выхода", unit: "г." },
    type: { label: "Тип кондиционера" },
    indoor_type: { label: "Тип внутреннего блока" },
    modes: { label: "Режимы работы" },
    color: { label: "Цвет" },
    wifi_ready: { label: "Wi-Fi", type: "boolean" },
    inverter: { label: "Инвертор", type: "boolean" },

    // Performance
    capacity_cooling_kw: { label: "Мощность охлаждения", unit: "кВт" },
    capacity_heating_kw: { label: "Мощность обогрева", unit: "кВт" },
    area_m2: { label: "Площадь", unit: "м²" },
    power_cons_cooling_kw: { label: "Потр. мощность (охлаждение)", unit: "кВт" },
    power_cons_heating_kw: { label: "Потр. мощность (обогрев)", unit: "кВт" },
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

    // --- ДЛЯ ПРОФИ (Диапазоны) ---
    // Можно вывести, если хочется, или использовать только для фильтров
    min_temp_cool: { label: "Мин. t° охлаждения", group: "performance" },
    min_temp_heat: { label: "Мин. t° обогрева", group: "performance" },

    // Номиналы мы обычно не выводим отдельно, если есть общий range, 
    // но если хочешь показать мин-макс потребление:
    power_cons_cooling_min_kw: { label: "Потр. охлаждение (мин)", group: "energy" },
    power_cons_cooling_max_kw: { label: "Потр. охлаждение (макс)", group: "energy" },
};

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
        .replace(/m3/gi, 'м³');  // m3 → м³
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
        const isTrue = value === true || value === 'true' || value === '1';
        formattedValue = isTrue ? 'Да' : 'Нет';

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

/**
 * Format all specs from a raw specs object
 * @param specs - Raw specs object from API
 * @returns Array of formatted specs (only known keys)
 */
export function formatAllSpecs(specs: Record<string, any>): Array<{ label: string; value: string }> {
    const formatted: Array<{ label: string; value: string }> = [];

    for (const [key, value] of Object.entries(specs)) {
        const formatted_spec = formatSpec(key, value);
        if (formatted_spec) {
            formatted.push(formatted_spec);
        }
    }

    return formatted;
}
