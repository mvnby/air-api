import { computed, ref } from 'vue';
import { api, type SpecRegistryResponse } from '../api';
import { hiddenSpecKeys, specsTranslations, type SpecConfig } from '../utils/specsTranslations';

type RegistryItem = SpecRegistryResponse['items'][number];

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

const registryTypeToControl = (item: RegistryItem): SpecConfig['type'] => {
    if (item.value_type === 'boolean') return 'boolean';
    if (item.value_type === 'enum' || item.value_type === 'state') return 'select';
    if (item.value_type === 'quantity') return 'number';
    return 'text';
};

const mapRegistryItem = (item: RegistryItem): SpecConfig => {
    const options = [...(item.enum_values || [])].filter(Boolean);
    return {
        label: item.label,
        type: registryTypeToControl(item),
        options: options.length ? options : undefined,
        unit: item.canonical_unit ? (unitLabels[item.canonical_unit] || item.canonical_unit) : undefined,
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

    const getSpecConfig = (key: string): SpecConfig | undefined => registryConfigs.value[key];

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
            result = result.replace(new RegExp(`${config.unit}$`, 'i'), '').trim();
            const match = result.match(/^-?\d*[.,]?\d*/);
            result = match && match[0] ? match[0].replace(',', '.') : '';
        }
        return result;
    };

    const serializeSpecValue = (key: string, value: unknown): string => {
        let finalValue = String(value ?? '');
        const config = getSpecConfig(key);
        if (config?.type === 'number' && config.unit && finalValue.trim() !== '') {
            finalValue = `${finalValue} ${config.unit}`.trim();
        } else if (config?.type === 'boolean') {
            finalValue = finalValue === 'true' ? 'true' : 'false';
        }
        return finalValue.trim();
    };

    return {
        getSelectOptions,
        getSpecConfig,
        getSpecHelpText,
        formatSelectOptionLabel,
        isHiddenSpecKey: (key: string) => hiddenSpecKeys.has(key),
        knownSpecKeys: computed(() => knownSpecKeys.value),
        loadSpecRegistry,
        normalizeValueForEdit,
        registryConfigs: computed(() => registryConfigs.value),
        registryLoading: computed(() => registryLoading.value),
        serializeSpecValue,
    };
};
