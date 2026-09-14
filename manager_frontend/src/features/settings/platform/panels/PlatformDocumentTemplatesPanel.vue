<script setup lang="ts">
import { DOCUMENT_ROLE_OPTIONS, DOCUMENT_TYPE_OPTIONS } from '../platform-settings-types';
import { usePlatformSettingsContext } from '../platform-settings-context';
const { activeSettingsTab, documentTemplates, templateFolderId, loadingTemplateFiles, loadTemplateFiles, filteredTemplateFiles, addDocumentTemplate, selectTemplateFile, savingTemplateKeys, deletingTemplateId, saveDocumentTemplate, deleteDocumentTemplate, customers, customerSearch, loadingCustomerSearch, loadCustomers, selectedCustomersForTemplate, customerLabel, addCustomerToTemplate, removeCustomerFromTemplate, contractDocumentTemplates, actDocumentTemplates } = usePlatformSettingsContext();
</script>

<template>
<div v-if="activeSettingsTab === 'documentTemplates'" class="mb-6 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-6">
            <div class="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h3 class="text-base font-semibold text-gray-900 dark:text-slate-200 mb-1 flex items-center gap-2">
                        <span class="material-icons-round text-brand-500 text-[20px]">description</span>
                        Шаблоны документов
                    </h3>
                    <p class="text-xs text-gray-500 dark:text-slate-400">
                        Общие формы для всех клиентов и редкие персональные формы по УНП/названию.
                    </p>
                </div>
                <div class="flex flex-wrap gap-2">
                    <button
                        v-for="option in DOCUMENT_TYPE_OPTIONS"
                        :key="option.value"
                        type="button"
                        class="flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-medium text-white shadow-sm"
                        :class="option.value === 'act' ? 'bg-slate-700 hover:bg-slate-600' : 'bg-brand-600 hover:bg-brand-500'"
                        @click="addDocumentTemplate(option.value)"
                    >
                        <span class="material-icons-round text-[16px]">add</span>
                        {{ option.addLabel }}
                    </button>
                </div>
            </div>

            <div class="mt-5 rounded-xl border border-brand-100 bg-brand-50/60 p-4 dark:border-brand-500/30 dark:bg-brand-500/10">
                <label class="mb-2 block text-xs font-medium text-brand-800 dark:text-brand-200">Папка Google Drive с шаблонами</label>
                <div class="flex flex-col gap-2 sm:flex-row">
                    <input
                        v-model="templateFolderId"
                        type="text"
                        class="min-w-0 flex-1 rounded-lg border border-brand-200 bg-white px-3 py-2 font-mono text-sm text-gray-900 shadow-sm dark:border-brand-500/40 dark:bg-slate-900 dark:text-slate-200"
                        placeholder="Google Drive folder ID"
                    />
                    <button
                        type="button"
                        class="flex items-center justify-center gap-2 rounded-lg bg-white px-3 py-2 text-sm font-medium text-brand-700 shadow-sm ring-1 ring-brand-200 hover:bg-brand-50 disabled:opacity-60 dark:bg-slate-900 dark:text-brand-200 dark:ring-brand-500/40 dark:hover:bg-slate-800"
                        :disabled="loadingTemplateFiles"
                        @click="loadTemplateFiles"
                    >
                        <span class="material-icons-round text-[18px]" :class="{ 'animate-spin': loadingTemplateFiles }">refresh</span>
                        Обновить список
                    </button>
                </div>
            </div>

            <div class="mt-5 space-y-3">
                <div
                    v-for="template in documentTemplates"
                    :key="template.document_template_id || `${template.doc_type}-${template.sort_order}-${template.google_template_id}`"
                    class="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-slate-700 dark:bg-slate-900/50"
                >
                    <div class="grid grid-cols-1 gap-3 lg:grid-cols-[170px_1fr_1.2fr_180px_120px]">
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Тип</label>
                            <select
                                v-model="template.doc_type"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            >
                                <option v-for="option in DOCUMENT_TYPE_OPTIONS" :key="option.value" :value="option.value">
                                    {{ option.label }}
                                </option>
                            </select>
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Название</label>
                            <input
                                v-model="template.name"
                                type="text"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                placeholder="Название для менеджера"
                            />
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Файл шаблона</label>
                            <select
                                :value="template.google_template_id"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                @change="selectTemplateFile(template, ($event.target as HTMLSelectElement).value)"
                            >
                                <option value="">Выберите файл из папки templates</option>
                                <option v-for="file in filteredTemplateFiles" :key="file.id" :value="file.id">
                                    {{ file.name }}
                                </option>
                            </select>
                            <input
                                v-model="template.google_template_id"
                                type="text"
                                class="mt-2 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 font-mono text-xs text-gray-600 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400"
                                placeholder="или Google Template ID вручную"
                            />
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Роли</label>
                            <select
                                v-model="template.document_role_type"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            >
                                <option v-for="option in DOCUMENT_ROLE_OPTIONS" :key="option.value" :value="option.value">
                                    {{ option.label }}
                                </option>
                            </select>
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Позиция</label>
                            <input
                                v-model.number="template.sort_order"
                                type="number"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                placeholder="0"
                            />
                        </div>
                    </div>

                    <div class="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-3">
                        <div class="space-y-2">
                            <textarea
                                v-model="template.description"
                                rows="3"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                placeholder="Комментарий для менеджера"
                            />
                            <input
                                v-if="template.doc_type === 'contract' || template.doc_type === 'invoice'"
                                v-model="template.base_document_type_label"
                                type="text"
                                class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                                placeholder="Тип основания: Счет-договор"
                            />
                        </div>
                        <div>
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Доступность</label>
                            <div class="rounded-lg border border-gray-300 bg-white p-3 shadow-sm dark:border-slate-600 dark:bg-slate-900">
                                <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-slate-300">
                                    <input
                                        type="checkbox"
                                        class="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
                                        :checked="!template.client_restricted"
                                        @change="template.client_restricted = !($event.target as HTMLInputElement).checked; if (!template.client_restricted) template.customer_ids = []"
                                    />
                                    Для всех клиентов
                                </label>
                                <div v-if="template.client_restricted" class="mt-3 space-y-2">
                                    <div class="flex gap-2">
                                        <input
                                            v-model="customerSearch"
                                            type="search"
                                            class="min-w-0 flex-1 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                                            placeholder="Найти по УНП или названию"
                                            @keydown.enter.prevent="loadCustomers(customerSearch)"
                                        />
                                        <button
                                            type="button"
                                            class="rounded-lg bg-slate-700 px-3 py-2 text-xs font-medium text-white hover:bg-slate-600 disabled:opacity-60"
                                            :disabled="loadingCustomerSearch"
                                            @click="loadCustomers(customerSearch)"
                                        >
                                            Найти
                                        </button>
                                    </div>
                                    <select
                                        class="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                                        @change="addCustomerToTemplate(template, ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"
                                    >
                                        <option value="">Добавить найденного клиента</option>
                                        <option
                                            v-for="customer in customers"
                                            :key="customer.id"
                                            :value="customer.id"
                                            :disabled="template.customer_ids.includes(customer.id)"
                                        >
                                            {{ customerLabel(customer) }}
                                        </option>
                                    </select>
                                    <div class="flex flex-wrap gap-2">
                                        <button
                                            v-for="customer in selectedCustomersForTemplate(template)"
                                            :key="customer.id"
                                            type="button"
                                            class="inline-flex items-center gap-1 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-800 ring-1 ring-brand-200 dark:bg-brand-500/10 dark:text-brand-200 dark:ring-brand-500/30"
                                            @click="removeCustomerFromTemplate(template, customer.id)"
                                        >
                                            {{ customerLabel(customer) }}
                                            <span class="material-icons-round text-[14px]">close</span>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div v-if="template.doc_type === 'contract' || template.doc_type === 'invoice'">
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Связанные акты</label>
                            <select
                                v-model="template.linked_act_template_ids"
                                multiple
                                class="h-24 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            >
                                <option v-for="act in actDocumentTemplates" :key="act.document_template_id || 0" :value="act.document_template_id || 0">
                                    {{ act.name }}
                                </option>
                            </select>
                        </div>
                        <div v-else-if="template.doc_type === 'act'">
                            <label class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Для договоров / счетов</label>
                            <select
                                v-model="template.linked_contract_template_ids"
                                multiple
                                class="h-24 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                            >
                                <option v-for="contract in contractDocumentTemplates" :key="contract.document_template_id || 0" :value="contract.document_template_id || 0">
                                    {{ contract.name }}
                                </option>
                            </select>
                        </div>
                        <div v-else class="rounded-lg border border-gray-200 bg-white p-3 text-sm text-gray-500 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
                            <template v-if="template.doc_type === 'retail_receipt' || template.doc_type === 'service_act' || template.doc_type === 'maintenance_service_act'">
                                Шаблон используется для заказов физических лиц без привязки к договору или счету.
                            </template>
                            <template v-else>
                            Дефектный акт выбирается как отдельный шаблон без привязки к договору или счету.
                            </template>
                        </div>
                    </div>

                    <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
                        <div class="flex flex-wrap gap-3 text-sm text-gray-700 dark:text-slate-300">
                            <label class="flex items-center gap-2">
                                <input v-model="template.is_active" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
                                Активен
                            </label>
                            <label class="flex items-center gap-2">
                                <input v-model="template.is_default" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
                                По умолчанию
                            </label>
                            <label v-if="template.doc_type === 'contract'" class="flex items-center gap-2">
                                <input v-model="template.is_open_contract" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
                                Открытый договор
                            </label>
                        </div>
                        <div class="flex gap-2">
                            <button
                                type="button"
                                class="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-medium text-red-600 shadow-sm hover:bg-red-50 dark:border-red-500/40 dark:bg-slate-900 dark:text-red-300 dark:hover:bg-red-500/10"
                                :disabled="deletingTemplateId === template.document_template_id"
                                @click="deleteDocumentTemplate(template)"
                            >
                                Удалить
                            </button>
                            <button
                                type="button"
                                class="rounded-lg bg-brand-600 px-4 py-2 text-xs font-medium text-white shadow-sm hover:bg-brand-500 disabled:opacity-60"
                                :disabled="savingTemplateKeys.has(String(template.document_template_id || `new:${template.doc_type}:${template.sort_order}`))"
                                @click="saveDocumentTemplate(template)"
                            >
                                Сохранить
                            </button>
                        </div>
                    </div>
                </div>
                <p v-if="!documentTemplates.length" class="rounded-lg border border-dashed border-gray-300 p-4 text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400">
                    Управляемые шаблоны пока не добавлены. Старые шаблоны из JSON продолжают работать как fallback до миграции.
                </p>
            </div>
        </div>
</template>
