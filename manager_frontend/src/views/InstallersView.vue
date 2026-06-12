<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api, type ManagerStaffResponse } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';
import InstallerEditModal from '../components/InstallerEditModal.vue';

const staff = ref<ManagerStaffResponse[]>([]);
const loading = ref(false);
const error = ref('');
const toast = ref('');

const showModal = ref(false);
const editingStaff = ref<ManagerStaffResponse | null>(null);

const roleLabels: Record<string, string> = {
    owner: 'Владелец',
    manager: 'Менеджер',
    installer: 'Монтажник',
};

const statusLabel = (item: ManagerStaffResponse) => (item.status === 'active' ? 'Активен' : 'В архиве');
const roleLabel = (role?: string | null) => roleLabels[role || 'installer'] || 'Монтажник';

const statusClasses = (item: ManagerStaffResponse) => (
    item.status === 'active'
        ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/30'
        : 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-700/60 dark:text-slate-300 dark:border-slate-600'
);

const roleClasses = (role?: string | null) => {
    if (role === 'owner') return 'bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-500/10 dark:text-violet-300 dark:border-violet-500/30';
    if (role === 'manager') return 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-500/30';
    return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/30';
};

const setToast = (msg: string) => {
    toast.value = msg;
    window.setTimeout(() => { toast.value = ''; }, 3000);
};

const loadStaff = async () => {
    loading.value = true;
    error.value = '';
    try {
        const res = await api.listManagerStaff(1, 100);
        staff.value = res.items;
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        loading.value = false;
    }
};

const openAddModal = () => {
    editingStaff.value = null;
    showModal.value = true;
};

const openEditModal = (item: ManagerStaffResponse) => {
    editingStaff.value = item;
    showModal.value = true;
};

const handleSuccess = () => {
    setToast('Сотрудник сохранен');
    loadStaff();
};

const toggleActive = async (item: ManagerStaffResponse) => {
    const nextStatus = item.status === 'active' ? 'inactive' : 'active';
    try {
        const updated = await api.patchManagerStaff(item.id, { status: nextStatus });
        Object.assign(item, updated);
        setToast('Статус обновлен');
    } catch (e) {
        error.value = getApiErrorMessage(e);
    }
};

onMounted(() => {
    loadStaff();
});
</script>

<template>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        <Transition name="toast">
            <div v-if="toast" class="fixed top-20 right-8 z-50 bg-teal-600 border border-teal-500 text-white px-4 py-3 rounded-lg shadow-xl shadow-teal-900/30 flex items-center gap-3">
                <span class="material-icons-round text-xl">check_circle</span>
                <span class="text-sm font-medium">{{ toast }}</span>
            </div>
        </Transition>

        <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-8">
            <div>
                <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
                    <span class="material-icons-round text-teal-600 dark:text-teal-400">badge</span>
                    Сотрудники
                </h1>
                <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
                    Профили, доступ в менеджер, Telegram и назначение на работы
                </p>
            </div>

            <button
                @click="openAddModal"
                class="inline-flex items-center justify-center gap-2 bg-teal-600 hover:bg-teal-500 active:bg-teal-700 text-white font-medium py-2.5 px-4 rounded-lg shadow-lg shadow-teal-900/30 transition-all text-sm"
            >
                <span class="material-icons-round text-[18px]">add</span>
                Добавить
            </button>
        </div>

        <div v-if="error" class="bg-red-500/10 border border-red-500/50 text-red-500 dark:text-red-300 p-4 rounded-xl mb-6">
            {{ error }}
        </div>

        <div v-if="loading && !staff.length" class="flex justify-center py-20">
            <div class="w-8 h-8 rounded-full border-4 border-slate-200 dark:border-slate-700 border-t-teal-500 animate-spin"></div>
        </div>

        <div v-else class="bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 overflow-hidden">
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200 dark:divide-slate-700/50">
                    <thead class="bg-gray-50 dark:bg-slate-800/80">
                        <tr>
                            <th class="px-5 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider">Сотрудник</th>
                            <th class="px-5 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider">Роль</th>
                            <th class="px-5 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider hidden lg:table-cell">Доступ</th>
                            <th class="px-5 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider hidden md:table-cell">Telegram</th>
                            <th class="px-5 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider hidden xl:table-cell">Работы</th>
                            <th class="px-5 py-4 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider">Статус</th>
                            <th class="px-5 py-4 text-right text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider">Действия</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-200 dark:divide-slate-700/50 bg-white dark:bg-[#1e293b]">
                        <tr v-for="item in staff" :key="item.id" class="hover:bg-gray-50 dark:hover:bg-slate-800/50 transition-colors group">
                            <td class="px-5 py-4">
                                <div class="flex items-center min-w-[220px]">
                                    <div class="h-9 w-9 rounded-full bg-gray-100 dark:bg-slate-700 flex items-center justify-center border border-gray-200 dark:border-slate-600 text-gray-600 dark:text-slate-300 font-bold text-xs shrink-0">
                                        {{ item.display_name.substring(0, 2).toUpperCase() }}
                                    </div>
                                    <div class="ml-3 min-w-0">
                                        <div class="text-sm font-medium text-gray-900 dark:text-slate-100 truncate">{{ item.display_name }}</div>
                                        <div class="text-xs text-gray-500 dark:text-slate-500 truncate">
                                            {{ item.phone || item.email || 'Контакты не заполнены' }}
                                        </div>
                                    </div>
                                </div>
                            </td>
                            <td class="px-5 py-4">
                                <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap" :class="roleClasses(item.primary_role)">
                                    {{ roleLabel(item.primary_role) }}
                                </span>
                            </td>
                            <td class="px-5 py-4 hidden lg:table-cell">
                                <div class="text-sm text-gray-700 dark:text-slate-300">
                                    <div>{{ item.username || 'Логин не задан' }}</div>
                                    <div class="text-xs text-gray-500 dark:text-slate-500">
                                        {{ item.has_password ? 'Пароль задан' : 'Пароль не задан' }}
                                    </div>
                                </div>
                            </td>
                            <td class="px-5 py-4 hidden md:table-cell">
                                <div class="text-sm text-gray-700 dark:text-slate-300">
                                    <div v-if="item.telegram_id">{{ item.telegram_id }}</div>
                                    <div v-else class="text-gray-400 dark:text-slate-500">Не привязан</div>
                                    <div v-if="item.telegram_username" class="text-xs text-blue-600 dark:text-blue-400">@{{ item.telegram_username }}</div>
                                </div>
                            </td>
                            <td class="px-5 py-4 hidden xl:table-cell">
                                <div class="text-sm text-gray-700 dark:text-slate-300">
                                    <span v-if="item.is_assignable_installer" class="font-medium text-emerald-600 dark:text-emerald-400">Можно назначать</span>
                                    <span v-else class="text-gray-500 dark:text-slate-500">Офисный профиль</span>
                                    <div class="text-xs text-gray-500 dark:text-slate-500">
                                        {{ item.default_rate ? item.default_rate + ' BYN' : 'Ставка не задана' }}
                                    </div>
                                </div>
                            </td>
                            <td class="px-5 py-4">
                                <div class="flex items-center gap-3">
                                    <span class="hidden sm:inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap" :class="statusClasses(item)">
                                        {{ statusLabel(item) }}
                                    </span>
                                    <label class="relative inline-flex items-center cursor-pointer" @click.prevent="toggleActive(item)" :title="item.status === 'active' ? 'Перевести в архив' : 'Вернуть в активные'">
                                        <input type="checkbox" :checked="item.status === 'active'" class="sr-only peer" />
                                        <div class="w-9 h-5 bg-gray-200 dark:bg-slate-600 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-teal-500 transition-colors"></div>
                                    </label>
                                </div>
                            </td>
                            <td class="px-5 py-4 text-right">
                                <button
                                    @click="openEditModal(item)"
                                    class="p-2 text-gray-500 hover:text-gray-900 border-gray-200 hover:bg-gray-50 dark:text-slate-400 dark:hover:text-white bg-white dark:bg-slate-800 dark:hover:bg-slate-700 rounded-lg border dark:border-slate-600 transition-colors inline-flex items-center shadow-sm"
                                    title="Редактировать"
                                >
                                    <span class="material-icons-round text-sm">edit</span>
                                </button>
                            </td>
                        </tr>

                        <tr v-if="staff.length === 0 && !loading">
                            <td colspan="7" class="px-6 py-12 text-center text-gray-500 dark:text-slate-400">
                                Сотрудники не найдены. Добавьте первого сотрудника.
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <InstallerEditModal
            v-model="showModal"
            :staff-user="editingStaff"
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
