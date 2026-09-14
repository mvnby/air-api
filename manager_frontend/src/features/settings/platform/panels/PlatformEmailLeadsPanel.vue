<script setup lang="ts">
import { usePlatformSettingsContext } from '../platform-settings-context';
const { activeSettingsTab, emailLeadSettings, emailLeadSettingsSaving, saveEmailLeadSettings, formatDate } = usePlatformSettingsContext();
</script>

<template>
<div v-if="activeSettingsTab === 'emailLeads'" class="mb-6 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-6">
            <div class="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h3 class="text-base font-semibold text-gray-900 dark:text-slate-200 mb-1 flex items-center gap-2">
                        <span class="material-icons-round text-brand-500 text-[20px]">mark_email_read</span>
                        Email-лиды
                    </h3>
                    <p class="text-xs text-gray-500 dark:text-slate-400">
                        Автоматическая проверка входящей почты, вложений и создание лидов через AI.
                    </p>
                </div>
                <button
                    type="button"
                    class="flex items-center justify-center gap-2 bg-brand-600 hover:bg-brand-500 active:bg-brand-700 text-white font-medium py-2 px-4 rounded-lg shadow-sm transition-all text-sm disabled:opacity-60"
                    :disabled="emailLeadSettingsSaving"
                    @click="saveEmailLeadSettings"
                >
                    <span v-if="emailLeadSettingsSaving" class="material-icons-round text-[18px] animate-spin">refresh</span>
                    <span v-else class="material-icons-round text-[18px]">save</span>
                    Сохранить
                </button>
            </div>

            <div class="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
                <label class="flex min-h-[88px] items-center gap-3 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
                    <input
                        v-model="emailLeadSettings.autoImport"
                        type="checkbox"
                        class="h-5 w-5 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
                        :disabled="emailLeadSettingsSaving"
                    />
                    <span>
                        <span class="block text-sm font-semibold text-gray-900 dark:text-slate-100">Автоимпорт</span>
                        <span class="block text-xs text-gray-500 dark:text-slate-400">Создавать входящие лиды без ручного запуска.</span>
                    </span>
                </label>

                <div class="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
                    <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Интервал проверки, минут</label>
                    <input
                        v-model.number="emailLeadSettings.intervalMinutes"
                        type="number"
                        min="1"
                        max="1440"
                        class="w-full bg-white dark:bg-slate-800 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition-colors shadow-sm text-sm"
                        :disabled="emailLeadSettingsSaving"
                    />
                </div>

                <div class="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
                    <div class="text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Окно проверки</div>
                    <div class="text-sm font-semibold text-gray-900 dark:text-slate-100">
                        {{ emailLeadSettings.lastImportAt ? `После ${formatDate(emailLeadSettings.lastImportAt)}` : 'Первый запуск: последние 5 дней' }}
                    </div>
                    <p class="mt-1 text-xs text-gray-500 dark:text-slate-400">
                        После успешной проверки дата прохода обновляется автоматически.
                    </p>
                </div>
            </div>
        </div>
</template>
