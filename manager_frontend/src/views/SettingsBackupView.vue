<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { api } from '../api';
import type { ManagerBackupItemResponse, ManagerRestoreJobStatusResponse } from '../client';
import { getApiErrorMessage } from '../utils/api-errors';

const backups = ref<ManagerBackupItemResponse[]>([]);
const loading = ref(false);
const error = ref('');

const kindFilter = ref<'all' | 'db' | 'media'>('all');

const toast = ref('');
const toastType = ref<'success' | 'error'>('success');

const restoreModalOpen = ref(false);
const restoreWord = ref('');
const selectedBackup = ref<ManagerBackupItemResponse | null>(null);
const restoreLaunching = ref(false);

const restoreJob = ref<ManagerRestoreJobStatusResponse | null>(null);
const restorePollingJobId = ref<string | null>(null);
const restorePollingHandle = ref<number | null>(null);

const STAGE_LABELS: Record<string, string> = {
    queued: 'В очереди',
    creating_safety_dump: 'Создаём safety dump',
    downloading_backup: 'Скачиваем backup',
    decompressing_backup: 'Распаковка SQL',
    restoring_database: 'Восстанавливаем БД',
    completed: 'Готово',
    failed: 'Ошибка',
};

const setToast = (message: string, type: 'success' | 'error' = 'success') => {
    toast.value = message;
    toastType.value = type;
    window.setTimeout(() => {
        if (toast.value === message) {
            toast.value = '';
        }
    }, 3500);
};

const restoring = computed(() => {
    const status = restoreJob.value?.status;
    return status === 'queued' || status === 'running';
});

const filteredBackups = computed(() => {
    if (kindFilter.value === 'all') return backups.value;
    return backups.value.filter((item) => item.kind === kindFilter.value);
});

const restoreStageLabel = computed(() => {
    const stage = restoreJob.value?.stage || '';
    return STAGE_LABELS[stage] || stage || '—';
});

const formatDate = (value?: string) => {
    if (!value) return '—';
    return new Date(value).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
};

const formatBytes = (size?: number | null) => {
    if (!size || size <= 0) return '—';
    const units = ['B', 'KB', 'MB', 'GB'];
    let value = size;
    let idx = 0;
    while (value >= 1024 && idx < units.length - 1) {
        value /= 1024;
        idx += 1;
    }
    return `${value.toFixed(value < 10 && idx > 0 ? 1 : 0)} ${units[idx]}`;
};

const loadBackups = async () => {
    loading.value = true;
    error.value = '';
    try {
        const response = await api.listManagerBackups();
        backups.value = response.items;
    } catch (exc) {
        error.value = getApiErrorMessage(exc);
    } finally {
        loading.value = false;
    }
};

const stopPolling = () => {
    if (restorePollingHandle.value !== null) {
        window.clearInterval(restorePollingHandle.value);
        restorePollingHandle.value = null;
    }
    restorePollingJobId.value = null;
};

const refreshRestoreStatus = async () => {
    const jobId = restorePollingJobId.value;
    if (!jobId) return;
    try {
        const statusPayload = await api.getManagerBackupRestoreStatus(jobId);
        restoreJob.value = statusPayload;
        if (statusPayload.status === 'success') {
            stopPolling();
            setToast('Восстановление базы завершено успешно', 'success');
        } else if (statusPayload.status === 'failed') {
            stopPolling();
            setToast(`Восстановление завершилось ошибкой: ${statusPayload.error || 'unknown error'}`, 'error');
        }
    } catch (exc) {
        stopPolling();
        setToast(getApiErrorMessage(exc), 'error');
    }
};

const startPolling = (jobId: string) => {
    stopPolling();
    restorePollingJobId.value = jobId;
    void refreshRestoreStatus();
    restorePollingHandle.value = window.setInterval(() => {
        void refreshRestoreStatus();
    }, 2000);
};

const openRestoreModal = (item: ManagerBackupItemResponse) => {
    selectedBackup.value = item;
    restoreWord.value = '';
    restoreModalOpen.value = true;
};

const closeRestoreModal = () => {
    restoreModalOpen.value = false;
    selectedBackup.value = null;
    restoreWord.value = '';
};

const startRestore = async () => {
    if (!selectedBackup.value) return;
    if (restoreWord.value.trim() !== 'RESTORE') {
        setToast('Введите RESTORE для подтверждения', 'error');
        return;
    }

    restoreLaunching.value = true;
    try {
        const startPayload = await api.startManagerBackupRestore(selectedBackup.value.id);
        restoreJob.value = {
            job_id: startPayload.job_id,
            file_id: selectedBackup.value.id,
            file_name: selectedBackup.value.name,
            kind: selectedBackup.value.kind,
            status: startPayload.status,
            stage: startPayload.stage,
            error: null,
            started_at: null,
            finished_at: null,
            safety_dump_path: null,
        };
        closeRestoreModal();
        setToast('Восстановление запущено. Не закрывайте manager до завершения.');
        startPolling(startPayload.job_id);
    } catch (exc) {
        setToast(getApiErrorMessage(exc), 'error');
    } finally {
        restoreLaunching.value = false;
    }
};

onMounted(() => {
    void loadBackups();
});

onBeforeUnmount(() => {
    stopPolling();
});
</script>

<template>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        <Transition name="toast">
            <div
                v-if="toast"
                class="fixed top-20 right-8 z-50 px-4 py-3 rounded-lg shadow-xl flex items-center gap-3"
                :class="toastType === 'success' ? 'bg-teal-600 border border-teal-500 text-white shadow-teal-900/30' : 'bg-red-600 border border-red-500 text-white shadow-red-900/30'"
            >
                <span class="material-icons-round text-xl">{{ toastType === 'success' ? 'check_circle' : 'error' }}</span>
                <span class="text-sm font-medium">{{ toast }}</span>
            </div>
        </Transition>

        <div class="mb-8">
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
                <span class="material-icons-round text-red-500">warning</span>
                DR / Восстановление из бэкапов
            </h1>
            <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
                Критическая операция: восстановление перезапишет текущую базу данных.
            </p>
        </div>

        <div class="mb-6 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/40 rounded-xl p-4">
            <div class="text-sm text-red-700 dark:text-red-300 font-medium">
                Перед восстановлением автоматически создаётся safety dump текущего состояния БД.
            </div>
            <div class="text-xs mt-1 text-red-600 dark:text-red-200/80">
                DR v1 восстанавливает только базу данных. Медиа-файлы в этот поток не входят.
            </div>
        </div>

        <div v-if="restoreJob" class="mb-6 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-4">
            <div class="flex items-center justify-between gap-3 flex-wrap">
                <div>
                    <p class="text-sm text-gray-500 dark:text-slate-400">Текущий restore job</p>
                    <p class="text-sm font-semibold text-gray-900 dark:text-slate-100 break-all">{{ restoreJob.job_id }}</p>
                </div>
                <span
                    class="px-2.5 py-1 rounded-full text-xs font-semibold"
                    :class="restoreJob.status === 'success'
                        ? 'bg-teal-100 text-teal-700 dark:bg-teal-500/20 dark:text-teal-300'
                        : restoreJob.status === 'failed'
                            ? 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300'
                            : 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300'"
                >
                    {{ restoreJob.status }}
                </span>
            </div>
            <div class="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                <div>
                    <p class="text-gray-500 dark:text-slate-400">Стадия</p>
                    <p class="font-medium text-gray-900 dark:text-slate-100">{{ restoreStageLabel }}</p>
                </div>
                <div>
                    <p class="text-gray-500 dark:text-slate-400">Начало</p>
                    <p class="font-medium text-gray-900 dark:text-slate-100">{{ formatDate(restoreJob.started_at || undefined) }}</p>
                </div>
                <div>
                    <p class="text-gray-500 dark:text-slate-400">Окончание</p>
                    <p class="font-medium text-gray-900 dark:text-slate-100">{{ formatDate(restoreJob.finished_at || undefined) }}</p>
                </div>
            </div>
            <p v-if="restoreJob.error" class="mt-3 text-sm text-red-600 dark:text-red-300">
                Ошибка: {{ restoreJob.error }}
            </p>
        </div>

        <div class="mb-4 flex flex-wrap gap-2">
            <button
                class="px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors"
                :class="kindFilter === 'all'
                    ? 'bg-teal-600 text-white border-teal-600'
                    : 'bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-300 border-gray-200 dark:border-slate-700'"
                @click="kindFilter = 'all'"
            >
                Все
            </button>
            <button
                class="px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors"
                :class="kindFilter === 'db'
                    ? 'bg-teal-600 text-white border-teal-600'
                    : 'bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-300 border-gray-200 dark:border-slate-700'"
                @click="kindFilter = 'db'"
            >
                DB
            </button>
            <button
                class="px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors"
                :class="kindFilter === 'media'
                    ? 'bg-teal-600 text-white border-teal-600'
                    : 'bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-300 border-gray-200 dark:border-slate-700'"
                @click="kindFilter = 'media'"
            >
                Media
            </button>
            <button
                class="ml-auto px-3 py-1.5 rounded-lg text-sm font-medium border bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-300 border-gray-200 dark:border-slate-700 hover:bg-gray-50 dark:hover:bg-slate-700"
                @click="loadBackups"
                :disabled="loading"
            >
                {{ loading ? 'Обновление…' : 'Обновить список' }}
            </button>
        </div>

        <div v-if="error" class="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/50 text-red-600 dark:text-red-400 p-4 rounded-xl mb-6">
            {{ error }}
        </div>

        <div class="bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 overflow-hidden">
            <table class="w-full text-sm">
                <thead class="bg-gray-50 dark:bg-slate-800/70 border-b border-gray-200 dark:border-slate-700">
                    <tr class="text-left">
                        <th class="px-4 py-3 text-gray-600 dark:text-slate-300 font-semibold">Файл</th>
                        <th class="px-4 py-3 text-gray-600 dark:text-slate-300 font-semibold">Тип</th>
                        <th class="px-4 py-3 text-gray-600 dark:text-slate-300 font-semibold">Дата</th>
                        <th class="px-4 py-3 text-gray-600 dark:text-slate-300 font-semibold">Размер</th>
                        <th class="px-4 py-3 text-gray-600 dark:text-slate-300 font-semibold text-right">Действие</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-if="loading && backups.length === 0">
                        <td colspan="5" class="px-4 py-8 text-center text-gray-500 dark:text-slate-400">Загрузка...</td>
                    </tr>
                    <tr v-else-if="filteredBackups.length === 0">
                        <td colspan="5" class="px-4 py-8 text-center text-gray-500 dark:text-slate-400">Бэкапы не найдены</td>
                    </tr>
                    <tr
                        v-for="item in filteredBackups"
                        :key="item.id"
                        class="border-b border-gray-100 dark:border-slate-800/60 last:border-0"
                    >
                        <td class="px-4 py-3 text-gray-900 dark:text-slate-100 break-all">{{ item.name }}</td>
                        <td class="px-4 py-3">
                            <span
                                class="px-2 py-0.5 rounded text-xs font-medium"
                                :class="item.kind === 'db'
                                    ? 'bg-teal-100 text-teal-700 dark:bg-teal-500/20 dark:text-teal-300'
                                    : 'bg-slate-100 text-slate-700 dark:bg-slate-500/20 dark:text-slate-300'"
                            >
                                {{ item.kind }}
                            </span>
                        </td>
                        <td class="px-4 py-3 text-gray-700 dark:text-slate-300">{{ formatDate(item.created_at) }}</td>
                        <td class="px-4 py-3 text-gray-700 dark:text-slate-300">{{ formatBytes(item.size_bytes) }}</td>
                        <td class="px-4 py-3 text-right">
                            <button
                                class="px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors"
                                :class="item.kind === 'db' && !restoring
                                    ? 'bg-red-600 hover:bg-red-500 text-white'
                                    : 'bg-gray-200 dark:bg-slate-700 text-gray-500 dark:text-slate-400 cursor-not-allowed'"
                                :disabled="item.kind !== 'db' || restoring"
                                @click="openRestoreModal(item)"
                            >
                                Restore DB
                            </button>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <Transition name="toast">
            <div
                v-if="restoreModalOpen && selectedBackup"
                class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
                @click.self="closeRestoreModal"
            >
                <div class="w-full max-w-lg rounded-xl border border-red-500/40 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden">
                    <div class="px-6 py-4 border-b border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-950/40">
                        <h3 class="text-lg font-bold text-red-700 dark:text-red-300">Критическое действие</h3>
                        <p class="mt-1 text-sm text-red-700/80 dark:text-red-300/80">
                            Восстановление удалит текущее состояние БД и заменит его выбранным backup.
                        </p>
                    </div>
                    <div class="px-6 py-4 space-y-4">
                        <div class="text-sm text-gray-700 dark:text-slate-300">
                            <p class="font-semibold mb-1">Файл для восстановления:</p>
                            <p class="break-all">{{ selectedBackup.name }}</p>
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">
                                Введите <span class="font-bold">RESTORE</span> для подтверждения
                            </label>
                            <input
                                v-model="restoreWord"
                                type="text"
                                class="w-full bg-gray-50 dark:bg-slate-800 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-100 focus:outline-none focus:border-red-500 transition-colors"
                                :disabled="restoreLaunching"
                            />
                        </div>
                    </div>
                    <div class="px-6 py-4 border-t border-gray-200 dark:border-slate-700 flex items-center justify-end gap-2">
                        <button
                            class="px-3 py-2 rounded-lg text-sm font-medium bg-white dark:bg-slate-800 border border-gray-300 dark:border-slate-600 text-gray-700 dark:text-slate-300"
                            :disabled="restoreLaunching"
                            @click="closeRestoreModal"
                        >
                            Отмена
                        </button>
                        <button
                            class="px-3 py-2 rounded-lg text-sm font-semibold text-white bg-red-600 hover:bg-red-500 disabled:opacity-50"
                            :disabled="restoreLaunching"
                            @click="startRestore"
                        >
                            {{ restoreLaunching ? 'Запуск...' : 'Подтвердить Restore' }}
                        </button>
                    </div>
                </div>
            </div>
        </Transition>
    </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
    transition: all 0.25s ease;
}
.toast-enter-from,
.toast-leave-to {
    opacity: 0;
    transform: translateY(-8px);
}
</style>
