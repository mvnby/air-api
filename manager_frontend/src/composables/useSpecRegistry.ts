import { computed, ref } from 'vue';
import { api, type SpecRegistryResponse } from '../api';
import { hiddenSpecKeys, specsTranslations, type SpecConfig } from '../utils/specsTranslations';

type RegistryItem = SpecRegistryResponse['items'][number];
type SpecGroupKey =
    | 'identity'
    | 'performance'
    | 'efficiency'
    | 'operation'
    | 'installation'
    | 'dimensions'
    | 'comfort'
    | 'logistics'
    | 'other';

const registryConfigs = ref<Record<string, SpecConfig>>({ ...specsTranslations });
const knownSpecKeys = ref<string[]>(Object.keys(specsTranslations).filter((key) => !hiddenSpecKeys.has(key)));
const registryLoading = ref(false);
const registryLoaded = ref(false);

const unitLabels: Record<string, string> = {
    A: 'А',
    C: '°C',
    dB: 'дБ',
    g: 'г',
    'g/m': 'г/м',
    kg: 'кг',
    kW: 'кВт',
    'kWh/year': 'кВт·ч/год',
    'l/h': 'л/ч',
    m: 'м',
    m2: 'м²',
    'm3/h': 'м³/ч',
    mm: 'мм',
    month: 'мес.',
};

const specGroupLabels: Record<SpecGroupKey, string> = {
    identity: 'Основное',
    performance: 'Производительность',
    efficiency: 'Эффективность',
    operation: 'Работа и управление',
    installation: 'Монтаж',
    dimensions: 'Габариты и вес',
    comfort: 'Фильтры и комфорт',
    logistics: 'Логистика',
    other: 'Прочее',
};

const specGroupOrder: SpecGroupKey[] = [
    'identity',
    'performance',
    'efficiency',
    'operation',
    'installation',
    'dimensions',
    'comfort',
    'logistics',
    'other',
];

const registryTypeToControl = (item: RegistryItem): SpecConfig['type'] => {
    if (item.value_type === 'boolean') return 'boolean';
    if (item.value_type === 'enum' || item.value_type === 'state') return 'select';
    if (item.value_type === 'quantity') return 'number';
    if (item.value_type === 'range') return 'range';
    if (item.value_type === 'number_list') return 'number_list';
    if (item.value_type === 'dimensions') return 'dimensions';
    return 'text';
};

const groupForSpecKey = (key: string, item?: RegistryItem | null): SpecGroupKey => {
    const normalized = key.trim();
    const quantityKind = item?.quantity_kind || registryConfigs.value[normalized]?.quantityKind || '';

    if (
        [
            'type',
            'indoor_type',
            'brand',
            'series',
            'model',
            'model_indoor',
            'model_outdoor',
            'sku',
            'sku_list',
            'country',
            'color',
            'availability',
            'release_year',
        ].includes(normalized)
    ) {
        return 'identity';
    }

    if (
        normalized.startsWith('capacity_')
        || normalized.startsWith('power_cons_')
        || normalized.startsWith('airflow_')
        || normalized === 'area_m2'
        || normalized === 'dehumidification_l_h'
        || quantityKind === 'power'
        || quantityKind === 'airflow'
        || quantityKind === 'area'
        || quantityKind === 'volume_rate'
    ) {
        return 'performance';
    }

    if (
        normalized.startsWith('energy_class')
        || ['eer', 'cop', 'seer', 'scop', 'annual_energy_cooling_kwh', 'annual_energy_heating_kwh'].includes(normalized)
        || quantityKind === 'energy'
    ) {
        return 'efficiency';
    }

    if (
        normalized.startsWith('temp_range_')
        || normalized.startsWith('wifi_')
        || [
            'inverter',
            'inverter_type',
            'compressor_type',
            'compressor_brand',
            'modes',
            'remote_control',
            'timer',
            'fan_speed',
            'airflow_direction',
            'autorestart',
            'sleep_mode',
            'turbo_mode',
            'power_supply_location',
        ].includes(normalized)
        || quantityKind === 'temperature'
        || quantityKind === 'noise'
    ) {
        return 'operation';
    }

    if (
        normalized.startsWith('pipe_')
        || normalized.startsWith('refrigerant_')
        || normalized.startsWith('power_supply')
        || normalized.startsWith('current_')
        || normalized.startsWith('cable_')
        || ['drain_pipe_diameter', 'multi_max_total_pipe_length', 'multi_max_indoor_units'].includes(normalized)
    ) {
        return 'installation';
    }

    if (
        normalized.startsWith('width_')
        || normalized.startsWith('height_')
        || normalized.startsWith('depth_')
        || normalized.startsWith('weight_')
        || normalized.startsWith('dimensions_')
        || quantityKind === 'weight'
    ) {
        return 'dimensions';
    }

    if (
        normalized.endsWith('_filter')
        || [
            'bio_filter',
            'carbon_filter',
            'electrostatic_filter',
            'fresh_air',
            'humidification',
            'ionizer',
            'photocatalytic_filter',
            'plasma_filter',
            'presence_sensor',
            'self_cleaning',
            'self_diagnosis',
            'smart_home_integration',
            'uv_sterilization',
            'voice_control',
            'winter_kit',
        ].includes(normalized)
    ) {
        return 'comfort';
    }

    if (
        normalized.includes('package')
        || normalized.startsWith('includes_')
        || normalized === 'warranty_months'
    ) {
        return 'logistics';
    }

    return 'other';
};

const mapRegistryItem = (item: RegistryItem): SpecConfig => {
    const options = [...(item.enum_values || [])].filter(Boolean);
    return {
        label: item.label,
        type: registryTypeToControl(item),
        options: options.length ? options : undefined,
        unit: item.canonical_unit ? (unitLabels[item.canonical_unit] || item.canonical_unit) : undefined,
        canonicalUnit: item.canonical_unit || undefined,
        quantityKind: item.quantity_kind || undefined,
        valueType: item.value_type || undefined,
        group: groupForSpecKey(item.key, item),
        description: item.description || undefined,
        managerNote: item.manager_note || undefined,
        source: 'registry',
    };
};

const mergeKnownKeys = (...groups: Array<Iterable<string> | undefined>) => {
    const combined = new Set<string>();
    for (const group of groups) {
        if (!group) continue;
        for (const key of group) {
            const normalized = String(key || '').trim();
            if (!normalized || hiddenSpecKeys.has(normalized)) continue;
            combined.add(normalized);
        }
    }
    knownSpecKeys.value = Array.from(combined).sort((a, b) => a.localeCompare(b, 'ru'));
};

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const valueHasUnit = (value: string, config?: SpecConfig): boolean => {
    const text = value.toLowerCase();
    const candidates = [config?.unit, config?.canonicalUnit].filter(Boolean) as string[];
    return candidates.some((unit) => text.includes(unit.toLowerCase()));
};

const appendUnitIfNeeded = (value: string, config?: SpecConfig): string => {
    const trimmed = value.trim();
    if (!trimmed || !config?.unit || valueHasUnit(trimmed, config)) return trimmed;
    return `${trimmed} ${config.unit}`.trim();
};

export const useSpecRegistry = () => {
    const loadSpecRegistry = async () => {
        if (registryLoaded.value || registryLoading.value) return;
        registryLoading.value = true;
        try {
            const [registry, keys] = await Promise.all([
                api.getPublicSpecRegistry(),
                api.getPublicSpecKeys().catch(() => ({ keys: [] as string[] })),
            ]);
            const nextConfigs: Record<string, SpecConfig> = { ...specsTranslations };
            for (const item of registry.items || []) {
                nextConfigs[item.key] = {
                    ...nextConfigs[item.key],
                    ...mapRegistryItem(item),
                };
            }
            registryConfigs.value = nextConfigs;
            mergeKnownKeys(Object.keys(nextConfigs), keys.keys || []);
            registryLoaded.value = true;
        } catch (error) {
            console.error('Failed to fetch spec registry', error);
            try {
                const keys = await api.getPublicSpecKeys();
                mergeKnownKeys(Object.keys(specsTranslations), keys.keys || []);
            } catch (keysError) {
                console.error('Failed to fetch spec keys', keysError);
                mergeKnownKeys(Object.keys(specsTranslations));
            }
        } finally {
            registryLoading.value = false;
        }
    };

    const getSpecConfig = (key: string): SpecConfig | undefined => {
        const normalized = String(key || '').trim();
        const config = registryConfigs.value[normalized];
        if (!config) return undefined;
        if (config.group) return config;
        return { ...config, group: groupForSpecKey(normalized) };
    };

    const getSelectOptions = (key: string, value: unknown): string[] => {
        const base = [...(getSpecConfig(key)?.options || [])];
        const current = String(value ?? '').trim();
        if (current && !base.includes(current)) return [current, ...base];
        return base;
    };

    const formatSelectOptionLabel = (key: string, option: string): string => {
        if (key === 'wifi_ready') {
            if (option === 'true') return 'Да (встроен)';
            if (option === 'ready') return 'Ready (модуль отдельно)';
            if (option === 'false') return 'Нет';
        }
        if (key === 'wifi_state') {
            if (option === 'builtin') return 'Встроенный';
            if (option === 'ready') return 'Ready (модуль отдельно)';
            if (option === 'none') return 'Нет';
        }
        return option;
    };

    const getSpecHelpText = (key: string): string => {
        const config = getSpecConfig(key);
        return [config?.description, config?.managerNote].filter(Boolean).join('\n\n');
    };

    const normalizeValueForEdit = (key: string, value: unknown): string => {
        const config = getSpecConfig(key);
        let result = String(value ?? '');
        if (config?.type === 'number' && config.unit) {
            result = result.replace(new RegExp(`${escapeRegExp(config.unit)}$`, 'i'), '').trim();
            if (config.canonicalUnit) {
                result = result.replace(new RegExp(`${escapeRegExp(config.canonicalUnit)}$`, 'i'), '').trim();
            }
            const match = result.match(/^-?\d*[.,]?\d*/);
            result = match && match[0] ? match[0].replace(',', '.') : '';
        }
        return result;
    };

    const serializeSpecValue = (key: string, value: unknown): string => {
        let finalValue = String(value ?? '');
        const config = getSpecConfig(key);
        if (config?.type === 'number' && config.unit && finalValue.trim() !== '') {
            finalValue = appendUnitIfNeeded(finalValue, config);
        } else if ((config?.type === 'range' || config?.type === 'number_list') && finalValue.trim() !== '') {
            finalValue = appendUnitIfNeeded(finalValue, config);
        } else if (config?.type === 'boolean') {
            finalValue = finalValue === 'true' ? 'true' : 'false';
        }
        return finalValue.trim();
    };

    const getSpecGroup = (key: string): SpecGroupKey => {
        const config = getSpecConfig(key);
        return (config?.group as SpecGroupKey | undefined) || groupForSpecKey(String(key || ''));
    };

    return {
        getSelectOptions,
        getSpecConfig,
        getSpecGroup,
        getSpecGroupLabel: (group: string): string => specGroupLabels[group as SpecGroupKey] || specGroupLabels.other,
        specGroupOrder,
        getSpecHelpText,
        formatSelectOptionLabel,
        isHiddenSpecKey: (key: string) => hiddenSpecKeys.has(key) || key.startsWith('__'),
        knownSpecKeys: computed(() => knownSpecKeys.value),
        loadSpecRegistry,
        normalizeValueForEdit,
        registryConfigs: computed(() => registryConfigs.value),
        registryLoading: computed(() => registryLoading.value),
        serializeSpecValue,
    };
};
