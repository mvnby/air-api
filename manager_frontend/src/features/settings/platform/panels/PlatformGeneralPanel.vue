<script setup lang="ts">
import AddressSuggestInput from '../../../../components/ui/AddressSuggestInput.vue';
import { usePlatformSettingsContext } from '../platform-settings-context';
const { activeSettingsTab, googleAuthStatus, googleAuthLoading, googleAuthBusy, loadGoogleAuthStatus, openGoogleAuth, showCreateForm, newKey, newValue, newDescription, creating, createSetting, loading, settings, companyRequisites, companyRequisitesSaving, saveCompanyRequisites, formatDate, savingKeys, DOCUMENT_ROLE_OPTIONS, ensureContractTemplateDraft, addContractTemplateRow, removeContractTemplateRow, saveContractTemplates, saveSetting } = usePlatformSettingsContext();
</script>

<template>
<div v-if="activeSettingsTab === 'general'" class="mb-6 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-6">
            <div class="flex items-start justify-between gap-4 flex-wrap">
                <div>
                    <h3 class="text-base font-semibold text-gray-900 dark:text-slate-200 mb-1 flex items-center gap-2">
                        <span class="material-icons-round text-brand-500 text-[20px]">account_tree</span>
                        Google Integration
                    </h3>
                    <p class="text-xs text-gray-500 dark:text-slate-400">
                        Авторизация Google API для документов и Google Sheets.
                    </p>
                </div>
                <button
                    @click="loadGoogleAuthStatus"
                    class="flex items-center gap-2 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 active:bg-gray-100 dark:active:bg-slate-600 text-gray-700 dark:text-slate-300 font-medium py-2 px-3 rounded-lg shadow-sm transition-all text-xs"
                    :disabled="googleAuthLoading || googleAuthBusy"
                >
                    <span class="material-icons-round text-[16px]" :class="{ 'animate-spin': googleAuthLoading }">refresh</span>
                    Проверить
                </button>
            </div>

            <div class="mt-4 p-3 rounded-lg border"
                :class="googleAuthStatus?.valid && googleAuthStatus?.persistence_ok
                    ? 'bg-green-50 border-green-200 text-green-800 dark:bg-green-500/10 dark:border-green-500/40 dark:text-green-300'
                    : 'bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-500/10 dark:border-amber-500/40 dark:text-amber-300'">
                <div class="text-sm font-medium">
                    <span v-if="googleAuthLoading">Проверяем статус...</span>
                    <span v-else-if="googleAuthStatus?.valid && googleAuthStatus?.persistence_ok">Подключено</span>
                    <span v-else-if="googleAuthStatus?.valid">Работает временно — токен не сохранён</span>
                    <span v-else>Не подключено / токен истёк</span>
                </div>
                <div v-if="googleAuthStatus?.valid && !googleAuthStatus?.persistence_ok" class="text-xs mt-1 opacity-80">
                    Переподключите Google: после перезапуска доступ может пропасть.
                </div>
                <div v-if="googleAuthStatus?.expiry" class="text-xs mt-1 opacity-80">
                    Действует до: {{ googleAuthStatus.expiry }}
                </div>
            </div>

            <div class="mt-4 flex flex-wrap items-center gap-2">
                <button
                    @click="openGoogleAuth"
                    class="flex items-center justify-center gap-2 bg-brand-600 hover:bg-brand-500 active:bg-brand-700 text-white font-medium py-2 px-4 rounded-lg shadow-sm transition-all text-sm disabled:opacity-60"
                    :disabled="googleAuthBusy"
                >
                    <span class="material-icons-round text-[18px]">open_in_new</span>
                    Подключить Google
                </button>
            </div>
        </div>

<Transition name="toast">
            <div v-if="activeSettingsTab === 'general' && showCreateForm" class="mb-6 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border-2 border-brand-500/50 p-6">
                <h3 class="text-base font-semibold text-gray-900 dark:text-slate-200 mb-4 flex items-center gap-2">
                    <span class="material-icons-round text-brand-500 text-[20px]">add_circle</span>
                    Новый параметр
                </h3>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Ключ *</label>
                        <input
                            v-model="newKey"
                            type="text"
                            class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition-colors shadow-sm font-mono text-sm"
                            placeholder="contract_templates"
                            :disabled="creating"
                        />
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Значение *</label>
                        <input
                            v-model="newValue"
                            type="text"
                            class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition-colors shadow-sm text-sm"
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
                                class="flex-1 bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition-colors shadow-sm text-sm"
                                placeholder="Описание параметра"
                                :disabled="creating"
                            />
                            <button
                                @click="createSetting"
                                class="flex items-center gap-1 px-4 py-2 text-sm font-medium text-white bg-brand-600 hover:bg-brand-500 active:bg-brand-700 transition-colors rounded-lg disabled:opacity-50 shadow-sm whitespace-nowrap"
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

<div v-if="activeSettingsTab === 'general' && loading && !settings.length" class="flex justify-center py-20">
            <div class="w-8 h-8 rounded-full border-4 border-gray-200 dark:border-slate-700 border-t-brand-500 animate-spin"></div>
        </div>

<div v-else-if="activeSettingsTab === 'general'" class="space-y-4">
            <section class="bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-6">
                <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                        <h2 class="text-lg font-bold text-gray-900 dark:text-white">Наши реквизиты</h2>
                        <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
                            Используются в актах сверки и следующих документах компании.
                        </p>
                    </div>
                    <button
                        type="button"
                        class="flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-500 active:bg-brand-700 disabled:opacity-50"
                        :disabled="companyRequisitesSaving"
                        @click="saveCompanyRequisites"
                    >
                        <span v-if="companyRequisitesSaving" class="material-icons-round text-sm animate-spin">refresh</span>
                        <span v-else class="material-icons-round text-sm">save</span>
                        Сохранить реквизиты
                    </button>
                </div>
                <div class="mt-5 grid gap-4 md:grid-cols-2">
                    <label class="block text-sm">
                        <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Краткое название</span>
                        <input v-model="companyRequisites.company_name" class="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-gray-900 shadow-sm transition-colors focus:border-brand-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200" />
                    </label>
                    <label class="block text-sm">
                        <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Полное наименование</span>
                        <input v-model="companyRequisites.company_full_legal_name" class="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-gray-900 shadow-sm transition-colors focus:border-brand-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200" />
                    </label>
                    <label class="block text-sm">
                        <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">УНП</span>
                        <input v-model="companyRequisites.company_unp" class="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-gray-900 shadow-sm transition-colors focus:border-brand-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200" />
                    </label>
                    <label class="block text-sm">
                        <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Юридический адрес</span>
                        <AddressSuggestInput v-model="companyRequisites.company_legal_address" input-class="bg-gray-50 dark:bg-slate-900" />
                    </label>
                    <label class="block text-sm">
                        <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">IBAN</span>
                        <input v-model="companyRequisites.company_iban" class="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-gray-900 shadow-sm transition-colors focus:border-brand-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200" />
                    </label>
                    <label class="block text-sm">
                        <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Банк</span>
                        <input v-model="companyRequisites.company_bank_name" class="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-gray-900 shadow-sm transition-colors focus:border-brand-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200" />
                    </label>
                    <label class="block text-sm">
                        <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">BIC</span>
                        <input v-model="companyRequisites.company_bic" class="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-gray-900 shadow-sm transition-colors focus:border-brand-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200" />
                    </label>
                    <label class="block text-sm">
                        <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Должность подписанта</span>
                        <input v-model="companyRequisites.company_signer_position" class="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-gray-900 shadow-sm transition-colors focus:border-brand-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200" />
                    </label>
                    <label class="block text-sm">
                        <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">ФИО подписанта</span>
                        <input v-model="companyRequisites.company_signer_name" class="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-gray-900 shadow-sm transition-colors focus:border-brand-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200" />
                    </label>
                    <label class="block text-sm">
                        <span class="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">Основание полномочий</span>
                        <input v-model="companyRequisites.company_acting_basis" class="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-gray-900 shadow-sm transition-colors focus:border-brand-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200" />
                    </label>
                </div>
            </section>

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

                <div v-if="setting.key === 'contract_templates'" class="flex-[2] w-full space-y-3">
                    <div class="flex items-center justify-between gap-3">
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400">Шаблоны договоров</label>
                        <button
                            type="button"
                            class="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-brand-700 bg-brand-50 hover:bg-brand-100 dark:bg-brand-500/10 dark:text-brand-300 dark:hover:bg-brand-500/20 rounded-lg"
                            @click="addContractTemplateRow(setting)"
                        >
                            <span class="material-icons-round text-[16px]">add</span>
                            Добавить шаблон
                        </button>
                    </div>
                    <div class="space-y-2">
                        <div
                            v-for="(template, index) in ensureContractTemplateDraft(setting)"
                            :key="`${setting.key}-${index}`"
                            class="grid grid-cols-1 gap-2 md:grid-cols-[1fr_1.4fr_220px_150px_auto] md:items-center"
                        >
                            <input
                                v-model="template.name"
                                type="text"
                                class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition-colors shadow-sm text-sm"
                                placeholder="Название для менеджера"
                                :disabled="savingKeys.has(setting.key)"
                            />
                            <input
                                v-model="template.id"
                                type="text"
                                class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition-colors shadow-sm text-sm font-mono"
                                placeholder="Google Template ID"
                                :disabled="savingKeys.has(setting.key)"
                            />
                            <select
                                v-model="template.document_role_type"
                                class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition-colors shadow-sm text-sm"
                                :disabled="savingKeys.has(setting.key)"
                            >
                                <option v-for="option in DOCUMENT_ROLE_OPTIONS" :key="option.value" :value="option.value">
                                    {{ option.label }}
                                </option>
                            </select>
                            <label class="flex h-10 items-center gap-2 rounded-lg border border-gray-300 bg-gray-50 px-3 text-sm text-gray-700 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200">
                                <input
                                    v-model="template.is_open_contract"
                                    type="checkbox"
                                    class="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
                                    :disabled="savingKeys.has(setting.key)"
                                />
                                <span>Открытый</span>
                            </label>
                            <button
                                type="button"
                                class="flex h-10 w-10 items-center justify-center rounded-lg text-red-500 transition-colors hover:bg-red-500/10"
                                title="Удалить шаблон"
                                :disabled="savingKeys.has(setting.key)"
                                @click="removeContractTemplateRow(setting, index)"
                            >
                                <span class="material-icons-round text-[20px]">delete</span>
                            </button>
                        </div>
                    </div>
                    <p v-if="!ensureContractTemplateDraft(setting).length" class="text-sm text-gray-500 dark:text-slate-400">
                        Шаблоны еще не добавлены.
                    </p>
                </div>
                <div v-else class="flex-1 w-full space-y-3">
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Значение</label>
                        <input
                            v-model="setting.value"
                            type="text"
                            class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition-colors shadow-sm"
                            :disabled="savingKeys.has(setting.key)"
                        />
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1">Описание</label>
                        <input
                            v-model="setting.description"
                            type="text"
                            class="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 focus:outline-none focus:border-brand-500 transition-colors shadow-sm text-sm"
                            :disabled="savingKeys.has(setting.key)"
                            placeholder="Добавьте описание..."
                        />
                    </div>
                </div>

                <div class="md:w-32 flex-shrink-0 flex justify-end w-full md:block">
                    <button
                        @click="setting.key === 'contract_templates' ? saveContractTemplates(setting) : saveSetting(setting)"
                        class="w-full flex justify-center items-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-brand-600 hover:bg-brand-500 active:bg-brand-700 transition-colors rounded-lg disabled:opacity-50 shadow-sm"
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
</template>
