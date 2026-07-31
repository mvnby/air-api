<script setup lang="ts">
import { computed } from 'vue';
import type { ManagerInstallerResponse } from '../../client';
import DateTimeField from '../ui/DateTimeField.vue';
import OrderDrawerSection from './OrderDrawerSection.vue';
import { NEGOTIATION_STATUS_OPTIONS } from './order-utils';
import { buildMeasurementSummary, type OrderWorkflowType } from './order-workspace';

const props = defineProps<{
  workflowType: OrderWorkflowType;
  executorOptions: ManagerInstallerResponse[];
  customerBranchId: number | null;
  newBranchAddress: string;
  measurementError?: string;
  installationError?: string;
}>();

const measurementRequired = defineModel<boolean>('measurementRequired', { required: true });
const assessmentDate = defineModel<string>('assessmentDate', { required: true });
const negotiationStatus = defineModel<string>('negotiationStatus', { required: true });
const autoExecutionOnPayment = defineModel<boolean>('autoExecutionOnPayment', { required: true });
const detailsExpanded = defineModel<boolean>('detailsExpanded', { required: true });
const measurerId = defineModel<number | null>('measurerId', { required: true });
const measurementResult = defineModel<string>('measurementResult', { required: true });
const installationDate = defineModel<string>('installationDate', { required: true });
const installerId = defineModel<number | null>('installerId', { required: true });

const isRepairWorkflow = computed(() => props.workflowType === 'repair');
const title = computed(() => {
  if (props.workflowType === 'repair') return 'Диагностика и выезд';
  if (props.workflowType === 'maintenance') return 'Планирование обслуживания';
  if (props.workflowType === 'service_work') return 'Планирование работ';
  return 'Планирование';
});
const workDateLabel = computed(() => {
  if (props.workflowType === 'repair') return 'Дата диагностики / ремонта';
  if (props.workflowType === 'maintenance') return 'Дата обслуживания';
  if (props.workflowType === 'service_work') return 'Дата работ';
  return 'Дата монтажа';
});

const formatDateTime = (value?: string | null) => {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const summary = computed(() => {
  const parts = [buildMeasurementSummary({
    required: measurementRequired.value,
    date: assessmentDate.value,
    result: measurementResult.value,
    kind: isRepairWorkflow.value ? 'diagnostic' : 'measurement',
    formatDate: formatDateTime,
  })];
  if (installationDate.value) {
    parts.push(`${workDateLabel.value.toLowerCase()} ${formatDateTime(installationDate.value)}`);
  }
  return parts.join(' · ');
});

const detailsSummary = computed(() => {
  const parts: string[] = [];
  if (measurerId.value) parts.push('замерщик назначен');
  if (measurementResult.value.trim()) parts.push('есть результат замера');
  if (props.customerBranchId) parts.push('выбран филиал');
  if (props.newBranchAddress.trim()) parts.push('готовится новый филиал');
  return parts.join(' · ') || 'дополнительные поля не заполнены';
});
</script>

<template>
  <section id="order-workspace-planning" class="mt-4 rounded-2xl border border-blue-100 bg-blue-50/30 p-3 dark:border-blue-500/30 dark:bg-blue-500/10">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="min-w-0">
        <h3 class="text-sm font-semibold text-blue-900 dark:text-blue-100">{{ title }}</h3>
        <p class="mt-0.5 truncate text-xs text-blue-700/70 dark:text-blue-200/70">{{ summary }}</p>
      </div>
      <button
        v-if="!measurementRequired"
        type="button"
        data-testid="enable-measurement"
        class="btn-mini-outline justify-center whitespace-nowrap text-xs"
        @click="measurementRequired = true"
      >
        <span class="material-icons-round text-[15px]">add_location_alt</span>
        {{ isRepairWorkflow ? 'Назначить диагностику' : 'Назначить замер' }}
      </button>
      <label v-else class="inline-flex items-center gap-2 rounded-xl bg-white px-3 py-2 text-xs font-medium text-blue-900 ring-1 ring-blue-100 dark:bg-slate-900 dark:text-blue-100 dark:ring-blue-500/30">
        <input v-model="measurementRequired" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
        {{ isRepairWorkflow ? 'Диагностика нужна' : 'Замер нужен' }}
      </label>
    </div>

    <div class="mt-3 rounded-xl border border-blue-100 bg-white p-3 shadow-sm dark:border-blue-500/30 dark:bg-slate-900">
      <label class="block">
        <span class="text-xs font-semibold uppercase tracking-[0.12em] text-blue-900/70 dark:text-blue-200/80">Состояние переговоров</span>
        <select v-model="negotiationStatus" data-testid="negotiation-status" class="field-input mt-2 bg-white dark:bg-slate-950">
          <option v-for="option in NEGOTIATION_STATUS_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
      <label class="mt-3 flex items-start gap-2 rounded-xl border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-100">
        <input v-model="autoExecutionOnPayment" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
        <span>
          <span class="block font-semibold">После полной оплаты автоматически перевести заказ в этап «Работы»</span>
          <span class="mt-0.5 block text-emerald-700/80 dark:text-emerald-200/70">Сработает автоматически, когда долг по заказу станет нулевым.</span>
        </span>
      </label>
    </div>

    <div v-if="measurementRequired" class="mt-3 rounded-xl border border-blue-100 bg-white p-3 shadow-sm dark:border-blue-500/30 dark:bg-slate-900">
      <DateTimeField v-model="assessmentDate" :label="isRepairWorkflow ? 'Дата и время диагностики' : 'Дата и время замера'" :error="measurementError" />
    </div>

    <OrderDrawerSection
      v-model:expanded="detailsExpanded"
      :title="isRepairWorkflow ? 'Детали диагностики и ремонта' : 'Детали выезда и монтажа'"
      :summary="detailsSummary"
      tone="blue"
      :has-error="Boolean(measurementError || installationError)"
    >
      <div class="grid gap-3 md:grid-cols-2">
        <template v-if="measurementRequired">
          <label class="field-label">
            {{ isRepairWorkflow ? 'Специалист' : 'Замерщик' }}
            <select v-model="measurerId" data-testid="measurer" class="field-input">
              <option :value="null">Не назначен</option>
              <option v-for="installer in executorOptions" :key="installer.id" :value="installer.id">
                {{ installer.name }} {{ !installer.is_active ? '(в архиве)' : '' }}
              </option>
            </select>
          </label>
          <label class="field-label md:col-span-2">
            Результат замера
            <textarea
              v-model="measurementResult"
              class="field-input min-h-[60px]"
              :placeholder="isRepairWorkflow ? 'Краткий результат диагностики...' : 'Резюме после выезда (длины трасс, доп. работы)...'"
            />
          </label>
        </template>
        <DateTimeField v-model="installationDate" :label="workDateLabel" :error="installationError" />
        <label class="field-label">
          {{ isRepairWorkflow ? 'Исполнитель ремонта' : 'Монтажник' }}
          <select v-model="installerId" data-testid="installer" class="field-input">
            <option :value="null">Не назначен</option>
            <option v-for="installer in executorOptions" :key="installer.id" :value="installer.id">
              {{ installer.name }} {{ !installer.is_active ? '(в архиве)' : '' }}
            </option>
          </select>
        </label>
      </div>
    </OrderDrawerSection>
  </section>
</template>
