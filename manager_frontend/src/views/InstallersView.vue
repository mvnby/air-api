<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { api } from '../api';
import type { ManagerInstallerResponse } from '../client';
import { getApiErrorMessage } from '../utils/api-errors';
import InstallerEditModal from '../components/InstallerEditModal.vue';

const installers = ref<ManagerInstallerResponse[]>([]);
const loading = ref(false);
const error = ref('');
const toast = ref('');

const showModal = ref(false);
const editingInstaller = ref<ManagerInstallerResponse | null>(null);

const setToast = (msg: string) => {
    toast.value = msg;
    window.setTimeout(() => { toast.value = ''; }, 3000);
}

const loadInstallers = async () => {
    loading.value = true;
    error.value = '';
    try {
        const res = await api.getManagerInstallers(1, 100);
        installers.value = res.items;
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        loading.value = false;
    }
};

const openAddModal = () => {
    editingInstaller.value = null;
    showModal.value = true;
};

const openEditModal = (inst: ManagerInstallerResponse) => {
    editingInstaller.value = inst;
    showModal.value = true;
};

const handleSuccess = () => {
    setToast('Монтажник сохранен');
    loadInstallers();
};

const toggleActive = async (inst: ManagerInstallerResponse) => {
    try {
        await api.updateManagerInstaller(inst.id, { is_active: !inst.is_active });
        inst.is_active = !inst.is_active;
        setToast('Статус обновлен');
    } catch (e) {
        console.error('Failed to toggle active status', e);
    }
};

onMounted(() => {
    loadInstallers();
});
</script>

<template>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        <!-- Toast Notification -->
        <Transition name="toast">
            <div v-if="toast" class="fixed top-20 right-8 z-50 bg-teal-600 border border-teal-500 text-white px-4 py-3 rounded-lg shadow-xl shadow-teal-900/30 flex items-center gap-3">
                <span class="material-icons-round text-xl">check_circle</span>
                <span class="text-sm font-medium">{{ toast }}</span>
            </div>
        </Transition>

        <div class="flex justify-between items-center mb-8">
            <div>
                <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
                    <span class="material-icons-round text-teal-600 dark:text-teal-400">engineering</span>
                    Бригады монтажников
                </h1>
                <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
                    Управление монтажниками, их ставками и доступностью для заказов
                </p>
            </div>
            
            <button 
                @click="openAddModal"
                class="flex items-center gap-2 bg-teal-600 hover:bg-teal-500 active:bg-teal-700 text-white font-medium py-2.5 px-4 rounded-lg shadow-lg shadow-teal-900/40 transition-all text-sm"
            >
                <span class="material-icons-round text-[18px]">add</span>
                Добавить
            </button>
        </div>

        <div v-if="error" class="bg-red-500/10 border border-red-500/50 text-red-400 p-4 rounded-xl mb-6">
            {{ error }}
        </div>

        <div v-if="loading && !installers.length" class="flex justify-center py-20">
            <div class="w-8 h-8 rounded-full border-4 border-slate-700 border-t-teal-500 animate-spin"></div>
        </div>

        <div v-else class="bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 overflow-hidden">
            <table class="min-w-full divide-y divide-gray-200 dark:divide-slate-700/50">
                <thead class="bg-gray-50 dark:bg-slate-800/80">
                    <tr>
                        <th class="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-1/3">
                            Имя
                        </th>
                        <th class="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider hidden sm:table-cell">
                            Телеграм ID
                        </th>
                        <th class="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider hidden sm:table-cell">
                            Базовая ставка
                        </th>
                        <th class="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                            Активен
                        </th>
                        <th class="px-6 py-4 text-right text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                            Действия
                        </th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-200 dark:divide-slate-700/50 bg-white dark:bg-[#1e293b]">
                    <tr v-for="inst in installers" :key="inst.id" class="hover:bg-gray-50 dark:hover:bg-slate-800/50 transition-colors group">
                        <td class="px-6 py-4">
                            <div class="flex items-center">
                                <div class="h-8 w-8 rounded-full bg-gray-100 dark:bg-slate-700 flex items-center justify-center border border-gray-200 dark:border-slate-600 text-gray-600 dark:text-slate-300 font-bold text-xs ring-2 ring-transparent group-hover:ring-gray-200 dark:group-hover:ring-slate-600 transition-all flex-shrink-0">
                                    {{ inst.name.substring(0, 2).toUpperCase() }}
                                </div>
                                <div class="ml-4">
                                    <div class="text-sm font-medium text-gray-900 dark:text-slate-100">{{ inst.name }}</div>
                                    <div class="text-xs text-gray-500 dark:text-slate-500 sm:hidden mt-0.5">
                                        {{ inst.default_rate ? inst.default_rate + ' BYN' : 'Ставка не задана' }}
                                    </div>
                                </div>
                            </div>
                        </td>
                        <td class="px-6 py-4 hidden sm:table-cell">
                            <span v-if="inst.telegram_id" class="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-500/20">
                                {{ inst.telegram_id }}
                            </span>
                            <span v-else class="text-gray-400 dark:text-slate-500 text-sm italic">-</span>
                        </td>
                        <td class="px-6 py-4 hidden sm:table-cell">
                            <div class="text-sm text-gray-700 dark:text-slate-300">
                                <span v-if="inst.default_rate" class="font-medium text-emerald-600 dark:text-emerald-400">{{ inst.default_rate }} BYN</span>
                                <span v-else class="text-gray-500 dark:text-slate-500 italic">Не задана</span>
                            </div>
                        </td>
                        <td class="px-6 py-4">
                            <label class="relative inline-flex items-center cursor-pointer" @click.prevent="toggleActive(inst)">
                                <input type="checkbox" :checked="inst.is_active" class="sr-only peer" />
                                <div class="w-9 h-5 bg-gray-200 dark:bg-slate-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-teal-500 transition-colors"></div>
                            </label>
                        </td>
                        <td class="px-6 py-4 text-right">
                            <button
                                @click="openEditModal(inst)"
                                class="p-2 text-gray-500 hover:text-gray-900 border-gray-200 hover:bg-gray-50 dark:text-slate-400 dark:hover:text-white bg-white dark:bg-slate-800 dark:hover:bg-slate-700 rounded-lg border dark:border-slate-600 transition-colors inline-flex items-center shadow-sm"
                                title="Редактировать"
                            >
                                <span class="material-icons-round text-sm">edit</span>
                            </button>
                        </td>
                    </tr>
                    
                    <tr v-if="installers.length === 0 && !loading">
                        <td colspan="5" class="px-6 py-12 text-center text-gray-500 dark:text-slate-400">
                            Монтажники не найдены. Создайте первую бригаду!
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <InstallerEditModal 
            v-model="showModal"
            :installer="editingInstaller"
            @success="handleSuccess"
        />
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
