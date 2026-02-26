<script setup lang="ts">
import { ref, watch } from 'vue';
import { api } from '../api';
import { X, Plus, Trash2, Save, AlertTriangle } from 'lucide-vue-next';
import { getApiErrorMessage, parseApiFieldErrors } from '../utils/api-errors';
import SpecKeyCombobox from './SpecKeyCombobox.vue';
import { specsTranslations } from '../utils/specsTranslations';

const props = defineProps<{
    modelValue: boolean; // isOpen
    selectedProductIds: number[];
}>();

const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void;
    (e: 'success'): void;
}>();

const specs = ref<{ key: string; value: string }[]>([{ key: '', value: '' }]);
const operation = ref<'merge' | 'replace' | 'delete_keys'>('merge');
const loading = ref(false);
const formMessage = ref('');
const formServerErrors = ref<Record<string, string>>({});
const knownKeys = ref<string[]>([]);
const keysLoading = ref(false);
const hiddenWifiAliasKeys = new Set([
    'wifi_module',
    'wi_fi',
    'wifi',
    'wifi-builtin',
    'wifi-ready',
    '__filter_wifi',
    '__filter_wifi_builtin',
]);

// Fetch known keys for autocomplete
const fetchKeys = async () => {
    keysLoading.value = true;
    try {
        const res = await api.getPublicSpecKeys();
        // Merge API keys with basic keys from translations to ensure they are always present
        const combined = new Set([...Object.keys(specsTranslations), ...res.keys]);
        knownKeys.value = Array.from(combined).filter((key) => !hiddenWifiAliasKeys.has(key));
    } catch (e) {
        console.error('Failed to fetch spec keys', e);
    } finally {
        keysLoading.value = false;
    }
};

watch(() => props.modelValue, (val) => {
    if (val) {
        formMessage.value = '';
        formServerErrors.value = {};
        if (knownKeys.value.length === 0) fetchKeys();
        // Reset form
        specs.value = [{ key: '', value: '' }];
        operation.value = 'merge';
    }
});

const addRow = () => {
    specs.value.push({ key: '', value: '' });
};

const removeRow = (index: number) => {
    specs.value.splice(index, 1);
};

const close = () => {
    emit('update:modelValue', false);
};

const save = async () => {
    if (props.selectedProductIds.length === 0) return;
    formMessage.value = '';
    formServerErrors.value = {};
    
    // Validate
    const validSpecs: Record<string, string> = {};
    for (const row of specs.value) {
        if (row.key.trim()) {
            let finalValue = row.value;
            const config = specsTranslations[row.key.trim()];
            if (config?.type === 'number' && config.unit && finalValue.toString().trim() !== '') {
                finalValue = `${finalValue} ${config.unit}`.trim();
            } else if (config?.type === 'boolean') {
                // Keep boolean strings or convert properly based on existing convention (e.g. "true"/"false")
                // Standardizing to string "true"/"false" as the modal values are tracked as strings initially
                finalValue = (row.value === 'true') ? 'true' : 'false';
            }
            validSpecs[row.key.trim()] = finalValue.toString().trim();
        }
    }
    
    // Logic for validation
    if (Object.keys(validSpecs).length === 0) {
         if (operation.value === 'delete_keys') {
              formMessage.value = 'Укажите хотя бы один ключ характеристики';
              return;
         }
         // For merge/replace, empty might mean clear all or nothing
         if (operation.value === 'replace') {
             // If manual clear (no rows or empty rows)
             if (!confirm('Будут очищены все характеристики у выбранных товаров. Продолжить?')) return;
         } else {
             // Merge with empty = do nothing
             formMessage.value = 'Нет изменений для применения';
             return;
         }
    }

    loading.value = true;
    try {
        await api.bulkUpdateSpecs(props.selectedProductIds, validSpecs, operation.value);
        emit('success');
        close();
    } catch (e) {
        console.error(e);
        const parsed = parseApiFieldErrors(e, ['product_ids', 'specs', 'operation']);
        formServerErrors.value = parsed.fieldErrors;
        formMessage.value = parsed.message || `Не удалось обновить характеристики: ${getApiErrorMessage(e)}`;
    } finally {
        loading.value = false;
    }
};
</script>

<template>
    <div v-if="modelValue" class="relative z-50">
        <!-- Backdrop -->
        <div class="fixed inset-0 bg-black/50 transition-opacity" @click="close"></div>
        
        <!-- Modal Container -->
        <div class="fixed inset-0 z-10 w-screen overflow-y-auto" @click.self="close">
            <div class="flex min-h-full items-center justify-center p-4 text-center sm:p-0" @click.self="close">
                <div class="relative transform rounded-xl bg-white dark:bg-slate-800 text-left shadow-xl transition-all w-full max-w-2xl border dark:border-slate-700 my-8 flex flex-col min-h-[500px]" @click.stop>
            <header class="p-4 border-b dark:border-slate-700 flex justify-between items-center bg-gray-50 dark:bg-slate-900/50 rounded-t-xl">
                <h2 class="text-lg font-bold text-gray-900 dark:text-white">
                    Массовое редактирование
                    <span class="text-sm font-normal text-gray-500 dark:text-slate-400 ml-2">
                        ({{ selectedProductIds.length }} {{ selectedProductIds.length === 1 ? 'товар' : (selectedProductIds.length >= 2 && selectedProductIds.length <= 4 ? 'товара' : 'товаров') }})
                    </span>
                </h2>
                <button @click="close" class="text-gray-400 hover:text-gray-600">
                    <X class="w-5 h-5" />
                </button>
            </header>
            <div v-if="formMessage" class="mx-6 mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {{ formMessage }}
            </div>
            
            <div class="p-4 sm:p-6 overflow-visible">
                <div v-if="Object.keys(formServerErrors).length" class="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                    <p v-for="(message, field) in formServerErrors" :key="`bulk-${field}`">{{ field }}: {{ message }}</p>
                </div>
                <!-- Operation Selector -->
                <div class="mb-6">
                    <label class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">Операция</label>
                    <div class="flex flex-wrap gap-4">
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input v-model="operation" type="radio" value="merge" class="text-teal-600 focus:ring-teal-500" />
                            <span class="text-sm text-gray-800 dark:text-slate-200">Слияние (Добавить/Обновить)</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input v-model="operation" type="radio" value="replace" class="text-red-500 focus:ring-red-500" />
                            <span class="text-sm text-gray-800 dark:text-slate-200">Заменить все (Перезапись)</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input v-model="operation" type="radio" value="delete_keys" class="text-orange-500 focus:ring-orange-500" />
                            <span class="text-sm text-gray-800 dark:text-slate-200">Удалить ключи</span>
                        </label>
                    </div>
                    <p v-if="operation === 'replace'" class="mt-2 text-xs text-red-500 dark:text-red-400 flex items-center gap-1">
                        <AlertTriangle class="w-3 h-3" /> Внимание: Это удалит все существующие характеристики и заменит их списком ниже.
                    </p>
                </div>
                
                <!-- Spec Rows -->
                <div class="space-y-3">
                    <div v-if="specs.length === 0" class="text-center text-gray-400 italic py-4">
                        No specs to update.
                    </div>
                    <div v-for="(row, idx) in specs" :key="idx" class="flex gap-2 items-start group">
                        <!-- Key Input with rudimentary autocomplete -->
                        <div class="relative flex-1">
                            <SpecKeyCombobox 
                                v-model="row.key" 
                                :known-keys="knownKeys" 
                            />
                        </div>
                        
                        <!-- Value Input (Disabled if deleting keys) -->
                        <div class="flex-1">
                            <template v-if="specsTranslations[row.key]?.type === 'boolean'">
                                <div class="flex items-center h-[38px]">
                                    <button 
                                        type="button"
                                        @click="row.value = (row.value === 'true') ? 'false' : 'true'"
                                        :disabled="operation === 'delete_keys'"
                                        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                        :class="(row.value === 'true') ? 'bg-teal-600' : 'bg-gray-200 dark:bg-slate-700'"
                                        role="switch"
                                        :aria-checked="row.value === 'true'"
                                    >
                                        <span class="sr-only">Toggle boolean</span>
                                        <span 
                                            aria-hidden="true" 
                                            class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                                            :class="(row.value === 'true') ? 'translate-x-5' : 'translate-x-0'"
                                        />
                                    </button>
                                    <span class="ml-3 text-sm font-medium text-gray-900 dark:text-slate-200">
                                        {{ (row.value === 'true') ? 'Да' : 'Нет' }}
                                    </span>
                                </div>
                            </template>
                            
                            <template v-else-if="specsTranslations[row.key]?.type === 'select'">
                                <select 
                                    v-model="row.value"
                                    :disabled="operation === 'delete_keys'"
                                    class="w-full h-[38px] border dark:border-slate-700 bg-white dark:bg-slate-900 dark:text-slate-200 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:bg-gray-100 dark:disabled:bg-slate-800 disabled:text-gray-400 dark:disabled:text-slate-500"
                                >
                                    <option value="" disabled>{{ operation === 'delete_keys' ? 'Пропускается' : 'Выберите значение' }}</option>
                                    <option v-for="opt in specsTranslations[row.key]?.options || []" :key="opt" :value="opt">
                                        {{
                                            row.key === 'wifi_ready'
                                                ? (opt === 'true' ? 'Да (встроен)' : (opt === 'ready' ? 'Ready (модуль отдельно)' : 'Нет'))
                                                : opt
                                        }}
                                    </option>
                                </select>
                            </template>
                            
                            <template v-else-if="specsTranslations[row.key]?.type === 'number'">
                                <div class="flex h-[38px] rounded shadow-sm">
                                    <input 
                                        type="number"
                                        v-model="row.value" 
                                        :disabled="operation === 'delete_keys'"
                                        :placeholder="operation === 'delete_keys' ? 'Пропускается' : 'Значение'" 
                                        class="flex-1 min-w-0 block w-full border dark:border-slate-700 bg-white dark:bg-slate-900 dark:text-slate-200 rounded-none rounded-l px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:bg-gray-100 dark:disabled:bg-slate-800 disabled:text-gray-400 dark:disabled:text-slate-500"
                                    />
                                    <span v-if="specsTranslations[row.key]?.unit" class="inline-flex items-center px-3 rounded-r border border-l-0 border-gray-300 dark:border-slate-700 bg-gray-50 dark:bg-slate-700 text-gray-500 dark:text-slate-300 text-sm">
                                        {{ specsTranslations[row.key]?.unit }}
                                    </span>
                                </div>
                            </template>
                            
                            <template v-else>
                                <input 
                                    type="text"
                                    v-model="row.value" 
                                    :disabled="operation === 'delete_keys'"
                                    :placeholder="operation === 'delete_keys' ? 'Пропускается' : 'Значение (например: Белый)'" 
                                    class="w-full h-[38px] border dark:border-slate-700 bg-white dark:bg-slate-900 dark:text-slate-200 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:bg-gray-100 dark:disabled:bg-slate-800 disabled:text-gray-400 dark:disabled:text-slate-500"
                                />
                            </template>
                        </div>
                        
                        <button @click="removeRow(idx)" class="p-2 text-gray-400 hover:text-red-500 transition-colors">
                            <Trash2 class="w-4 h-4" />
                        </button>
                    </div>
                </div>
                
                <button @click="addRow" class="mt-4 flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800 font-medium">
                    <Plus class="w-4 h-4" /> Add Row
                </button>
            </div>
            
            <footer class="p-4 border-t dark:border-slate-700 bg-gray-50 dark:bg-slate-900/50 rounded-b-xl flex justify-end gap-3">
                <button @click="close" class="px-4 py-2 text-sm font-medium text-gray-600 dark:text-slate-400 hover:text-gray-800 dark:hover:text-slate-200">Отмена</button>
                <button 
                    @click="save" 
                    :disabled="loading"
                    class="px-6 py-2 bg-[#007f80] text-white rounded shadow hover:bg-teal-700 disabled:opacity-50 flex items-center gap-2 text-sm font-medium"
                >
                    <div v-if="loading" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                    <Save v-else class="w-4 h-4" />
                    Применить
                </button>
            </footer>
                </div>
            </div>
        </div>
    </div>
</template>
