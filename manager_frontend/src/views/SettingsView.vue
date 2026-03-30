<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { api } from '../api';
import type { ManagerSettingResponse, ManagerSettingUpdatePayload } from '../client';
import { ManagerSettingsService } from '../client';
import { getApiErrorMessage } from '../utils/api-errors';

const settings = ref<ManagerSettingResponse[]>([]);
const loading = ref(false);
const error = ref('');
const toast = ref('');
const toastType = ref<'success' | 'error'>('success');

// A set to keep track of which settings are currently being saved
const savingKeys = ref<Set<string>>(new Set());

// Create form
const showCreateForm = ref(false);
const newKey = ref('');
const newValue = ref('');
const newDescription = ref('');
const creating = ref(false);

const setToast = (msg: string, type: 'success' | 'error' = 'success') => {
    toast.value = msg;
    toastType.value = type;
    window.setTimeout(() => { toast.value = ''; }, 3000);
}

const loadSettings = async () => {
    loading.value = true;
    error.value = '';
    try {
        const res = await api.listManagerSettings();
        settings.value = res.items;
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        loading.value = false;
    }
};

const saveSetting = async (setting: ManagerSettingResponse) => {
    if (savingKeys.value.has(setting.key)) return;
    
    savingKeys.value.add(setting.key);
    error.value = '';
    
    try {
        const payload: ManagerSettingUpdatePayload = {
            value: setting.value,
            description: setting.description || undefined
        };
        const updated = await api.updateManagerSetting(setting.key, payload);
        
        // Update local state with the exact response
        const index = settings.value.findIndex(s => s.key === updated.key);
        if (index !== -1) {
            settings.value[index] = updated;
        }
        
        setToast('Настройка сохранена');
    } catch (e) {
        error.value = getApiErrorMessage(e);
        // Reload to revert to actual state in case of error
        await loadSettings(); 
    } finally {
        savingKeys.value.delete(setting.key);
    }
};

const createSetting = async () => {
    if (!newKey.value.trim() || !newValue.value.trim()) {
        setToast('Заполните ключ и значение', 'error');
        return;
    }
    creating.value = true;
    error.value = '';
    try {
        await ManagerSettingsService.createManagerSetting({
            key: newKey.value.trim(),
            value: newValue.value.trim(),
            description: newDescription.value.trim() || undefined,
        });
        setToast('Настройка создана');
        newKey.value = '';
        newValue.value = '';
        newDescription.value = '';
        showCreateForm.value = false;
        await loadSettings();
    } catch (e) {
        setToast(getApiErrorMessage(e), 'error');
    } finally {
        creating.value = false;
    }
};

const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
};

onMounted(() => {
    loadSettings();
});
</script>

<template>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        <!-- Toast Notification -->
        <Transition name="toast">
            <div v-if="toast" class="fixed top-20 right-8 z-50 px-4 py-3 rounded-lg shadow-xl flex items-center gap-3"
                 :class="toastType === 'success' ? 'bg-teal-600 border border-teal-500 text-white shadow-teal-900/30' : 'bg-red-600 border border-red-500 text-white shadow-red-900/30'">
                <span class="material-icons-round text-xl">{{ toastType === 'success' ? 'check_circle' : 'error' }}</span>
                <span class="text-sm font-medium">{{ toast }}</span>
            </div>
        </Transition>

        <div class="flex justify-between items-center mb-8">
            <div>
                <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
                    <span class="material-icons-round text-teal-600 dark:text-teal-400">settings</span>
                    Настройки сайта
                </h1>
                <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
                    Управление глобальными параметрами и конфигурацией сайта
                </p>
            </div>
            
            <div class="flex items-center gap-2">
                <button 
                    @click="showCreateForm = !showCreateForm"
                    class="flex items-center gap-2 bg-teal-600 hover:bg-teal-500 active:bg-teal-700 text-white font-medium py-2.5 px-4 rounded-lg shadow-sm transition-all text-sm"
                >
                    <span class="material-icons-round text-[18px]">{{ showCreateForm ? 'close' : 'add_circle' }}</span>
                    {{ showCreateForm ? 'Отмена' : 'Добавить' }}
                </button>
                <button 
                    @click="loadSettings"
                    class="flex items-center gap-2 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 active:bg-gray-100 dark:active:bg-slate-600 text-gray-700 dark:text-slate-300 font-medium py-2.5 px-4 rounded-lg shadow-sm transition-all text-sm"
                    :disabled="loading"
                >
                    <span class="material-icons-round text-[18px]" :class="{'animate-spin': loading}">refresh</span>
                    Обновить
                </button>
            </div>
        </div>

        <!-- Create Setting Form -->
        <Transition name="toast">
            <div v-if="showCreateForm" class="mb-6 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border-2 border-teal-500/50 p-6">
                <h3 class="text-base font-semibold text-gray-900 dark:text-slate-200 mb-4 flex items-center gap-2">
                    <span class="material-icons-round text-teal-500 text-[20px]">add_circle</span>
                    Новый параметр
                </h3>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Ключ *</label>
                        <input
                            v-model="newKey"
                            type="text"
                            class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm font-mono text-sm"
                            placeholder="contract_templates"
                            :disabled="creating"
                        />
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Значение *</label>
                        <input
                            v-model="newValue"
                            type="text"
                            class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm text-sm"
                            placeholder='[{"id": "...", "name": "..."}]'
                            :disabled="creating"
                        />
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Описание</label>
                        <div class="flex gap-2">
                            <input
                                v-model="newDescription"
                                type="text"
                                class="flex-1 bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm text-sm"
                                placeholder="Описание параметра"
                                :disabled="creating"
                            />
                            <button
                                @click="createSetting"
                                class="flex items-center gap-1 px-4 py-2 text-sm font-medium text-white bg-teal-600 hover:bg-teal-500 active:bg-teal-700 transition-colors rounded-lg disabled:opacity-50 shadow-sm whitespace-nowrap"
                                :disabled="creating || !newKey.trim() || !newValue.trim()"
                            >
                                <span v-if="creating" class="material-icons-round text-sm animate-spin">refresh</span>
                                <span v-else class="material-icons-round text-sm">save</span>
                                Создать
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </Transition>

        <div v-if="error" class="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/50 text-red-600 dark:text-red-400 p-4 rounded-xl mb-6">
            {{ error }}
        </div>

        <div v-if="loading && !settings.length" class="flex justify-center py-20">
            <div class="w-8 h-8 rounded-full border-4 border-gray-200 dark:border-slate-700 border-t-teal-500 animate-spin"></div>
        </div>

        <div v-else class="space-y-4">
            <div v-for="setting in settings" :key="setting.key" class="bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-6 flex flex-col md:flex-row gap-6 items-start md:items-center transition-colors">
                <div class="flex-1 space-y-2 w-full">
                    <div>
                        <h3 class="text-sm font-semibold text-gray-900 dark:text-slate-200 font-mono bg-gray-100 dark:bg-slate-800 px-2 py-1 rounded inline-block mb-1 border border-gray-200 dark:border-slate-700">
                            {{ setting.key }}
                        </h3>
                        <p class="text-xs text-gray-500 dark:text-slate-400">
                            Изменено: {{ formatDate(setting.updated_at) }}
                        </p>
                    </div>
                </div>
                
                <div class="flex-1 w-full space-y-3">
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Значение</label>
                        <input
                            v-model="setting.value"
                            type="text"
                            class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm"
                            :disabled="savingKeys.has(setting.key)"
                        />
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Описание</label>
                        <input
                            v-model="setting.description"
                            type="text"
                            class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-teal-500 transition-colors shadow-sm text-sm"
                            :disabled="savingKeys.has(setting.key)"
                            placeholder="Добавьте описание..."
                        />
                    </div>
                </div>
                
                <div class="md:w-32 flex-shrink-0 flex justify-end w-full md:block">
                    <button
                        @click="saveSetting(setting)"
                        class="w-full flex justify-center items-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-teal-600 hover:bg-teal-500 active:bg-teal-700 transition-colors rounded-lg disabled:opacity-50 shadow-sm"
                        :disabled="savingKeys.has(setting.key)"
                    >
                        <span v-if="savingKeys.has(setting.key)" class="material-icons-round text-sm animate-spin">refresh</span>
                        <span v-else class="material-icons-round text-sm">save</span>
                        Сохранить
                    </button>
                </div>
            </div>
            
            <div v-if="settings.length === 0 && !loading" class="bg-white dark:bg-[#1e293b] rounded-xl border border-gray-200 dark:border-slate-700/60 p-12 text-center">
                <p class="text-gray-500 dark:text-slate-400">Настройки не найдены.</p>
            </div>
        </div>
    </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.toast-enter-from,
.toast-leave-to {
    opacity: 0;
    transform: translateY(-1rem) translateX(2rem);
}
</style>
