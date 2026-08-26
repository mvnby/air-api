<script setup lang="ts">
import { inject } from 'vue';
import AdditionalConditionsLibrary from '../../../components/orders/AdditionalConditionsLibrary.vue';
import AddressSuggestInput from '../../../components/ui/AddressSuggestInput.vue';
import { DOCUMENT_FILE_ACCEPT, DOCUMENT_ROLE_OPTIONS, DOCUMENT_TYPES } from '../model/document-constants';
import { formatMoney, getRoleLabel } from '../model/document-formatters';
import WaybillComposition from './WaybillComposition.vue';
import { DocumentGenerationContextKey, type DocumentGenerationContext } from '../model/document-generation-context';

const context = inject<DocumentGenerationContext>(DocumentGenerationContextKey);
if (!context) throw new Error('DocumentGenerationForm requires a generation context');

const {
  activeActServiceLines, actScopeAddress, actScopeTitle, actServiceQuantity, additionalConditions,
  additionalConditionsMode, baseDocumentOptions, contractTemplates, createChecklist, creatingActBranch,
  customerContracts, externalContractDate, externalContractFile, externalContractNumber, externalContractOpen,
  documentDate, externalContractUrl, hasClosingBaseDocument, inheritedDocumentRoleType, isDocumentTypeLocked, isGeneratingDoc,
  isRegisteringExternalContract, isWaybillDocument, needsContractBinding, newActBranchAddress, newActBranchName,
  selectedActBranchId, selectedBaseDocumentBinding, selectedContractTemplateId, selectedDocumentRoleBinding,
  selectedDocumentType, selectedDocumentTypeItem, showAdvancedSettings, showsAdditionalConditions,
  showsDocumentRoleControl, waybillProductLines,
  actions: { createActBranch, generateDocument, handleExternalContractFile, lockedDocumentTitle,
    maxActServiceQuantity, onActBranchChange, onActServiceCheckboxChange, openCustomerProfileForContract,
    registerExternalContract, selectDocumentType, setActServiceLineQuantity, syncActServiceSelection },
  customerBranches, documentAccess, isCreatePanelOpen,
} = context;
</script>

<template>
      <div v-if="isCreatePanelOpen && documentAccess.canCreate" class="order-first rounded-xl border border-teal-200 bg-teal-50/30 p-3 dark:border-teal-800/70 dark:bg-teal-950/20">
        <div class="mb-3 flex items-center justify-between gap-3">
          <div>
            <p class="text-[11px] font-bold uppercase tracking-wide text-teal-700 dark:text-teal-300">Создание документа</p>
            <p class="text-xs text-slate-500 dark:text-slate-400">Проверьте обязательные поля и создайте документ.</p>
          </div>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-xs font-semibold text-slate-500 hover:bg-white dark:text-slate-400 dark:hover:bg-slate-800"
            @click="isCreatePanelOpen = false"
          >
            Закрыть
          </button>
        </div>

        <div class="space-y-4">
          <div>
            <p class="mb-2 text-xs font-semibold text-slate-700 dark:text-slate-200">Шаг 1: выберите тип документа</p>
            <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <button
                v-for="dtype in DOCUMENT_TYPES"
                :key="dtype.type"
                type="button"
                class="flex min-h-10 items-center justify-between rounded-lg border px-3 py-2 text-left text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                :class="selectedDocumentType === dtype.type ? 'border-teal-500 bg-white text-teal-700 shadow-sm dark:bg-slate-900 dark:text-teal-300' : 'border-slate-200 bg-white/80 text-slate-600 hover:border-teal-300 hover:text-teal-700 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300'"
                :disabled="isDocumentTypeLocked(dtype.type)"
                :title="isDocumentTypeLocked(dtype.type) ? lockedDocumentTitle(dtype.type) : ''"
                @click="selectDocumentType(dtype.type)"
              >
                <span>{{ dtype.label }}</span>
                <span v-if="isDocumentTypeLocked(dtype.type)" class="material-icons-round text-[16px] text-amber-500">lock</span>
              </button>
            </div>
            <p v-if="isDocumentTypeLocked(selectedDocumentType)" class="mt-2 text-xs text-amber-600 dark:text-amber-400">
              {{ lockedDocumentTitle(selectedDocumentType) }}.
            </p>
          </div>

          <div class="grid gap-3 md:grid-cols-2">
            <label class="text-xs font-medium text-slate-600 dark:text-slate-300">Шаг 2: дата документа
              <input
                v-model="documentDate"
                type="date"
                class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              />
            </label>
            <label v-if="selectedDocumentType === 'contract'" class="text-xs font-medium text-slate-600 dark:text-slate-300">Шаг 2: шаблон
              <select
                v-model="selectedContractTemplateId"
                class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              >
                <option v-for="template in contractTemplates" :key="template.id" :value="template.id">{{ template.name }}</option>
              </select>
            </label>
          </div>

          <div v-if="showsDocumentRoleControl" class="rounded-xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-700/50 dark:bg-slate-800/40">
            <label class="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-200">Шаг 2: роли сторон</label>
            <select
              v-model="selectedDocumentRoleBinding"
              class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            >
              <option value="">Оставить по шаблону · {{ getRoleLabel(inheritedDocumentRoleType) }}</option>
              <option v-for="option in DOCUMENT_ROLE_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </div>

      <div v-if="needsContractBinding" class="rounded-xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-700/50 dark:bg-slate-800/40">
        <div class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <label class="block text-xs font-semibold text-slate-700 dark:text-slate-200">Шаг 2: документ-основание</label>
          <button
            type="button"
            class="inline-flex w-fit items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            @click="externalContractOpen = !externalContractOpen"
          >
            <span class="material-icons-round text-[16px]">post_add</span>
            Внешний договор
          </button>
        </div>

        <select
          v-model="selectedBaseDocumentBinding"
          class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
        >
          <option value="">Выберите основание</option>
          <option v-for="option in baseDocumentOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>

        <p v-if="baseDocumentOptions.length > 1" class="mt-2 text-xs text-slate-500 dark:text-slate-400">
          Если в заказе несколько счетов, договоров или оферт, закрывающий документ будет привязан к выбранному основанию.
        </p>

        <form
          v-if="externalContractOpen"
          class="mt-3 space-y-3 rounded-lg border border-dashed border-teal-300 bg-teal-50/40 p-3 dark:border-teal-700/70 dark:bg-teal-950/20"
          @submit.prevent="registerExternalContract"
        >
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="text-xs font-medium text-slate-600 dark:text-slate-300">Номер договора
              <input
                v-model="externalContractNumber"
                type="text"
                class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                placeholder="Например, 44-ЭА/2026"
              />
            </label>
            <label class="text-xs font-medium text-slate-600 dark:text-slate-300">Дата договора
              <input
                v-model="externalContractDate"
                type="date"
                class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </label>
          </div>
          <label class="block text-xs font-medium text-slate-600 dark:text-slate-300">Ссылка на договор
            <input
              v-model="externalContractUrl"
              type="url"
              class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              placeholder="https://..."
            />
          </label>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label class="inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-300">
              <span class="material-icons-round text-[18px] text-teal-600 dark:text-teal-400">upload_file</span>
              <span>{{ externalContractFile?.name || 'Прикрепить файл вместо ссылки' }}</span>
              <input type="file" class="hidden" :accept="DOCUMENT_FILE_ACCEPT" @change="handleExternalContractFile" />
            </label>
            <div class="flex justify-end gap-2">
              <button
                type="button"
                class="rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                @click="externalContractOpen = false"
              >
                Отмена
              </button>
              <button
                type="submit"
                class="inline-flex items-center gap-1 rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-teal-700 disabled:opacity-60"
                :disabled="isRegisteringExternalContract"
              >
                <span v-if="isRegisteringExternalContract" class="material-icons-round animate-spin text-[16px]">loop</span>
                <span v-else class="material-icons-round text-[16px]">check</span>
                Добавить договор
              </button>
            </div>
          </div>
        </form>

        <div
          v-if="customerContracts.length === 0"
          class="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-slate-300 bg-white p-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-300"
        >
          <span>У клиента нет открытых договоров.</span>
          <button
            type="button"
            class="rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-500/50"
            @click="openCustomerProfileForContract"
          >
            Создать открытый договор
          </button>
        </div>
        <p v-else-if="!hasClosingBaseDocument" class="mt-2 text-xs text-amber-600 dark:text-amber-400">
          Для актов и накладных нужен договор, счет или оферта.
        </p>
      </div>

          <div
            v-if="selectedDocumentType === 'act'"
            class="rounded-xl border border-teal-200 bg-white p-3 dark:border-teal-800/70 dark:bg-slate-900/70"
          >
            <div class="mb-3">
              <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">Шаг 3: объект и строки акта</p>
              <p class="text-[11px] text-slate-500 dark:text-slate-400">
                Можно выпустить несколько актов по одному договору, разделив услуги по объектам.
              </p>
            </div>

            <div class="grid gap-3 md:grid-cols-2">
              <label class="text-xs font-medium text-slate-600 dark:text-slate-300 md:col-span-2">Объект клиента
                <select
                  v-model.number="selectedActBranchId"
                  class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
                  @change="onActBranchChange"
                >
                  <option :value="null">Адрес из заказа / вручную</option>
                  <option v-for="branch in customerBranches" :key="`act-branch-${branch.id}`" :value="branch.id">
                    {{ branch.name || `Объект #${branch.id}` }} — {{ branch.delivery_address }}
                  </option>
                </select>
              </label>
              <input
                v-model="actScopeTitle"
                class="field-input text-sm"
                placeholder="Название объекта, если нужно"
              />
              <AddressSuggestInput
                v-model="actScopeAddress"
                placeholder="Адрес объекта"
                input-class="text-sm"
                @input="selectedActBranchId = null"
              />
            </div>

            <div class="mt-3 grid gap-2 rounded-lg border border-dashed border-slate-300 bg-slate-50/70 p-3 dark:border-slate-700 dark:bg-slate-800/40 md:grid-cols-[1fr_1.4fr_auto]">
              <input
                v-model="newActBranchName"
                class="field-input text-sm"
                placeholder="Новый объект"
              />
              <AddressSuggestInput
                v-model="newActBranchAddress"
                placeholder="Адрес нового объекта"
                input-class="text-sm"
              />
              <button
                type="button"
                class="inline-flex items-center justify-center gap-1 rounded-lg border border-teal-300 bg-white px-3 py-2 text-xs font-semibold text-teal-700 hover:bg-teal-50 disabled:opacity-60 dark:border-teal-700 dark:bg-slate-900 dark:text-teal-300 dark:hover:bg-teal-950/30"
                :disabled="creatingActBranch"
                @click="createActBranch"
              >
                <span v-if="creatingActBranch" class="material-icons-round animate-spin text-[16px]">loop</span>
                <span v-else class="material-icons-round text-[16px]">add_location_alt</span>
                Добавить
              </button>
            </div>

            <div class="mt-3">
              <div class="mb-2 flex items-center justify-between gap-3">
                <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">Услуги в акте</p>
                <button
                  type="button"
                  class="text-xs font-semibold text-teal-700 hover:text-teal-800 dark:text-teal-300"
                  @click="syncActServiceSelection"
                >
                  Выбрать все
                </button>
              </div>
              <div v-if="activeActServiceLines.length" class="space-y-2">
                <label
                  v-for="line in activeActServiceLines"
                  :key="`act-service-${line.id}`"
                  class="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50/80 p-2 text-sm dark:border-slate-700 dark:bg-slate-800/50"
                >
                  <input
                    type="checkbox"
                    class="mt-1 h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                    :checked="actServiceQuantity(line.id) > 0"
                    @change="onActServiceCheckboxChange(line.id, $event)"
                  />
                  <span class="min-w-0 flex-1">
                    <span class="block font-medium text-slate-800 dark:text-slate-100">{{ line.service_title }}</span>
                    <span class="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                      <span>{{ line.quantity }} шт. · {{ formatMoney(line.line_total) }}</span>
                      <span class="inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 shadow-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
                        <span>В акт</span>
                        <input
                          type="number"
                          min="0"
                          :max="maxActServiceQuantity(line)"
                          step="1"
                          inputmode="numeric"
                          class="h-7 w-14 rounded border border-slate-200 bg-white px-2 text-center text-sm font-semibold text-slate-800 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:ring-teal-900/40"
                          :value="actServiceQuantity(line.id)"
                          @input="setActServiceLineQuantity(line, ($event.target as HTMLInputElement).value)"
                        />
                        <span>из {{ maxActServiceQuantity(line) }}</span>
                      </span>
                    </span>
                  </span>
                </label>
              </div>
              <p v-else class="rounded-lg border border-dashed border-amber-300 bg-amber-50 px-3 py-3 text-xs font-semibold text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/20 dark:text-amber-300">
                В активном предложении нет услуг для акта.
              </p>
            </div>
          </div>

          <WaybillComposition v-if="isWaybillDocument" :lines="waybillProductLines" />

          <div v-if="showsAdditionalConditions">
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
              @click="showAdvancedSettings = !showAdvancedSettings"
            >
              <span class="material-icons-round text-[16px]">{{ showAdvancedSettings ? 'expand_less' : 'tune' }}</span>
              {{ showAdvancedSettings ? 'Скрыть дополнительные условия' : 'Дополнительные условия' }}
            </button>
          </div>

          <div v-if="showAdvancedSettings && showsAdditionalConditions" class="space-y-3">
            <AdditionalConditionsLibrary
              v-model="additionalConditions"
              :default-mode="additionalConditionsMode"
            />
          </div>

          <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700/50 dark:bg-slate-900/60">
            <p class="mb-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
              {{ isWaybillDocument ? 'Шаг 4: проверьте перед созданием' : 'Шаг 3: проверьте перед созданием' }}
            </p>
            <dl class="grid gap-2 text-xs sm:grid-cols-2">
              <div v-for="item in createChecklist" :key="item.label" class="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/70">
                <dt class="text-slate-500 dark:text-slate-400">{{ item.label }}</dt>
                <dd class="truncate font-semibold text-slate-800 dark:text-slate-100">{{ item.value }}</dd>
              </div>
            </dl>
            <div class="mt-3 flex justify-end gap-2">
              <button
                type="button"
                class="rounded-lg px-3 py-2 text-sm font-semibold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                @click="isCreatePanelOpen = false"
              >
                Отмена
              </button>
              <button
                type="button"
                class="inline-flex items-center gap-1 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-teal-700 disabled:opacity-60"
                :disabled="isGeneratingDoc || isDocumentTypeLocked(selectedDocumentType)"
                @click="generateDocument(selectedDocumentType)"
              >
                <span v-if="isGeneratingDoc" class="material-icons-round animate-spin text-[18px]">loop</span>
                <span v-else class="material-icons-round text-[18px]">check</span>
                Создать {{ selectedDocumentTypeItem.label }}
              </button>
            </div>
          </div>
        </div>
      </div>

</template>
