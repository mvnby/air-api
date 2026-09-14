<script setup lang="ts">
import { usePlatformSettingsContext } from '../platform-settings-context';
const { activeSettingsTab, botSelectionRulesSaving, resetBotSelectionRulesDraft, botSelectionRulesError, saveBotSelectionRules, botSelectionRulesText, botSelectionRulesUpdatedAt, formatDate, botSelectionPowerPreview, botSelectionTierPreview } = usePlatformSettingsContext();
</script>

<template>
<div v-if="activeSettingsTab === 'botSelection'" class="mb-6 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-6">
            <div class="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h3 class="text-base font-semibold text-gray-900 dark:text-slate-200 mb-1 flex items-center gap-2">
                        <span class="material-icons-round text-brand-500 text-[20px]">smart_toy</span>
                        Подбор в Telegram-боте
                    </h3>
                    <p class="text-xs text-gray-500 dark:text-slate-400">
                        Мощности, диапазоны, категории и уровни рекомендаций для staff-бота.
                    </p>
                </div>
                <div class="flex flex-wrap gap-2">
                    <button
                        type="button"
                        class="flex items-center justify-center gap-2 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 active:bg-gray-100 dark:active:bg-slate-600 text-gray-700 dark:text-slate-300 font-medium py-2 px-4 rounded-lg shadow-sm transition-all text-sm disabled:opacity-60"
                        :disabled="botSelectionRulesSaving"
                        @click="resetBotSelectionRulesDraft"
                    >
                        <span class="material-icons-round text-[18px]">restart_alt</span>
                        Сбросить
                    </button>
                    <button
                        type="button"
                        class="flex items-center justify-center gap-2 bg-brand-600 hover:bg-brand-500 active:bg-brand-700 text-white font-medium py-2 px-4 rounded-lg shadow-sm transition-all text-sm disabled:opacity-60"
                        :disabled="botSelectionRulesSaving || !!botSelectionRulesError"
                        @click="saveBotSelectionRules"
                    >
                        <span v-if="botSelectionRulesSaving" class="material-icons-round text-[18px] animate-spin">refresh</span>
                        <span v-else class="material-icons-round text-[18px]">save</span>
                        Сохранить
                    </button>
                </div>
            </div>

            <div class="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
                <div>
                    <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400">bot_product_selection_rules</label>
                        <span
                            class="rounded-full px-2.5 py-1 text-xs font-medium"
                            :class="botSelectionRulesError ? 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300' : 'bg-green-50 text-green-700 dark:bg-green-500/10 dark:text-green-300'"
                        >
                            {{ botSelectionRulesError || 'JSON корректен' }}
                        </span>
                    </div>
                    <textarea
                        v-model="botSelectionRulesText"
                        class="min-h-[520px] w-full resize-y rounded-lg border border-gray-300 bg-gray-50 px-3 py-3 font-mono text-sm leading-5 text-gray-900 shadow-sm transition-colors focus:border-brand-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                        spellcheck="false"
                        :disabled="botSelectionRulesSaving"
                    ></textarea>
                    <p v-if="botSelectionRulesUpdatedAt" class="mt-2 text-xs text-gray-500 dark:text-slate-400">
                        Изменено: {{ formatDate(botSelectionRulesUpdatedAt) }}
                    </p>
                </div>

                <div class="space-y-4">
                    <div class="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-slate-700 dark:bg-slate-900">
                        <div class="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-slate-100">
                            <span class="material-icons-round text-[18px] text-brand-500">speed</span>
                            Мощности
                        </div>
                        <div class="space-y-2">
                            <div
                                v-for="item in botSelectionPowerPreview"
                                :key="item.code"
                                class="grid grid-cols-[48px_1fr_82px] items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm dark:bg-slate-800"
                            >
                                <span class="font-semibold text-gray-900 dark:text-slate-100">{{ item.code }}</span>
                                <span class="text-gray-600 dark:text-slate-300">{{ item.kw }} кВт</span>
                                <span class="text-right text-xs text-gray-500 dark:text-slate-400">{{ item.area }} м²</span>
                            </div>
                        </div>
                    </div>

                    <div class="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-slate-700 dark:bg-slate-900">
                        <div class="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-slate-100">
                            <span class="material-icons-round text-[18px] text-brand-500">tune</span>
                            Режимы
                        </div>
                        <div class="space-y-2">
                            <div
                                v-for="item in botSelectionTierPreview"
                                :key="item.mode"
                                class="rounded-lg bg-white px-3 py-2 dark:bg-slate-800"
                            >
                                <div class="font-mono text-xs font-semibold text-gray-700 dark:text-slate-300">{{ item.mode }}</div>
                                <div class="mt-1 text-sm text-gray-600 dark:text-slate-400">{{ item.labels || '—' }}</div>
                            </div>
                        </div>
                    </div>

                    <div class="rounded-xl border border-brand-200 bg-brand-50 p-4 text-sm text-brand-900 dark:border-brand-500/30 dark:bg-brand-500/10 dark:text-brand-200">
                        <div class="font-semibold">Активно после сохранения</div>
                        <div class="mt-1 text-xs opacity-80">
                            Бот перечитает правила при следующем запросе подбора.
                        </div>
                    </div>
                </div>
            </div>
        </div>
</template>
