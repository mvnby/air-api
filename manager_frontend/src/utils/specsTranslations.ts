export interface SpecConfig {
    label: string;
    type: 'boolean' | 'select' | 'number' | 'text' | 'range' | 'number_list' | 'dimensions';
    options?: string[];
    unit?: string;
    canonicalUnit?: string;
    quantityKind?: string;
    valueType?: string;
    group?: string;
    description?: string;
    managerNote?: string;
    source?: 'registry' | 'fallback';
}

export const specsTranslations: Record<string, SpecConfig> = {
    brand: { label: 'Бренд', type: 'text' },
    series: { label: 'Серия (Линейка)', type: 'text' },
    is_inverter: { label: 'Инвертор', type: 'boolean' },
    wifi_module: { label: 'Wi-Fi', type: 'boolean' },
    wifi_builtin: { label: 'Wi-Fi встроенный', type: 'boolean' },
    wifi_state: { label: 'Состояние Wi-Fi', type: 'select', options: ['builtin', 'ready', 'none'] },
    compressor_brand: { label: 'Марка компрессора', type: 'select', options: ['GMCC', 'Toshiba', 'Highly', 'Panasonic', 'Gree', 'Mitsubishi'] },
    pipe_liquid: { label: 'Труба жидкостная', type: 'select', options: ['1/4"', '3/8"', '1/2"'] },
    pipe_gas: { label: 'Труба газовая', type: 'select', options: ['3/8"', '1/2"', '5/8"', '3/4"'] },
    capacity_cooling_kw: { label: 'Мощность охлаждения', type: 'number', unit: 'кВт' },
    capacity_heating_kw: { label: 'Мощность обогрева', type: 'number', unit: 'кВт' },
    area_m2: { label: 'Площадь', type: 'number', unit: 'м²' },
    recommended_area_m2: { label: 'Рекомендуемая площадь', type: 'number', unit: 'м²' },
    airflow_max: { label: 'Расход воздуха', type: 'number', unit: 'м³/ч' },
    noise_level_db: { label: 'Уровень шума', type: 'number', unit: 'дБ' },
    energy_efficiency_class: { label: 'Класс энергоэффективности', type: 'text' },
    refrigerant: { label: 'Фреон', type: 'text' },
    compressor_type: { label: 'Тип компрессора', type: 'text' },
    max_pipe_length_m: { label: 'Макс. длина трассы', type: 'number', unit: 'м' },
    max_elevation_m: { label: 'Макс. перепад высот', type: 'number', unit: 'м' },
    power_supply: { label: 'Электропитание', type: 'text' },
    power_consumption_cooling_w: { label: 'Потребляемая мощность при охлаждении', type: 'number', unit: 'Вт' },
    power_consumption_heating_w: { label: 'Потребляемая мощность при обогреве', type: 'number', unit: 'Вт' },
    operating_temp_cooling: { label: 'Рабочий диапазон (охлаждение)', type: 'text' },
    operating_temp_heating: { label: 'Рабочий диапазон (обогрев)', type: 'text' },
    indoor_unit_dimensions_mm: { label: 'Размеры внутреннего блока', type: 'text', unit: 'мм' },
    outdoor_unit_dimensions_mm: { label: 'Размеры наружного блока', type: 'text', unit: 'мм' },
    indoor_unit_weight_kg: { label: 'Вес внутреннего блока', type: 'number', unit: 'кг' },
    outdoor_unit_weight_kg: { label: 'Вес наружного блока', type: 'number', unit: 'кг' },
    wi_fi: { label: 'Wi-Fi', type: 'boolean' },
    wifi_ready: { label: 'Wi-Fi', type: 'select', options: ['true', 'ready', 'false'] },
    color: { label: 'Цвет', type: 'text' },
    country_of_origin: { label: 'Страна-производитель', type: 'text' },
    warranty_years: { label: 'Гарантия', type: 'number', unit: 'лет' },
    fresh_air: { label: 'Приток свежего воздуха', type: 'boolean' },
    type: {
        label: 'Тип кондиционера',
        type: 'select',
        options: [
            'сплит-система',
            'мульти-сплит-система',
            'внутренний блок',
            'наружный блок',
            'полупромышленный кондиционер',
        ],
    },
    indoor_type: {
        label: 'Тип внутреннего блока',
        type: 'select',
        options: ['настенный', 'кассетный', 'канальный', 'напольно-потолочный', 'колонный'],
    },
    multi_max_indoor_units: { label: 'Максимум внутренних блоков', type: 'number', unit: 'шт' },
    multi_max_total_pipe_length: { label: 'Максимальная суммарная длина трассы', type: 'number', unit: 'м' },
    multi_max_height_diff: { label: 'Максимальный перепад высот', type: 'number', unit: 'м' },
    modes: { label: 'Режимы работы', type: 'text' },
    freon_type: { label: 'Тип фреона', type: 'text' },
    inverter: { label: 'Инвертор', type: 'boolean' },
    remote_control: { label: 'Пульт ДУ', type: 'boolean' },
    timer: { label: 'Таймер', type: 'boolean' },
};

export const hiddenSpecKeys = new Set([
    'wifi_module',
    'wi_fi',
    'wifi',
    'wifi-builtin',
    'wifi-ready',
    '__filter_wifi',
    '__filter_wifi_builtin',
    '__filter_min_heat',
    '__filter_noise_min',
    '__filter_indoor_type',
    '__typed_specs',
    'compressor_type_norm',
]);
