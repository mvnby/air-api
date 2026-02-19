<script setup lang="ts">
import { ref, watch } from 'vue';
import { api } from '../api';
import { X, Plus, Trash2, Save, AlertTriangle } from 'lucide-vue-next';
import { getApiErrorMessage, parseApiFieldErrors } from '../utils/api-errors';

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

// Fetch known keys for autocomplete
const fetchKeys = async () => {
    keysLoading.value = true;
    try {
        const res = await api.getPublicSpecKeys();
        knownKeys.value = res.keys;
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
            validSpecs[row.key.trim()] = row.value.trim();
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
    <div v-if="modelValue" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" @click.self="close">
        <div class="bg-white dark:bg-slate-800 rounded-xl w-full max-w-2xl flex flex-col max-h-[90vh] border dark:border-slate-700">
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
            
            <div class="p-6 overflow-y-auto flex-1">
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
                            <input 
                                v-model="row.key" 
                                placeholder="Ключ (например: Цвет)" 
                                class="w-full border dark:border-slate-700 bg-white dark:bg-slate-900 dark:text-slate-200 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                                list="keys-datalist"
                            />
                            <!-- Native datalist for simplicity -->
                            <datalist id="keys-datalist">
                                <option v-for="k in knownKeys" :key="k" :value="k" />
                            </datalist>
                        </div>
                        
                        <!-- Value Input (Disabled if deleting keys) -->
                        <div class="flex-1">
                            <input 
                                v-model="row.value" 
                                :disabled="operation === 'delete_keys'"
                                :placeholder="operation === 'delete_keys' ? 'Пропускается' : 'Значение (например: Белый)'" 
                                class="w-full border dark:border-slate-700 bg-white dark:bg-slate-900 dark:text-slate-200 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:bg-gray-100 dark:disabled:bg-slate-800 disabled:text-gray-400 dark:disabled:text-slate-500"
                            />
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
</template>
