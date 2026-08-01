<script setup lang="ts">
import { computed } from 'vue';
import type { ManagerQuickTariffResponse, ManagerServiceEstimateResponse } from '../../client';
import ServiceDescriptionModeSwitch from './ServiceDescriptionModeSwitch.vue';
import type { ServiceLine } from './order-editor-types';
import { formatMoney } from './order-utils';
import type { ServiceDescriptionMode } from './service-description-mode';

const props = defineProps<{
  serviceOptions: ManagerQuickTariffResponse[];
  serviceLookupLoading: boolean;
  activeSuggestionIndex: number | null;
  servicesError?: string;
  estimateOptions: ManagerServiceEstimateResponse[];
  estimateOptionsLoading: boolean;
  importingEstimate: boolean;
  formatServiceKind: (kind?: string | null) => string;
}>();

const emit = defineEmits<{
  focus: [index: number];
  input: [index: number];
  blur: [index: number];
  select: [payload: { index: number; option: ManagerQuickTariffResponse }];
  descriptionMode: [payload: { index: number; mode: ServiceDescriptionMode }];
  remove: [index: number];
  add: [];
  toggleEstimate: [];
  importEstimate: [];
  loadEstimates: [];
  rememberDescriptionMode: [mode: ServiceDescriptionMode];
}>();

const lines = defineModel<ServiceLine[]>('lines', { required: true });
const editingIndex = defineModel<number | null>('editingIndex', { required: true });
const showEstimateImport = defineModel<boolean>('showEstimateImport', { required: true });
const selectedEstimateId = defineModel<number | null>('selectedEstimateId', { required: true });
const estimateSearchQuery = defineModel<string>('estimateSearchQuery', { required: true });
const estimateImportMode = defineModel<'detailed' | 'collapsed'>('estimateImportMode', { required: true });
const descriptionMode = defineModel<ServiceDescriptionMode>('descriptionMode', { required: true });

const suggestionsFor = (index: number) => (
  props.activeSuggestionIndex === index ? props.serviceOptions.slice(0, 10) : []
);
const filteredEstimates = computed(() => {
  const query = estimateSearchQuery.value.trim().toLowerCase();
  if (!query) return props.estimateOptions;
  return props.estimateOptions.filter((estimate) => (
    (estimate.title || '').toLowerCase().includes(query)
    || String(estimate.id).includes(query)
  ));
});
const lineTotal = (line: ServiceLine) => Number(line.quantity || 0) * Number(line.price || 0);
const updatePreferredMode = (mode: ServiceDescriptionMode) => {
  descriptionMode.value = mode;
  emit('rememberDescriptionMode', mode);
};
</script>

<template>
  <section class="mt-6">
    <div class="mb-2"><h4 class="text-md font-semibold text-gray-800">Услуги</h4></div>
    <p v-if="servicesError" class="mb-2 text-xs text-red-300">{{ servicesError }}</p>
    <div class="space-y-2">
      <div v-for="(line, index) in lines" :key="`service-${index}`" class="relative rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
        <button v-if="editingIndex === index" type="button" class="absolute -right-2 -top-2 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full border border-red-200 bg-red-50 text-lg font-bold text-red-600 shadow-sm transition-colors hover:bg-red-100" :aria-label="`Удалить услугу #${index + 1}`" title="Удалить услугу" @click="emit('remove', index)">
          ×
        </button>
        <div v-if="editingIndex !== index" class="flex min-w-0 items-start gap-3">
          <div class="min-w-0 flex-1">
            <p class="break-words text-sm font-semibold leading-snug text-slate-900 dark:text-slate-100">{{ line.title || 'Новая услуга' }}</p>
            <div class="mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
              <span>{{ line.quantity }} × {{ formatMoney(line.price) }}</span>
              <span class="font-semibold text-slate-800 dark:text-slate-200">{{ formatMoney(lineTotal(line)) }}</span>
            </div>
          </div>
          <button type="button" class="btn-mini-outline h-9 w-9 shrink-0 justify-center p-0" :aria-label="`Редактировать услугу #${index + 1}`" title="Редактировать" @click="editingIndex = index">
            <span class="material-icons-round text-[17px]">edit</span>
          </button>
        </div>
        <div v-else class="grid grid-cols-6 gap-2 md:grid-cols-12 md:items-start">
          <div class="relative col-span-6 space-y-1 md:col-span-5">
            <span class="flex min-h-6 items-center justify-between gap-2 px-1 text-xs font-medium text-gray-500">
              <span>Название</span>
              <ServiceDescriptionModeSwitch v-if="line.template_full_description" :model-value="line.description_mode || 'short'" @update:model-value="emit('descriptionMode', { index, mode: $event })" />
            </span>
            <textarea
              v-model="line.title"
              class="field-input min-h-[64px] resize-none overflow-hidden text-sm leading-snug focus:min-h-[120px] focus:resize-y focus:overflow-auto sm:text-base"
              rows="2"
              placeholder="Название услуги"
              @focus="emit('focus', index)"
              @input="emit('input', index)"
              @blur="emit('blur', index)"
            />
            <div v-if="line.title.trim().length >= 2 && activeSuggestionIndex === index && (serviceLookupLoading || suggestionsFor(index).length)" class="absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-auto rounded-[12px] border border-gray-200 bg-white p-1 shadow-xl">
              <div v-if="serviceLookupLoading" class="px-3 py-2 text-xs text-gray-500">Ищем тарифы...</div>
              <button
                v-for="item in suggestionsFor(index)"
                :key="`service-tariff-suggest-${index}-${item.tariff_id}`"
                type="button"
                :data-testid="`select-service-${item.tariff_id}`"
                class="mb-1 block w-full rounded-[12px] px-3 py-2 text-left text-xs text-gray-700 hover:bg-slate-100 last:mb-0"
                @mousedown.prevent
                @click="emit('select', { index, option: item })"
              >
                <p class="line-clamp-2 font-medium text-gray-900">{{ item.short_name || item.title }}</p>
                <p v-if="item.full_description && item.full_description !== item.short_name" class="mt-0.5 line-clamp-2 text-[11px] leading-snug text-gray-500">{{ item.full_description }}</p>
                <p class="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-gray-500">
                  <span>{{ formatMoney(item.price) }}</span>
                  <span v-if="item.service_kind">· {{ formatServiceKind(item.service_kind) }}</span>
                  <span v-if="item.category">· {{ item.category }}</span>
                  <span v-if="item.included_route_meters">· трасса до {{ item.included_route_meters }} м</span>
                </p>
              </button>
            </div>
          </div>
          <label class="col-span-4 space-y-1 md:col-span-2"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Цена</span><input v-model.number="line.price" type="number" min="0" class="field-input" placeholder="0" /></label>
          <label class="col-span-2 space-y-1 md:col-span-1"><span class="flex h-auto items-center whitespace-nowrap px-1 text-xs font-medium text-gray-500 md:h-6 md:text-[11px]">Кол-во</span><input v-model.number="line.quantity" type="number" min="1" class="field-input" placeholder="1" /></label>
          <label class="col-span-3 space-y-1 md:col-span-2"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Себест.</span><input v-model.number="line.cost" type="number" min="0" class="field-input" placeholder="0" /></label>
          <div class="col-span-3 space-y-1 md:col-span-2"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Итого</span><div class="rounded-lg bg-gray-50 px-3 py-2"><p class="whitespace-nowrap text-base font-semibold leading-tight text-gray-900">{{ formatMoney(lineTotal(line)) }}</p></div></div>
          <div class="col-span-6 flex justify-end md:col-span-12"><button type="button" class="btn-mini-outline h-8 px-3 text-xs" @click="editingIndex = null">Готово</button></div>
        </div>
      </div>
    </div>

    <div class="mt-3 grid grid-cols-2 gap-2">
      <button type="button" data-testid="add-service-line" class="btn-mini justify-center" @click="emit('add')">+ услуга</button>
      <button type="button" class="btn-mini-outline justify-center" :class="showEstimateImport ? 'border-teal-200 bg-teal-50 text-teal-700' : ''" @click="emit('toggleEstimate')">Из сметы</button>
    </div>
    <div v-if="showEstimateImport" class="mt-3 grid gap-2 rounded-xl border border-gray-200 bg-gray-50 p-3">
      <div class="grid gap-2 md:grid-cols-3">
        <label class="space-y-1 md:col-span-3">
          <span class="px-1 text-xs font-medium text-gray-500">Смета</span>
          <select v-model="selectedEstimateId" class="field-input min-w-0" :disabled="estimateOptionsLoading">
            <option :value="null">Выберите смету</option>
            <option v-for="estimate in filteredEstimates" :key="estimate.id" :value="estimate.id">#{{ estimate.id }} · {{ estimate.title }} · {{ formatMoney(estimate.total) }} {{ estimate.currency }}</option>
          </select>
        </label>
        <label class="space-y-1"><span class="px-1 text-xs font-medium text-gray-500">Поиск</span><input v-model="estimateSearchQuery" class="field-input" placeholder="ID или название" /></label>
        <label class="space-y-1"><span class="px-1 text-xs font-medium text-gray-500">Структура</span><select v-model="estimateImportMode" class="field-input"><option value="detailed">По строкам</option><option value="collapsed">Одной строкой</option></select></label>
        <div class="space-y-1"><span class="block px-1 text-xs font-medium text-gray-500">Текст позиции</span><ServiceDescriptionModeSwitch :model-value="descriptionMode" @update:model-value="updatePreferredMode" /></div>
      </div>
      <div class="flex flex-col gap-2 sm:flex-row">
        <button type="button" data-testid="import-estimate" class="btn-mini justify-center whitespace-nowrap" :disabled="importingEstimate || !selectedEstimateId" @click="emit('importEstimate')">{{ importingEstimate ? 'Добавляю...' : 'Добавить из сметы' }}</button>
        <button type="button" class="btn-mini-outline justify-center whitespace-nowrap" :disabled="estimateOptionsLoading" title="Обновить список смет" @click="emit('loadEstimates')">Обновить</button>
      </div>
      <p class="text-xs text-gray-500">Показываем 10 последних смет. Структура определяет количество строк, а формат текста — краткую или подробную формулировку.</p>
    </div>
  </section>
</template>
