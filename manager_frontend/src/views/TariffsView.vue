<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { api } from '../api';
import type { ManagerTariffResponse } from '../client';
import { getApiErrorMessage } from '../utils/api-errors';
import TariffEditModal from '../components/TariffEditModal.vue';

const tariffs = ref<ManagerTariffResponse[]>([]);
const loading = ref(false);
const error = ref('');
const toast = ref('');

const showModal = ref(false);
const editingTariff = ref<ManagerTariffResponse | null>(null);

const setToast = (msg: string) => {
    toast.value = msg;
    window.setTimeout(() => { toast.value = ''; }, 3000);
}

const loadTariffs = async () => {
    loading.value = true;
    error.value = '';
    try {
        const res = await api.listManagerTariffs();
        tariffs.value = res.items;
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        loading.value = false;
    }
};

const openAddModal = () => {
    editingTariff.value = null;
    showModal.value = true;
};

const openEditModal = (tariff: ManagerTariffResponse) => {
    editingTariff.value = tariff;
    showModal.value = true;
};

const confirmDelete = async (tariff: ManagerTariffResponse) => {
    if (confirm(`Удалить тариф "${tariff.category} ${tariff.power_range}"?`)) {
        try {
            await api.deleteManagerTariff(tariff.id);
            setToast('Тариф удален');
            await loadTariffs();
        } catch (e) {
            error.value = getApiErrorMessage(e);
        }
    }
};

const handleSuccess = () => {
    setToast('Тариф сохранен');
    loadTariffs();
};

onMounted(() => {
    loadTariffs();
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
                    <span class="material-icons-round text-teal-600 dark:text-teal-400">payments</span>
                    Тарифы на монтаж
                </h1>
                <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
                    Управление ценами на установку в зависимости от категории и мощности
                </p>
            </div>
            
            <button 
                @click="openAddModal"
                class="flex items-center gap-2 bg-teal-600 hover:bg-teal-500 active:bg-teal-700 text-white font-medium py-2.5 px-4 rounded-lg shadow-lg shadow-teal-900/40 transition-all text-sm"
            >
                <span class="material-icons-round text-[18px]">add</span>
                Добавить тариф
            </button>
        </div>

        <div v-if="error" class="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/50 text-red-600 dark:text-red-400 p-4 rounded-xl mb-6">
            {{ error }}
        </div>

        <div v-if="loading && !tariffs.length" class="flex justify-center py-20">
            <div class="w-8 h-8 rounded-full border-4 border-gray-200 dark:border-slate-700 border-t-teal-500 animate-spin"></div>
        </div>

        <div v-else class="bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 overflow-hidden">
            <table class="min-w-full divide-y divide-gray-200 dark:divide-slate-700/50">
                <thead class="bg-gray-50 dark:bg-slate-800/80">
                    <tr>
                        <th class="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                            Категория
                        </th>
                        <th class="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                            Базовая цена
                        </th>
                        <th class="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider hidden sm:table-cell">
                            Доп. метр
                        </th>
                        <th class="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider hidden md:table-cell">
                            Включено м.
                        </th>
                        <th class="px-6 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider hidden lg:table-cell">
                            Фикс.
                        </th>
                        <th class="px-6 py-4 text-right text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                            Действия
                        </th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-200 dark:divide-slate-700/50 bg-white dark:bg-[#1e293b]">
                    <tr v-for="t in tariffs" :key="t.id" class="hover:bg-gray-50 dark:hover:bg-slate-800/50 transition-colors group">
                        <td class="px-6 py-4">
                            <div class="text-sm font-medium text-gray-900 dark:text-slate-100 max-w-xs break-words">
                                {{ t.category }}
                            </div>
                            <div class="text-xs text-gray-500 dark:text-slate-500 mt-1 flex gap-2" v-if="t.power_range || t.comment">
                                <span v-if="t.power_range" class="px-2 py-0.5 bg-gray-100 dark:bg-slate-700 rounded">{{ t.power_range }}</span>
                                <span v-if="t.comment" class="italic">{{ t.comment }}</span>
                            </div>
                        </td>
                        <td class="px-6 py-4">
                            <span class="font-medium text-emerald-600 dark:text-emerald-400 text-sm whitespace-nowrap">{{ t.base_price }} BYN</span>
                        </td>
                        <td class="px-6 py-4 hidden sm:table-cell">
                            <span class="text-sm text-gray-700 dark:text-slate-300 font-medium whitespace-nowrap">{{ t.extra_pipe_price }} BYN</span>
                        </td>
                        <td class="px-6 py-4 hidden md:table-cell text-sm text-gray-600 dark:text-slate-400">
                            {{ t.included_pipe_meters }} м
                        </td>
                        <td class="px-6 py-4 hidden lg:table-cell">
                            <span v-if="t.is_fixed" class="material-icons-round text-teal-600 dark:text-teal-400 text-[18px]">check_circle</span>
                            <span v-else class="material-icons-round text-gray-400 dark:text-slate-600 text-[18px]">cancel</span>
                        </td>
                        <td class="px-6 py-4 text-right">
                            <div class="flex justify-end gap-2">
                                <button
                                    @click="openEditModal(t)"
                                    class="p-2 text-gray-500 hover:text-gray-900 border border-gray-200 hover:bg-gray-50 dark:text-slate-400 dark:hover:text-white bg-white dark:bg-slate-800 dark:hover:bg-slate-700 rounded-lg dark:border-slate-600 transition-colors inline-flex items-center shadow-sm"
                                    title="Редактировать"
                                >
                                    <span class="material-icons-round text-sm">edit</span>
                                </button>
                                <button
                                    @click="confirmDelete(t)"
                                    class="p-2 text-red-500 hover:text-red-700 border border-red-200 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 bg-white dark:bg-slate-800 dark:hover:bg-slate-700 rounded-lg dark:border-slate-600 transition-colors inline-flex items-center shadow-sm opacity-0 group-hover:opacity-100 lg:opacity-100"
                                    title="Удалить"
                                >
                                    <span class="material-icons-round text-sm">delete</span>
                                </button>
                            </div>
                        </td>
                    </tr>
                    
                    <tr v-if="tariffs.length === 0 && !loading">
                        <td colspan="6" class="px-6 py-12 text-center text-gray-500 dark:text-slate-400">
                            Тарифы не найдены. Создайте первый тариф!
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <TariffEditModal 
            v-model="showModal"
            :tariff="editingTariff"
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
