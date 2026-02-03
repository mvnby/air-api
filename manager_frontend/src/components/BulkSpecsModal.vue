<script setup lang="ts">
import { ref, watch } from 'vue';
import { api } from '../api';
import { X, Plus, Trash2, Save, AlertTriangle } from 'lucide-vue-next';

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
              alert('Please specify at least one specification key');
              return;
         }
         // For merge/replace, empty might mean clear all or nothing
         if (operation.value === 'replace') {
             // If manual clear (no rows or empty rows)
             if (!confirm('This will clear ALL specs for selected products. Continue?')) return;
         } else {
             // Merge with empty = do nothing
             return;
         }
    }

    loading.value = true;
    try {
        await api.bulkUpdateSpecs(props.selectedProductIds, validSpecs, operation.value);
        emit('success');
        close();
        alert('Specs updated successfully');
    } catch (e) {
        console.error(e);
        alert('Failed to update specs');
    } finally {
        loading.value = false;
    }
};
</script>

<template>
    <div v-if="modelValue" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" @click.self="close">
        <div class="bg-white rounded-xl w-full max-w-2xl flex flex-col max-h-[90vh]">
            <header class="p-4 border-b flex justify-between items-center bg-gray-50 rounded-t-xl">
                <h2 class="text-lg font-bold text-gray-900">
                    Bulk Edit Specs
                    <span class="text-sm font-normal text-gray-500 ml-2">({{ selectedProductIds.length }} products)</span>
                </h2>
                <button @click="close" class="text-gray-400 hover:text-gray-600">
                    <X class="w-5 h-5" />
                </button>
            </header>
            
            <div class="p-6 overflow-y-auto flex-1">
                <!-- Operation Selector -->
                <div class="mb-6">
                    <label class="block text-sm font-medium text-gray-700 mb-2">Operation</label>
                    <div class="flex gap-4">
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input v-model="operation" type="radio" value="merge" class="text-blue-600 focus:ring-blue-500" />
                            <span class="text-sm text-gray-800">Merge (Add/Update)</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input v-model="operation" type="radio" value="replace" class="text-red-600 focus:ring-red-500" />
                            <span class="text-sm text-gray-800">Replace All (Overwrite)</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input v-model="operation" type="radio" value="delete_keys" class="text-orange-600 focus:ring-orange-500" />
                            <span class="text-sm text-gray-800">Delete Keys</span>
                        </label>
                    </div>
                    <p v-if="operation === 'replace'" class="mt-2 text-xs text-red-600 flex items-center gap-1">
                        <AlertTriangle class="w-3 h-3" /> Warning: This will remove all existing specs and replace them with the list below.
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
                                placeholder="Key (e.g. Color)" 
                                class="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                                :placeholder="operation === 'delete_keys' ? 'Ignored' : 'Value (e.g. Red)'" 
                                class="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:text-gray-400"
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
            
            <footer class="p-4 border-t bg-gray-50 rounded-b-xl flex justify-end gap-3">
                <button @click="close" class="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-800">Cancel</button>
                <button 
                    @click="save" 
                    :disabled="loading"
                    class="px-6 py-2 bg-blue-600 text-white rounded shadow hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2 text-sm font-medium"
                >
                    <div v-if="loading" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                    <Save v-else class="w-4 h-4" />
                    Apply Changes
                </button>
            </footer>
        </div>
    </div>
</template>
