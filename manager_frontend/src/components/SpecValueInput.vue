<script setup lang="ts">
import { computed } from 'vue';
import { useSpecRegistry } from '../composables/useSpecRegistry';

const props = withDefaults(defineProps<{
    modelValue: string;
    specKey: string;
    disabled?: boolean;
    compact?: boolean;
    placeholder?: string;
}>(), {
    disabled: false,
    compact: false,
    placeholder: 'Значение',
});

const emit = defineEmits<{
    (e: 'update:modelValue', value: string): void;
}>();

const {
    formatSelectOptionLabel,
    getSelectOptions,
    getSpecConfig,
} = useSpecRegistry();

const config = computed(() => getSpecConfig(props.specKey));
const value = computed({
    get: () => String(props.modelValue ?? ''),
    set: (next: string) => emit('update:modelValue', next),
});
const controlTextClass = computed(() => props.compact ? 'text-xs' : 'text-sm');
const inputBaseClass = computed(() => [
    'block w-full border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-200',
    'focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 transition-all',
    'disabled:bg-gray-100 dark:disabled:bg-slate-800 disabled:text-gray-400 dark:disabled:text-slate-500',
    props.compact ? 'h-[38px] px-2.5 py-1.5 text-xs' : 'h-[38px] px-3 py-1.5 text-sm',
].join(' '));
const softInputClass = computed(() => [
    inputBaseClass.value,
    'bg-slate-100 dark:bg-slate-800 shadow-inner',
].join(' '));
const unitPillClass = computed(() => [
    'inline-flex items-center border border-l-0 border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-700 text-gray-500 dark:text-slate-300',
    props.compact ? 'px-2.5 text-xs' : 'px-3 text-sm',
].join(' '));

const extractNumbers = (raw: string): string[] => {
    const normalized = String(raw || '').replace('−', '-').replace('—', '-').replace(/,/g, '.');
    return Array.from(normalized.matchAll(/[-+]?\d+(?:\.\d+)?/g)).map((match) => match[0]);
};
const eventValue = (event: Event): string => (event.target as HTMLInputElement | null)?.value || '';

const rangeNumbers = computed(() => extractNumbers(value.value));
const rangeMin = computed(() => {
    const text = value.value.toLowerCase();
    if (rangeNumbers.value.length === 0) return '';
    if (rangeNumbers.value.length === 1 && text.includes('до') && !text.includes('от')) return '';
    return rangeNumbers.value[0] || '';
});
const rangeMax = computed(() => {
    const text = value.value.toLowerCase();
    if (rangeNumbers.value.length >= 2) return rangeNumbers.value[1] || '';
    if (rangeNumbers.value.length === 1 && text.includes('до') && !text.includes('от')) return rangeNumbers.value[0] || '';
    return '';
});

const withUnit = (raw: string): string => {
    const trimmed = raw.trim();
    if (!trimmed || !config.value?.unit) return trimmed;
    const lower = trimmed.toLowerCase();
    const localized = config.value.unit.toLowerCase();
    const canonical = String(config.value.canonicalUnit || '').toLowerCase();
    if (lower.includes(localized) || (canonical && lower.includes(canonical))) return trimmed;
    return `${trimmed} ${config.value.unit}`.trim();
};

const updateRange = (part: 'min' | 'max', nextValue: string) => {
    const min = (part === 'min' ? nextValue : rangeMin.value).trim();
    const max = (part === 'max' ? nextValue : rangeMax.value).trim();
    if (min && max) {
        value.value = withUnit(`от ${min} до ${max}`);
    } else if (min) {
        value.value = withUnit(`от ${min}`);
    } else if (max) {
        value.value = withUnit(`до ${max}`);
    } else {
        value.value = '';
    }
};

const normalizeNumberList = () => {
    if (config.value?.type !== 'number_list' || !value.value.trim()) return;
    const numbers = extractNumbers(value.value);
    if (numbers.length === 0) return;
    value.value = withUnit(numbers.join(' / '));
};

const dimensionNumbers = computed(() => extractNumbers(value.value));
const updateDimension = (index: number, nextValue: string) => {
    const values = [dimensionNumbers.value[0] || '', dimensionNumbers.value[1] || '', dimensionNumbers.value[2] || ''];
    values[index] = nextValue.trim();
    const filled = values.filter(Boolean);
    value.value = filled.length ? withUnit(values.map((item) => item || '').join(' × ')) : '';
};
</script>

<template>
    <template v-if="config?.type === 'boolean'">
        <div class="flex h-[38px] items-center">
            <button
                type="button"
                :disabled="disabled"
                class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                :class="value === 'true' ? 'bg-teal-600' : 'bg-gray-200 dark:bg-slate-700'"
                role="switch"
                :aria-checked="value === 'true'"
                @click="value = value === 'true' ? 'false' : 'true'"
            >
                <span class="sr-only">Переключить значение</span>
                <span
                    aria-hidden="true"
                    class="pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                    :class="value === 'true' ? 'translate-x-5' : 'translate-x-0'"
                />
            </button>
            <span class="ml-3 font-medium text-gray-900 dark:text-slate-200" :class="controlTextClass">
                {{ value === 'true' ? 'Да' : 'Нет' }}
            </span>
        </div>
    </template>

    <template v-else-if="config?.type === 'select'">
        <select
            v-model="value"
            :disabled="disabled"
            class="rounded-lg"
            :class="softInputClass"
        >
            <option value="" disabled>{{ disabled ? 'Пропускается' : 'Выберите значение' }}</option>
            <option v-for="opt in getSelectOptions(specKey, value)" :key="opt" :value="opt">
                {{ formatSelectOptionLabel(specKey, opt) }}
            </option>
        </select>
    </template>

    <template v-else-if="config?.type === 'number'">
        <div class="flex h-[38px] rounded-lg shadow-inner">
            <input
                v-model="value"
                type="number"
                :disabled="disabled"
                :placeholder="disabled ? 'Пропускается' : placeholder"
                class="min-w-0 flex-1 rounded-none rounded-l-lg"
                :class="softInputClass"
            />
            <span v-if="config?.unit" class="rounded-r-lg" :class="unitPillClass">
                {{ config.unit }}
            </span>
        </div>
    </template>

    <template v-else-if="config?.type === 'range'">
        <div class="flex h-[38px] rounded-lg shadow-inner">
            <input
                :value="rangeMin"
                type="number"
                :disabled="disabled"
                placeholder="от"
                class="min-w-0 flex-1 rounded-none rounded-l-lg"
                :class="softInputClass"
                @input="updateRange('min', eventValue($event))"
            />
            <span class="inline-flex items-center border-y border-gray-200 bg-white px-2 text-slate-400 dark:border-slate-700 dark:bg-slate-900" :class="controlTextClass">
                до
            </span>
            <input
                :value="rangeMax"
                type="number"
                :disabled="disabled"
                placeholder="до"
                class="min-w-0 flex-1 rounded-none"
                :class="softInputClass"
                @input="updateRange('max', eventValue($event))"
            />
            <span v-if="config?.unit" class="rounded-r-lg" :class="unitPillClass">
                {{ config.unit }}
            </span>
        </div>
    </template>

    <template v-else-if="config?.type === 'number_list'">
        <div class="flex h-[38px] rounded-lg shadow-inner">
            <input
                v-model="value"
                type="text"
                :disabled="disabled"
                placeholder="23 / 26 / 31"
                class="min-w-0 flex-1 rounded-none rounded-l-lg"
                :class="softInputClass"
                @blur="normalizeNumberList"
            />
            <span v-if="config?.unit" class="rounded-r-lg" :class="unitPillClass">
                {{ config.unit }}
            </span>
        </div>
    </template>

    <template v-else-if="config?.type === 'dimensions'">
        <div class="grid grid-cols-[1fr_1fr_1fr_auto] gap-1">
            <input
                :value="dimensionNumbers[0] || ''"
                type="number"
                :disabled="disabled"
                placeholder="Ш"
                class="rounded-lg"
                :class="softInputClass"
                @input="updateDimension(0, eventValue($event))"
            />
            <input
                :value="dimensionNumbers[1] || ''"
                type="number"
                :disabled="disabled"
                placeholder="В"
                class="rounded-lg"
                :class="softInputClass"
                @input="updateDimension(1, eventValue($event))"
            />
            <input
                :value="dimensionNumbers[2] || ''"
                type="number"
                :disabled="disabled"
                placeholder="Г"
                class="rounded-lg"
                :class="softInputClass"
                @input="updateDimension(2, eventValue($event))"
            />
            <span v-if="config?.unit" class="inline-flex items-center rounded-lg border border-gray-200 bg-gray-50 px-2 text-gray-500 dark:border-slate-700 dark:bg-slate-700 dark:text-slate-300" :class="controlTextClass">
                {{ config.unit }}
            </span>
        </div>
    </template>

    <template v-else>
        <input
            v-model="value"
            type="text"
            :disabled="disabled"
            :placeholder="disabled ? 'Пропускается' : placeholder"
            class="rounded-lg"
            :class="softInputClass"
        />
    </template>
</template>
