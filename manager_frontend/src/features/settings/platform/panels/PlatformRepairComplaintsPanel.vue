<script setup lang="ts">
import { REPAIR_COMPLAINT_GROUP_OPTIONS } from '../platform-settings-types';
import { usePlatformSettingsContext } from '../platform-settings-context';
const { activeSettingsTab, repairComplaintSearch, repairComplaintGroupFilter, loadRepairComplaintPresets, loadingRepairComplaints, addRepairComplaintPreset, repairComplaintPresets, savingRepairComplaintKeys, deletingRepairComplaintId, saveRepairComplaintPreset, deleteRepairComplaintPreset } = usePlatformSettingsContext();
</script>

<template>
<div v-if="activeSettingsTab === 'repairComplaints'" class="mb-6 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-6">
            <div class="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h3 class="text-base font-semibold text-gray-900 dark:text-slate-200 mb-1 flex items-center gap-2">
                        <span class="material-icons-round text-brand-500 text-[20px]">build_circle</span>
                        Жалобы и диагнозы для ремонта
                    </h3>
                    <p class="text-xs text-gray-500 dark:text-slate-400">
                        Менеджер выбирает жалобу в заказе, а карточка подставляет формулировку для акта и вероятный диагноз.
                    </p>
                </div>
                <button
                    type="button"
                    class="flex items-center gap-1 rounded-lg bg-brand-600 px-3 py-2 text-xs font-medium text-white shadow-sm hover:bg-brand-500"
                    @click="addRepairComplaintPreset"
                >
                    <span class="material-icons-round text-[16px]">add</span>
                    Добавить жалобу
                </button>
            </div>

            <div class="mt-5 grid gap-3 md:grid-cols-[1fr_240px_auto]">
                <input
                    v-model="repairComplaintSearch"
                    type="search"
                    class="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                    placeholder="Поиск по жалобе, формулировке или диагнозу"
                    @keydown.enter.prevent="loadRepairComplaintPresets"
                />
                <select
                    v-model="repairComplaintGroupFilter"
                    class="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                    @change="loadRepairComplaintPresets"
                >
                    <option value="">Все группы</option>
                    <option v-for="group in REPAIR_COMPLAINT_GROUP_OPTIONS" :key="group.value" :value="group.value">
                        {{ group.label }}
                    </option>
                </select>
                <button
                    type="button"
                    class="flex items-center justify-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-60 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                    :disabled="loadingRepairComplaints"
                    @click="loadRepairComplaintPresets"
                >
                    <span class="material-icons-round text-[18px]" :class="{ 'animate-spin': loadingRepairComplaints }">refresh</span>
                    Обновить
                </button>
            </div>

            <div class="mt-5 space-y-3">
                <div
                    v-for="preset in repairComplaintPresets"
                    :key="preset.id || `new:${preset.complaint_group}:${preset.sort_order}`"
                    class="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-slate-700 dark:bg-slate-900/50"
                >
                    <div class="grid grid-cols-1 gap-3 lg:grid-cols-[180px_1fr_110px]">
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Группа</label>
                            <select
                                v-model="preset.complaint_group"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            >
                                <option v-for="group in REPAIR_COMPLAINT_GROUP_OPTIONS" :key="group.value" :value="group.value">
                                    {{ group.label }}
                                </option>
                            </select>
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Как говорит клиент *</label>
                            <input
                                v-model="preset.customer_phrase"
                                type="text"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                placeholder="Не холодит, капает вода, шумит..."
                            />
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Порядок</label>
                            <input
                                v-model.number="preset.sort_order"
                                type="number"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            />
                        </div>
                    </div>

                    <div class="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
                        <label class="block">
                            <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Формулировка в акт</span>
                            <textarea
                                v-model="preset.document_wording"
                                rows="3"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                placeholder="Официальная формулировка для дефектного акта"
                            />
                        </label>
                        <label class="block">
                            <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Вероятный диагноз</span>
                            <textarea
                                v-model="preset.likely_diagnosis"
                                rows="3"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                placeholder="Внутренняя подсказка для менеджера/мастера"
                            />
                        </label>
                    </div>

                    <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
                        <div class="flex flex-wrap gap-3 text-sm text-gray-700 dark:text-slate-300">
                            <label class="flex items-center gap-2">
                                <input v-model="preset.is_active" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
                                Активна
                            </label>
                            <label class="flex items-center gap-2">
                                <input v-model="preset.is_favorite" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
                                Избранная
                            </label>
                        </div>
                        <div class="flex gap-2">
                            <button
                                type="button"
                                class="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-medium text-red-600 shadow-sm hover:bg-red-50 disabled:opacity-60 dark:border-red-500/40 dark:bg-slate-900 dark:text-red-300 dark:hover:bg-red-500/10"
                                :disabled="deletingRepairComplaintId === preset.id"
                                @click="deleteRepairComplaintPreset(preset)"
                            >
                                Удалить
                            </button>
                            <button
                                type="button"
                                class="rounded-lg bg-brand-600 px-4 py-2 text-xs font-medium text-white shadow-sm hover:bg-brand-500 disabled:opacity-60"
                                :disabled="savingRepairComplaintKeys.has(String(preset.id || `new:${preset.complaint_group}:${preset.sort_order}`))"
                                @click="saveRepairComplaintPreset(preset)"
                            >
                                Сохранить
                            </button>
                        </div>
                    </div>
                </div>
                <p v-if="!repairComplaintPresets.length" class="rounded-lg border border-dashed border-gray-300 p-4 text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400">
                    Жалобы не найдены. Добавьте первую или сбросьте фильтр.
                </p>
            </div>
        </div>
</template>
