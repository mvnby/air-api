<script setup lang="ts">
import PlatformBotSelectionPanel from '../features/settings/platform/panels/PlatformBotSelectionPanel.vue';
import PlatformDocumentTemplatesPanel from '../features/settings/platform/panels/PlatformDocumentTemplatesPanel.vue';
import PlatformEmailLeadsPanel from '../features/settings/platform/panels/PlatformEmailLeadsPanel.vue';
import PlatformGeneralPanel from '../features/settings/platform/panels/PlatformGeneralPanel.vue';
import PlatformRepairComplaintsPanel from '../features/settings/platform/panels/PlatformRepairComplaintsPanel.vue';
import { providePlatformSettingsContext } from '../features/settings/platform/platform-settings-context';
import { usePlatformSettings } from '../features/settings/platform/usePlatformSettings';
const controller = usePlatformSettings();
providePlatformSettingsContext(controller);
const { activeSettingsTab, goToBackups, loadSettings, loading, showCreateForm, toast, toastType, error } = controller;
</script>

<template>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        <!-- Toast Notification -->
        <Transition name="toast">
            <div v-if="toast" class="fixed top-20 right-8 z-50 px-4 py-3 rounded-lg shadow-xl flex items-center gap-3"
                 :class="toastType === 'success' ? 'bg-emerald-600 border border-emerald-500 text-white shadow-emerald-900/30' : 'bg-red-600 border border-red-500 text-white shadow-red-900/30'">
                <span class="material-icons-round text-xl">{{ toastType === 'success' ? 'check_circle' : 'error' }}</span>
                <span class="text-sm font-medium">{{ toast }}</span>
            </div>
        </Transition>

        <div class="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div class="pl-16 sm:pl-0">
                <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
                    <span class="material-icons-round text-brand-600 dark:text-brand-400">settings</span>
                    Настройки
                </h1>
                <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
                    Управление глобальными параметрами и конфигурацией сайта
                </p>
            </div>

            <div class="grid w-full grid-cols-3 gap-2 sm:flex sm:w-auto sm:items-center">
                <button
                    @click="goToBackups"
                    class="flex min-w-0 items-center justify-center gap-2 bg-red-600 hover:bg-red-500 active:bg-red-700 text-white font-medium py-2.5 px-3 sm:px-4 rounded-lg shadow-sm transition-all text-sm"
                >
                    <span class="material-icons-round text-[18px]">warning</span>
                    <span class="min-w-0 leading-tight">DR / Бэкапы</span>
                </button>
                <button
                    @click="showCreateForm = !showCreateForm"
                    class="flex min-w-0 items-center justify-center gap-2 bg-brand-600 hover:bg-brand-500 active:bg-brand-700 text-white font-medium py-2.5 px-3 sm:px-4 rounded-lg shadow-sm transition-all text-sm"
                >
                    <span class="material-icons-round text-[18px]">{{ showCreateForm ? 'close' : 'add_circle' }}</span>
                    <span class="min-w-0 leading-tight">{{ showCreateForm ? 'Отмена' : 'Добавить' }}</span>
                </button>
                <button
                    @click="loadSettings"
                    class="flex min-w-0 items-center justify-center gap-2 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 active:bg-gray-100 dark:active:bg-slate-600 text-gray-700 dark:text-slate-300 font-medium py-2.5 px-3 sm:px-4 rounded-lg shadow-sm transition-all text-sm"
                    :disabled="loading"
                >
                    <span class="material-icons-round text-[18px]" :class="{'animate-spin': loading}">refresh</span>
                    <span class="min-w-0 leading-tight">Обновить</span>
                </button>
            </div>
        </div>

        <div class="mb-6 flex flex-wrap gap-2 rounded-xl border border-gray-200 bg-white p-2 shadow-sm dark:border-slate-700/60 dark:bg-[#1e293b]">
            <button
                type="button"
                class="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
                :class="activeSettingsTab === 'general' ? 'bg-brand-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800'"
                @click="activeSettingsTab = 'general'"
            >
                <span class="material-icons-round text-[18px]">tune</span>
                Основные
            </button>
            <button
                type="button"
                class="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
                :class="activeSettingsTab === 'documentTemplates' ? 'bg-brand-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800'"
                @click="activeSettingsTab = 'documentTemplates'"
            >
                <span class="material-icons-round text-[18px]">description</span>
                Шаблоны документов
            </button>
            <button
                type="button"
                class="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
                :class="activeSettingsTab === 'repairComplaints' ? 'bg-brand-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800'"
                @click="activeSettingsTab = 'repairComplaints'"
            >
                <span class="material-icons-round text-[18px]">build_circle</span>
                Жалобы ремонта
            </button>
            <button
                type="button"
                class="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
                :class="activeSettingsTab === 'emailLeads' ? 'bg-brand-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800'"
                @click="activeSettingsTab = 'emailLeads'"
            >
                <span class="material-icons-round text-[18px]">mark_email_read</span>
                Email-лиды
            </button>
            <button
                type="button"
                class="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
                :class="activeSettingsTab === 'botSelection' ? 'bg-brand-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800'"
                @click="activeSettingsTab = 'botSelection'"
            >
                <span class="material-icons-round text-[18px]">smart_toy</span>
                Telegram-бот
            </button>
        </div>


        <div v-if="error" class="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/50 text-red-600 dark:text-red-400 p-4 rounded-xl mb-6">{{ error }}</div>
        <PlatformGeneralPanel />
        <PlatformDocumentTemplatesPanel />
        <PlatformRepairComplaintsPanel />
        <PlatformEmailLeadsPanel />
        <PlatformBotSelectionPanel />
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
