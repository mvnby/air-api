<script setup lang="ts">
import LineFormattedText from './LineFormattedText.vue';
import { computed, ref } from 'vue';
import OrderServiceTitleInput from './OrderServiceTitleInput.vue';
import OrderServiceInstallationCalculator from './OrderServiceInstallationCalculator.vue';
import { type SuggestedInstallation } from './service-installation-choices';
import { Pencil } from 'lucide-vue-next';
import type { ManagerQuickTariffResponse, ManagerServiceEstimateResponse, ManagerInstallationStandardTariff } from '../../client';
import OrderServiceCatalogPicker from './OrderServiceCatalogPicker.vue';
import type { OrderWorkflowType } from './order-workspace';
import ServiceDescriptionModeSwitch from './ServiceDescriptionModeSwitch.vue';
import type { ServiceLine } from './order-editor-types';
import { formatMoney } from './order-utils';
import { useDemoReadOnly } from '../../services/manager-demo';
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
  workflow: OrderWorkflowType;
  customerId?: number | null;
  canOpenInstallationEstimate?: boolean;
  compact?: boolean;
  hideActions?: boolean;
  showCosts?: boolean;
  suggestedInstallations?: SuggestedInstallation[];
}>();

const emit = defineEmits<{
  focus: [index: number];
  input: [index: number];
  blur: [index: number];
  select: [payload: { index: number; option: ManagerQuickTariffResponse; quantity?: number }];
  addSuggested: [index: number];
  descriptionMode: [payload: { index: number; mode: ServiceDescriptionMode }];
  remove: [index: number, displayIndex?: number];
  editInstallation: [index: number, displayIndex: number];
  add: [];
  addTariff: [option: ManagerQuickTariffResponse];
  appendEstimate: [payload: { id: number; lines: Array<{ service_id?: number | null; title: string; quantity: number; price: number; cost?: number | null }> }];
  toggleEstimate: [];
  importEstimate: [];
  loadEstimates: [];
  rememberDescriptionMode: [mode: ServiceDescriptionMode];
  openInstallationEstimate: [];
  standardInstallation: [tariff: ManagerInstallationStandardTariff, edit: boolean];
}>();

const lines = defineModel<ServiceLine[]>('lines', { required: true });
const showCatalog = ref(false);
const calculatingLine = ref<ServiceLine | null>(null);
const applyCalculation = (line: ServiceLine, result: { title: string; description: string; price: number; installation_standard: ManagerInstallationStandardTariff }) => {
  if (!lines.value.includes(line)) return;
  Object.assign(line, result);
  calculatingLine.value = null;
};
defineExpose({ openCatalog: () => { showCatalog.value = !showCatalog.value; } });
const chooseTariff = (option: ManagerQuickTariffResponse) => {
  emit('addTariff', option);
  showCatalog.value = false;
};
const createEstimate = (payload: { id: number; lines: Array<{ service_id?: number | null; title: string; quantity: number; price: number; cost?: number | null }> }) => {
  emit('appendEstimate', payload);
  showCatalog.value = false;
};
const addCustom = () => {
  emit('add');
  showCatalog.value = false;
};
const demoReadOnly = useDemoReadOnly();
const compactShowCosts = computed(() => props.compact && props.showCosts && !demoReadOnly.value);
const editingIndex = defineModel<number | null>('editingIndex', { required: true });
const showEstimateImport = defineModel<boolean>('showEstimateImport', { required: true });
const selectedEstimateId = defineModel<number | null>('selectedEstimateId', { required: true });
const estimateSearchQuery = defineModel<string>('estimateSearchQuery', { required: true });
const estimateImportMode = defineModel<'detailed' | 'collapsed'>('estimateImportMode', { required: true });
const descriptionMode = defineModel<ServiceDescriptionMode>('descriptionMode', { required: true });

const filteredEstimates = computed(() => {
  const query = estimateSearchQuery.value.trim().toLowerCase();
  if (!query) return props.estimateOptions;
  return props.estimateOptions.filter((estimate) => (
    (estimate.title || '').toLowerCase().includes(query)
    || String(estimate.id).includes(query)
  ));
});
const lineTotal = (line: ServiceLine) => Number(line.quantity || 0) * Number(line.price || 0);
const displayLines = (line: ServiceLine) => line.installation_display_lines?.length
  ? line.installation_display_lines : [line];
const editLine = (index: number, displayIndex = 0) => {
  if (lines.value[index]?.installation_estimate_revision_id) emit('editInstallation', index, displayIndex);
  else editingIndex.value = index;
};
const updatePreferredMode = (mode: ServiceDescriptionMode) => {
  descriptionMode.value = mode;
  emit('rememberDescriptionMode', mode);
};
</script>

<template>
  <section :class="compact ? 'border-t border-slate-200 dark:border-slate-700' : 'mt-6'" aria-label="Услуги">
    <div v-if="!hideActions" class="mb-2"><h4 class="text-md font-semibold text-gray-800">Услуги</h4></div>
    <p v-if="servicesError" class="mb-2 text-xs text-red-300">{{ servicesError }}</p>
    <div class="space-y-2">
      <div v-for="(line, index) in lines" :key="`service-${index}`" class="relative bg-white" :class="compact ? 'border-b border-gray-100 dark:border-slate-800 dark:bg-slate-950' : 'rounded-xl border border-gray-200 p-3 shadow-sm'">
        <template v-if="compact">
          <div v-if="editingIndex === index && !line.installation_estimate_revision_id" class="p-3">
            <button type="button" data-order-usage="order_service_remove" class="mb-2 inline-flex h-8 items-center rounded-lg border border-red-200 bg-red-50 px-3 text-xs font-medium text-red-600 hover:bg-red-100" :aria-label="`Удалить услугу #${index + 1}`" @click="emit('remove', index)">Удалить услугу</button>
            <div class="grid grid-cols-6 gap-2 md:grid-cols-12 md:items-start">
              <div class="relative col-span-6 space-y-1 md:col-span-5">
                <span class="flex min-h-6 items-center justify-between gap-2 px-1 text-xs font-medium text-gray-500">
                  <span>Название</span>
                  <ServiceDescriptionModeSwitch v-if="line.template_full_description" :model-value="line.description_mode || 'short'" @update:model-value="emit('descriptionMode', { index, mode: $event })" />
                </span>
                <OrderServiceTitleInput v-model="line.title" :workflow="workflow" :autofocus="!line.title" :suggestions="suggestedInstallations" @focus="emit('focus', index)" @input="emit('input', index)" @blur="emit('blur', index)" @select="(option, quantity) => emit('select', { index, option, quantity })" @add-suggested="emit('addSuggested', index)" />
              </div>
              <label class="col-span-4 space-y-1 md:col-span-2"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Цена</span><input v-model.number="line.price" type="number" min="0" step="0.01" class="field-input" placeholder="0" /></label>
              <label class="col-span-2 space-y-1 md:col-span-1"><span class="flex h-auto items-center whitespace-nowrap px-1 text-xs font-medium text-gray-500 md:h-6 md:text-[11px]">Кол-во</span><input v-model.number="line.quantity" type="number" min="1" class="field-input" placeholder="1" /></label>
              <label v-if="compactShowCosts" class="col-span-3 space-y-1 md:col-span-2"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Себест.</span><input v-model.number="line.cost" type="number" min="0" step="0.01" class="field-input" placeholder="0" /></label>
              <div class="col-span-3 space-y-1 md:col-span-2"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Итого</span><div class="rounded-lg bg-gray-50 px-3 py-2"><p class="whitespace-nowrap text-base font-semibold leading-tight text-gray-900">{{ formatMoney(lineTotal(line)) }}</p></div></div>
              <label class="col-span-6 space-y-1 md:col-span-12"><span class="block text-xs font-medium text-gray-500">Описание для клиента</span><textarea v-model="line.description" data-testid="service-client-description" rows="2" maxlength="10000" class="field-input min-h-[64px] resize-y text-sm leading-relaxed [field-sizing:content]" placeholder="Состав работ и согласованные условия" /></label>
              <div class="col-span-6 flex flex-wrap items-center justify-between gap-2 md:col-span-12"><button type="button" data-testid="service-open-calculator" class="min-h-8 text-xs text-brand-700" @click="calculatingLine = calculatingLine === line ? null : line">{{ calculatingLine === line ? 'Скрыть расчёт' : 'Рассчитать монтаж' }}</button><button type="button" class="btn-mini-outline h-8 px-3 text-xs" @click="editingIndex = null">Готово</button></div>
              <OrderServiceInstallationCalculator v-if="calculatingLine === line" class="col-span-6 md:col-span-12" :initial-tariff="line.installation_standard" :quantity="line.quantity" @close="calculatingLine = null" @apply="applyCalculation(line, $event)" />
            </div>
          </div>
          <div v-else class="divide-y divide-gray-100">
            <div v-for="(display, displayIndex) in displayLines(line)" :key="`compact-service-${index}-${displayIndex}`" class="grid grid-cols-3 items-center gap-2 px-3 py-2.5" :class="compactShowCosts ? 'md:grid-cols-[minmax(0,1fr)_3.5rem_6rem_6.5rem_6rem_4.5rem]' : 'md:grid-cols-[minmax(0,1fr)_3.5rem_6rem_6.5rem_4.5rem]'" :data-testid="`compact-service-row-${index}-${displayIndex}`">
              <div class="col-span-3 min-w-0 md:col-auto">
                <p class="break-words text-sm font-semibold leading-snug text-slate-900 dark:text-slate-100"><LineFormattedText :text="display.title || 'Новая услуга'" /></p>
                <p v-if="display.description" class="break-words text-xs font-normal leading-relaxed text-slate-500 dark:text-slate-400"><LineFormattedText :text="display.description" /></p>
                <span v-if="line.installation_estimate_revision_id" class="text-[11px] font-medium text-slate-500">По расчёту</span>
              </div>
              <span class="text-left text-xs text-slate-600 dark:text-slate-300 md:text-center"><span class="mb-1 block font-medium text-slate-500 md:hidden">Кол-во</span>{{ display.quantity }}</span>
              <span class="text-left text-xs text-slate-600 dark:text-slate-300 md:text-right"><span class="mb-1 block font-medium text-slate-500 md:hidden">Цена</span>{{ formatMoney(display.price) }}</span>
              <span class="text-left text-xs font-semibold text-slate-900 dark:text-slate-100 md:text-right"><span class="mb-1 block font-medium text-slate-500 md:hidden">Итого</span>{{ formatMoney(display.quantity * display.price) }}</span>
              <span v-if="compactShowCosts" class="col-span-2 text-left text-xs text-slate-600 dark:text-slate-300 md:col-auto md:text-right"><span class="mb-1 block font-medium text-slate-500 md:hidden">Себест.</span>{{ line.installation_estimate_revision_id ? '—' : formatMoney(line.cost) }}</span>
              <div class="flex justify-end md:justify-center" :class="compactShowCosts ? 'md:col-auto' : 'col-span-3 md:col-auto'">
                <button type="button" data-order-usage="order_service_edit" class="btn-mini-outline h-8 w-8 shrink-0 justify-center p-0" :aria-label="`Редактировать услугу #${index + 1}.${displayIndex + 1}`" title="Редактировать услугу" @click="editLine(index, displayIndex)"><Pencil :size="16" aria-hidden="true" /></button>
                <button type="button" data-order-usage="order_service_remove" class="ml-1 inline-flex h-8 w-8 items-center justify-center rounded-lg text-lg text-red-600 hover:bg-red-50" :aria-label="`Удалить услугу #${index + 1}.${displayIndex + 1}`" title="Удалить услугу" @click="emit('remove', index, displayIndex)">×</button>
              </div>
            </div>
          </div>
        </template>
        <template v-else>
        <button v-if="editingIndex === index && !line.installation_estimate_revision_id" type="button" data-order-usage="order_service_remove" class="absolute -right-2 -top-2 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full border border-red-200 bg-red-50 text-lg font-bold text-red-600 shadow-sm transition-colors hover:bg-red-100" :aria-label="`Удалить услугу #${index + 1}`" title="Удалить услугу" @click="emit('remove', index)">
          ×
        </button>
        <div v-if="editingIndex !== index || line.installation_estimate_revision_id" class="flex min-w-0 items-start gap-3">
          <div class="min-w-0 flex-1">
            <div v-for="(display, displayIndex) in displayLines(line)" :key="displayIndex" :class="displayIndex ? 'mt-3' : ''">
            <p class="break-words text-sm font-semibold leading-snug text-slate-900 dark:text-slate-100"><LineFormattedText :text="display.title || 'Новая услуга'" /></p>
            <p v-if="display.description" class="mt-1 break-words text-xs font-normal leading-relaxed text-slate-500"><LineFormattedText :text="display.description" /></p>
            <div class="mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
              <span>{{ display.quantity }} × {{ formatMoney(display.price) }} <span v-if="line.installation_estimate_revision_id" class="ml-1 text-slate-500">По расчёту</span></span>
              <span class="font-semibold text-slate-800 dark:text-slate-200">{{ formatMoney(display.quantity * display.price) }}</span>
            </div>
            <div class="mt-1 flex gap-1"><button type="button" data-order-usage="order_service_edit" class="btn-mini-outline h-8 text-xs" @click="editLine(index, displayIndex)">Редактировать</button><button type="button" data-order-usage="order_service_remove" class="h-8 px-2 text-xs text-red-600" @click="emit('remove', index, displayIndex)">Удалить</button></div>
            </div>
          </div>
        </div>
        <div v-else class="grid grid-cols-6 gap-2 md:grid-cols-12 md:items-start">
          <div class="relative col-span-6 space-y-1 md:col-span-5">
            <span class="flex min-h-6 items-center justify-between gap-2 px-1 text-xs font-medium text-gray-500">
              <span>Название</span>
              <ServiceDescriptionModeSwitch v-if="line.template_full_description" :model-value="line.description_mode || 'short'" @update:model-value="emit('descriptionMode', { index, mode: $event })" />
            </span>
            <OrderServiceTitleInput v-model="line.title" :workflow="workflow" :autofocus="!line.title" :suggestions="suggestedInstallations" @focus="emit('focus', index)" @input="emit('input', index)" @blur="emit('blur', index)" @select="(option, quantity) => emit('select', { index, option, quantity })" @add-suggested="emit('addSuggested', index)" />
          </div>
          <label class="col-span-4 space-y-1 md:col-span-2"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Цена</span><input v-model.number="line.price" type="number" min="0" step="0.01" class="field-input" placeholder="0" /></label>
          <label class="col-span-2 space-y-1 md:col-span-1"><span class="flex h-auto items-center whitespace-nowrap px-1 text-xs font-medium text-gray-500 md:h-6 md:text-[11px]">Кол-во</span><input v-model.number="line.quantity" type="number" min="1" class="field-input" placeholder="1" /></label>
          <label v-if="!demoReadOnly" class="col-span-3 space-y-1 md:col-span-2"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Себест.</span><input v-model.number="line.cost" type="number" min="0" step="0.01" class="field-input" placeholder="0" /></label>
          <div class="col-span-3 space-y-1 md:col-span-2"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Итого</span><div class="rounded-lg bg-gray-50 px-3 py-2"><p class="whitespace-nowrap text-base font-semibold leading-tight text-gray-900">{{ formatMoney(lineTotal(line)) }}</p></div></div>
          <label class="col-span-6 space-y-1 md:col-span-12"><span class="block text-xs font-medium text-gray-500">Описание для клиента</span><textarea v-model="line.description" data-testid="service-client-description" rows="2" maxlength="10000" class="field-input min-h-[64px] resize-y text-sm leading-relaxed [field-sizing:content]" placeholder="Состав работ и согласованные условия" /></label>
          <div class="col-span-6 flex flex-wrap items-center justify-between gap-2 md:col-span-12"><button type="button" data-testid="service-open-calculator" class="min-h-8 text-xs text-brand-700" @click="calculatingLine = calculatingLine === line ? null : line">{{ calculatingLine === line ? 'Скрыть расчёт' : 'Рассчитать монтаж' }}</button><button type="button" class="btn-mini-outline h-8 px-3 text-xs" @click="editingIndex = null">Готово</button></div>
          <OrderServiceInstallationCalculator v-if="calculatingLine === line" class="col-span-6 md:col-span-12" :initial-tariff="line.installation_standard" :quantity="line.quantity" @close="calculatingLine = null" @apply="applyCalculation(line, $event)" />
        </div>
        </template>
      </div>
    </div>

    <div v-if="!hideActions" class="mt-3 grid grid-cols-2 gap-2" :class="compact ? 'sm:max-w-md' : ''">
      <button type="button" data-testid="add-service-line" data-order-usage="order_service_add" class="btn-mini justify-center" @click="emit('add')">+ услуга</button>
      <button type="button" class="btn-mini-outline justify-center" :class="showEstimateImport ? 'border-brand-200 bg-brand-50 text-brand-700' : ''" @click="emit('toggleEstimate')">Из сметы</button>
    </div>
    <OrderServiceCatalogPicker
      v-if="showCatalog"
      :workflow="workflow"
      :customer-id="customerId"
      :can-open-installation-estimate="canOpenInstallationEstimate"
      @choose="chooseTariff"
      @custom="addCustom"
      @created-estimate="createEstimate"
      @close="showCatalog = false"
      @open-installation-estimate="showCatalog = false; emit('openInstallationEstimate')"
      @standard-installation="(tariff, edit) => { showCatalog = false; emit('standardInstallation', tariff, edit); }"
    />
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
        <button type="button" class="btn-mini-outline justify-center whitespace-nowrap" @click="showEstimateImport = false; showCatalog = true">Создать новую смету</button>
      </div>
      <p class="text-xs text-gray-500">Показываем до 100 последних смет. Структура определяет количество строк, а формат текста — краткую или подробную формулировку.</p>
    </div>
  </section>
</template>
