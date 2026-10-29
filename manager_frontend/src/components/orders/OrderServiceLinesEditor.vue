<script setup lang="ts">
import OrderMoney from './OrderMoney.vue';
import OrderLineEditorActions from './OrderLineEditorActions.vue';
import LineFormattedText from './LineFormattedText.vue';
import { computed, nextTick, ref, watch } from 'vue';
import { beginLineEdit, cancelLineEdit, commitLineEdit, focusInvalidLineEditor, focusLineEditor, hasLineEdits, lineErrors, lineKey } from './order-line-drafts';
import OrderServiceTitleInput from './OrderServiceTitleInput.vue';
import OrderServiceInstallationCalculator from './OrderServiceInstallationCalculator.vue';
import { type SuggestedInstallation } from './service-installation-choices';
import { Pencil, Trash2 } from 'lucide-vue-next';
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
const rows = new Map<number, HTMLElement>();
const touched = ref<Record<number, string[]>>({});
const errorsFor = (line: ServiceLine): Record<string, string> => ({ ...lineErrors(line, line.title),
  ...((line.description?.length || 0) > 10000 ? { description: 'Не более 10000 символов' } : {}) });
const touch = (line: ServiceLine, field: string) => { const key = lineKey(line); touched.value[key] = [...(touched.value[key] || []), field]; };
const fieldError = (line: ServiceLine, field: string) => touched.value[lineKey(line)]?.includes(field) ? errorsFor(line)[field] : '';
const finishEditing = (line: ServiceLine) => {
  const group = line.editor?.group;
  const targets = group != null ? lines.value.filter(row => row.editor?.group === group) : [line];
  for (const row of targets) touched.value[lineKey(row)] = ['title', 'quantity', 'price', 'cost', 'description'];
  const invalid = targets.find(row => Object.keys(errorsFor(row)).length);
  if (invalid) { void focusInvalidEditor(invalid); return; }
  commitLineEdit(line, lines.value);
  editingIndex.value = null;
  calculatingLine.value = null;
};
const cancelEditing = (line: ServiceLine) => { cancelLineEdit(lines.value, line); editingIndex.value = null; calculatingLine.value = null; };
const focusEditor = async (line: ServiceLine) => { await nextTick(); await focusLineEditor(rows.get(lineKey(line))); };
const focusInvalidEditor = (line: ServiceLine) => focusInvalidLineEditor(rows.get(lineKey(line)));
const showCatalog = ref(false);
const calculatingLine = ref<ServiceLine | null>(null);
const applyCalculation = (line: ServiceLine, result: { title: string; description: string; price: number; installation_standard: ManagerInstallationStandardTariff }) => {
  if (!lines.value.includes(line)) return;
  Object.assign(line, result);
  calculatingLine.value = null;
};
const validateDrafts = () => {
  const drafts = lines.value.filter(line => line.editor && (line.editor.original || hasLineEdits([line])));
  for (const line of drafts) touched.value[lineKey(line)] = ['title', 'quantity', 'price', 'cost', 'description'];
  const invalid = drafts.find(line => Object.keys(errorsFor(line)).length);
  if (invalid) void focusInvalidEditor(invalid);
  return !invalid;
};
const commitDrafts = () => {
  for (const line of [...lines.value]) {
    if (!line.editor) continue;
    if (!line.editor.original && !hasLineEdits([line])) cancelLineEdit(lines.value, line);
    else commitLineEdit(line, lines.value);
  }
  editingIndex.value = null;
  calculatingLine.value = null;
};
const cancelDrafts = () => {
  for (const line of [...lines.value]) if (line.editor) cancelLineEdit(lines.value, line);
  editingIndex.value = null;
  calculatingLine.value = null;
};
const focusDraft = () => {
  const invalid = lines.value.find(line => line.editor && touched.value[lineKey(line)]?.length && Object.keys(errorsFor(line)).length);
  const line = invalid || lines.value.find(line => hasLineEdits([line])) || lines.value.find(line => line.editor);
  if (line) void (invalid ? focusInvalidEditor(line) : focusEditor(line));
};
defineExpose({ openCatalog: () => { showCatalog.value = !showCatalog.value; }, validateDrafts, commitDrafts, cancelDrafts, focusDraft });
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
watch(editingIndex, (index) => {
  const line = index === null ? null : lines.value[index];
  if (!line) return;
  if (!line.editor) {
    if (!line.title.trim() && !line.link_id) line.editor = { original: null };
    else beginLineEdit(line);
  }
  void focusEditor(line);
}, { flush: 'post', immediate: true });
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
  else { beginLineEdit(lines.value[index]!); editingIndex.value = index; }
};
const updatePreferredMode = (mode: ServiceDescriptionMode) => {
  descriptionMode.value = mode;
  emit('rememberDescriptionMode', mode);
};
</script>

<template>
  <section class="order-lines" :class="compact ? 'border-t border-slate-200 dark:border-slate-700' : 'mt-6'" aria-label="Услуги">
    <div v-if="!hideActions" class="mb-2"><h4 class="text-md font-semibold text-gray-800">Услуги</h4></div>
    <p v-if="servicesError" class="mb-2 text-xs text-red-300">{{ servicesError }}</p>
    <div class="space-y-2">
      <div v-for="(line, index) in lines" :key="lineKey(line)" :ref="element => { if (element) rows.set(lineKey(line), element as HTMLElement); else rows.delete(lineKey(line)); }" class="relative bg-white" :class="compact ? 'border-b border-gray-100 dark:border-slate-800 dark:bg-slate-950' : 'rounded-xl border border-gray-200 p-3 shadow-sm'">
        <template v-if="compact">
          <div v-if="(editingIndex === index || line.editor) && !line.installation_estimate_revision_id" class="p-3">
            <div class="mb-2 flex items-center justify-between gap-2"><p class="text-xs font-semibold text-slate-600 dark:text-slate-300">{{ line.editor?.original === null && !line.editor?.group ? 'Новая услуга' : 'Редактирование услуги' }}</p></div>
            <div class="order-line-form grid grid-cols-6 items-start gap-3">
              <div data-line-field class="relative min-w-0 space-y-1 col-span-full">
                <span class="flex min-h-6 items-center justify-between gap-2 px-1 text-xs font-medium text-gray-500">
                  <span>Название</span>
                  <ServiceDescriptionModeSwitch v-if="line.template_full_description" :model-value="line.description_mode || 'short'" @update:model-value="emit('descriptionMode', { index, mode: $event })" />
                </span>
                <OrderServiceTitleInput v-model="line.title" :invalid="Boolean(fieldError(line, 'title'))" :workflow="workflow" :autofocus="false" :suggestions="suggestedInstallations" @focus="emit('focus', index)" @input="emit('input', index)" @blur="touch(line, 'title'); emit('blur', index)" @select="(option, quantity) => emit('select', { index, option, quantity })" @add-suggested="emit('addSuggested', index)" />
                <p v-if="fieldError(line, 'title')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'title') }}</p>
              </div>
              <label class="col-span-3 min-w-0 space-y-1"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Цена</span><input :aria-invalid="Boolean(fieldError(line, 'price'))" @blur="touch(line, 'price')" v-model.number="line.price" type="number" min="0" step="0.01" class="field-input" placeholder="0" /><p v-if="fieldError(line, 'price')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'price') }}</p></label>
              <label class="col-span-3 min-w-0 space-y-1"><span class="flex h-auto items-center whitespace-nowrap px-1 text-xs font-medium text-gray-500 md:h-6 md:text-[11px]">Кол-во</span><input :aria-invalid="Boolean(fieldError(line, 'quantity'))" @blur="touch(line, 'quantity')" v-model.number="line.quantity" type="number" min="1" class="field-input" placeholder="1" /><p v-if="fieldError(line, 'quantity')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'quantity') }}</p></label>
              <label v-if="compactShowCosts" class="col-span-3 min-w-0 space-y-1"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Себест.</span><input :aria-invalid="Boolean(fieldError(line, 'cost'))" @blur="touch(line, 'cost')" v-model.number="line.cost" type="number" min="0" step="0.01" class="field-input" placeholder="0" /><p v-if="fieldError(line, 'cost')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'cost') }}</p></label>
              <div class="col-span-3 min-w-0 space-y-1"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Итого</span><div class="rounded-lg bg-gray-50 px-3 py-2"><p class="whitespace-nowrap text-base font-semibold leading-tight text-gray-900"><OrderMoney :value="lineTotal(line)" /></p></div></div>
              <label class="space-y-1 col-span-full"><span class="block text-xs font-medium text-gray-500">Описание для клиента</span><textarea :aria-invalid="Boolean(fieldError(line, 'description'))" @blur="touch(line, 'description')" v-model="line.description" data-testid="service-client-description" rows="2" maxlength="10000" class="field-input min-h-[64px] resize-y text-sm leading-relaxed [field-sizing:content]" placeholder="Состав работ и согласованные условия" /><p v-if="fieldError(line, 'description')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'description') }}</p></label>
              <div class="flex flex-wrap items-center justify-between gap-2 col-span-full"><button type="button" data-testid="service-open-calculator" class="min-h-8 text-xs text-brand-700" @click="calculatingLine = calculatingLine === line ? null : line">{{ calculatingLine === line ? 'Скрыть расчёт' : 'Рассчитать монтаж' }}</button></div>
              <OrderServiceInstallationCalculator v-if="calculatingLine === line" class="col-span-full" :initial-tariff="line.installation_standard" :quantity="line.quantity" @close="calculatingLine = null" @apply="applyCalculation(line, $event)" />
            </div>
            <OrderLineEditorActions
                class="-mx-3 -mb-3 mt-3"
                :commit-label="line.editor?.original === null && !line.editor?.group ? 'Добавить услугу' : 'Применить'"
                :remove-label="!line.editor?.group && line.editor?.original !== null ? `Удалить услугу #${index + 1}` : undefined"
                remove-usage="order_service_remove"
                @commit="finishEditing(line)" @cancel="cancelEditing(line)" @remove="emit('remove', index)"
              />
          </div>
          <div v-else class="divide-y divide-gray-100">
            <div v-for="(display, displayIndex) in displayLines(line)" :key="`compact-service-${index}-${displayIndex}`" class="order-line-row grid items-center gap-2 px-3 py-2.5" :class="{ 'has-costs': compactShowCosts }" :data-testid="`compact-service-row-${index}-${displayIndex}`">
              <div class="order-line-name min-w-0">
                <p class="break-words text-sm font-semibold leading-snug text-slate-900 dark:text-slate-100"><LineFormattedText :text="display.title || 'Новая услуга'" /></p>
                <p v-if="display.description" class="break-words text-xs font-normal leading-relaxed text-slate-500 dark:text-slate-400"><LineFormattedText :text="display.description" /></p>
                <span v-if="line.installation_estimate_revision_id" class="text-[11px] font-medium text-slate-500">По расчёту</span>
              </div>
              <span class="order-line-quantity text-xs text-slate-600 dark:text-slate-300"><span class="order-line-mobile-label mb-1 font-medium text-slate-500">Кол-во</span>{{ display.quantity }}</span>
              <span class="text-xs text-slate-600 dark:text-slate-300"><span class="order-line-mobile-label mb-1 font-medium text-slate-500">Цена</span><OrderMoney :value="display.price" /></span>
              <span class="text-xs font-semibold text-slate-900 dark:text-slate-100"><span class="order-line-mobile-label mb-1 font-medium text-slate-500">Итого</span><OrderMoney :value="display.quantity * display.price" /></span>
              <span v-if="compactShowCosts" class="order-line-cost text-xs text-slate-600 dark:text-slate-300"><span class="order-line-mobile-label mb-1 font-medium text-slate-500">Себест.</span><span v-if="line.installation_estimate_revision_id">—</span><OrderMoney v-else :value="line.cost" /></span>
              <div class="order-line-actions flex items-center justify-end gap-2">
                <button type="button" data-order-usage="order_service_edit" class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100 focus-visible:ring-2 focus-visible:ring-brand-500 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-300" :aria-label="`Редактировать услугу #${index + 1}.${displayIndex + 1}`" title="Редактировать услугу" @click="editLine(index, displayIndex)"><Pencil class="h-5 w-5 shrink-0" aria-hidden="true" /></button>
                <button type="button" data-order-usage="order_service_remove" class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 focus-visible:ring-2 focus-visible:ring-red-500 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400" :aria-label="`Удалить услугу #${index + 1}.${displayIndex + 1}`" title="Удалить услугу" @click="emit('remove', index, displayIndex)"><Trash2 class="h-5 w-5 shrink-0" aria-hidden="true" /></button>
              </div>
            </div>
          </div>
        </template>
        <template v-else>
        <div v-if="(editingIndex !== index && !line.editor) || line.installation_estimate_revision_id" class="flex min-w-0 items-start gap-3">
          <div class="min-w-0 flex-1">
            <div v-for="(display, displayIndex) in displayLines(line)" :key="displayIndex" :class="displayIndex ? 'mt-3' : ''">
            <p class="break-words text-sm font-semibold leading-snug text-slate-900 dark:text-slate-100"><LineFormattedText :text="display.title || 'Новая услуга'" /></p>
            <p v-if="display.description" class="mt-1 break-words text-xs font-normal leading-relaxed text-slate-500"><LineFormattedText :text="display.description" /></p>
            <div class="mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
              <span>{{ display.quantity }} × <OrderMoney :value="display.price" /> <span v-if="line.installation_estimate_revision_id" class="ml-1 text-slate-500">По расчёту</span></span>
              <span class="font-semibold text-slate-800 dark:text-slate-200"><OrderMoney :value="display.quantity * display.price" /></span>
            </div>
            <div class="mt-1 flex gap-1"><button type="button" data-order-usage="order_service_edit" class="btn-mini-outline h-8 text-xs" @click="editLine(index, displayIndex)">Редактировать</button><button type="button" data-order-usage="order_service_remove" class="h-8 px-2 text-xs text-red-600" @click="emit('remove', index, displayIndex)">Удалить</button></div>
            </div>
          </div>
        </div>
        <div v-else>
        <div class="order-line-form grid grid-cols-6 items-start gap-3">
          <div data-line-field class="relative min-w-0 space-y-1 col-span-full">
            <span class="flex min-h-6 items-center justify-between gap-2 px-1 text-xs font-medium text-gray-500">
              <span>Название</span>
              <ServiceDescriptionModeSwitch v-if="line.template_full_description" :model-value="line.description_mode || 'short'" @update:model-value="emit('descriptionMode', { index, mode: $event })" />
            </span>
            <OrderServiceTitleInput v-model="line.title" :invalid="Boolean(fieldError(line, 'title'))" :workflow="workflow" :autofocus="false" :suggestions="suggestedInstallations" @focus="emit('focus', index)" @input="emit('input', index)" @blur="touch(line, 'title'); emit('blur', index)" @select="(option, quantity) => emit('select', { index, option, quantity })" @add-suggested="emit('addSuggested', index)" />
                <p v-if="fieldError(line, 'title')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'title') }}</p>
          </div>
          <label class="col-span-3 min-w-0 space-y-1"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Цена</span><input :aria-invalid="Boolean(fieldError(line, 'price'))" @blur="touch(line, 'price')" v-model.number="line.price" type="number" min="0" step="0.01" class="field-input" placeholder="0" /><p v-if="fieldError(line, 'price')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'price') }}</p></label>
          <label class="col-span-3 min-w-0 space-y-1"><span class="flex h-auto items-center whitespace-nowrap px-1 text-xs font-medium text-gray-500 md:h-6 md:text-[11px]">Кол-во</span><input :aria-invalid="Boolean(fieldError(line, 'quantity'))" @blur="touch(line, 'quantity')" v-model.number="line.quantity" type="number" min="1" class="field-input" placeholder="1" /><p v-if="fieldError(line, 'quantity')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'quantity') }}</p></label>
          <label v-if="!demoReadOnly" class="col-span-3 min-w-0 space-y-1"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Себест.</span><input :aria-invalid="Boolean(fieldError(line, 'cost'))" @blur="touch(line, 'cost')" v-model.number="line.cost" type="number" min="0" step="0.01" class="field-input" placeholder="0" /><p v-if="fieldError(line, 'cost')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'cost') }}</p></label>
          <div class="col-span-3 min-w-0 space-y-1"><span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Итого</span><div class="rounded-lg bg-gray-50 px-3 py-2"><p class="whitespace-nowrap text-base font-semibold leading-tight text-gray-900"><OrderMoney :value="lineTotal(line)" /></p></div></div>
          <label class="space-y-1 col-span-full"><span class="block text-xs font-medium text-gray-500">Описание для клиента</span><textarea :aria-invalid="Boolean(fieldError(line, 'description'))" @blur="touch(line, 'description')" v-model="line.description" data-testid="service-client-description" rows="2" maxlength="10000" class="field-input min-h-[64px] resize-y text-sm leading-relaxed [field-sizing:content]" placeholder="Состав работ и согласованные условия" /><p v-if="fieldError(line, 'description')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'description') }}</p></label>
          <div class="flex flex-wrap items-center justify-between gap-2 col-span-full"><button type="button" data-testid="service-open-calculator" class="min-h-8 text-xs text-brand-700" @click="calculatingLine = calculatingLine === line ? null : line">{{ calculatingLine === line ? 'Скрыть расчёт' : 'Рассчитать монтаж' }}</button></div>
          <OrderServiceInstallationCalculator v-if="calculatingLine === line" class="col-span-full" :initial-tariff="line.installation_standard" :quantity="line.quantity" @close="calculatingLine = null" @apply="applyCalculation(line, $event)" />
        </div>
        <OrderLineEditorActions
                class="-mx-3 -mb-3 mt-3"
                :commit-label="line.editor?.original === null && !line.editor?.group ? 'Добавить услугу' : 'Применить'"
                :remove-label="!line.editor?.group && line.editor?.original !== null ? `Удалить услугу #${index + 1}` : undefined"
                remove-usage="order_service_remove"
                @commit="finishEditing(line)" @cancel="cancelEditing(line)" @remove="emit('remove', index)"
              />
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

<style scoped>
.order-lines { container-type: inline-size; }
.order-line-row { grid-template-columns: var(--line-columns, repeat(3, minmax(0, 1fr))); }
.order-line-row > * { text-align: var(--line-align, left); }
.order-line-row > .order-line-name { grid-column: var(--line-name-column, span 3 / span 3); text-align: left; }
.order-line-row > .order-line-quantity { text-align: var(--line-quantity-align, left); }
.order-line-cost { grid-column: var(--line-cost-column, span 2 / span 2); }
.order-line-mobile-label { display: var(--line-label-display, block); }
.order-line-actions { grid-column: var(--line-actions-column, span 3 / span 3); flex-direction: var(--line-actions-direction, row); }
.has-costs .order-line-actions { grid-column: var(--line-actions-column, auto); }
@container (min-width: 650px) {
  .order-line-form { grid-template-columns: repeat(12, minmax(0, 1fr)); }
  .order-line-row:not(.has-costs) {
    --line-columns: minmax(0, 1fr) 3.5rem 6rem 6.5rem 3rem;
    --line-name-column: auto;
    --line-actions-column: auto;
    --line-label-display: none;
    --line-align: right;
    --line-quantity-align: center;
    --line-actions-direction: column;
  }
}
@container (min-width: 750px) {
  .order-line-row.has-costs {
    --line-columns: minmax(0, 1fr) 3.5rem 6rem 6.5rem 6rem 3rem;
    --line-name-column: auto;
    --line-actions-column: auto;
    --line-cost-column: auto;
    --line-label-display: none;
    --line-align: right;
    --line-quantity-align: center;
    --line-actions-direction: column;
  }
}
</style>
