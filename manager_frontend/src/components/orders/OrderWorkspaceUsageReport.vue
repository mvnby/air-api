<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { BarChart3, X } from 'lucide-vue-next';
import { getApiErrorMessage } from '../../utils/api-errors';
import {
  type OrderWorkspaceUsageParty,
  type OrderWorkspaceUsageReport,
  type OrderWorkspaceUsageReportItem,
  type OrderWorkspaceUsageViewport,
  type OrderWorkspaceUsageWorkflow,
  orderWorkspaceUsageApi,
} from '../../services/order-workspace-usage-api';
import { managerSession } from '../../services/manager-session';
import { managerStorefrontSelection } from '../../services/manager-storefront-selection';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../../manager-capabilities';
import { useDrawerFocusTrap } from '../../composables/useDrawerFocusTrap';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();
const dialog = ref<HTMLElement | null>(null);
const { captureFocus, focusContainer, restoreFocus, trapFocus } = useDrawerFocusTrap(dialog);

const days = ref<7 | 30 | 90>(30);
const workflow = ref<OrderWorkspaceUsageWorkflow | ''>('');
const partyKind = ref<OrderWorkspaceUsageParty | ''>('');
const viewport = ref<OrderWorkspaceUsageViewport | ''>('');
const loading = ref(false);
const error = ref('');
const report = ref<OrderWorkspaceUsageReport | null>(null);
let pendingRequest: ReturnType<typeof orderWorkspaceUsageApi.daily> | null = null;
const reportScope = computed(() => {
  const auth = managerSession.auth.value;
  const storefront = managerStorefrontSelection.selectedSlug.value;
  if (!managerSession.isAuthenticated.value || !auth || !storefront) return '';
  return `${auth.tenant_id}:${auth.staff_user_id || auth.username}:${storefront}`;
});
const canViewReport = computed(() => hasManagerCapability(
  managerSession.auth.value,
  MANAGER_CAPABILITY.analyticsManage,
));

const metricLabels: Record<OrderWorkspaceUsageReportItem['metric'], string> = {
  order_open: 'Открытие заказа', proposal_open: 'Предложение', documents_open: 'Документы', work_open: 'Работы', payments_open: 'Оплаты',
  customer_open: 'Клиент', object_edit: 'Объект', equipment_open: 'Оборудование', attachments_open: 'Вложения',
  product_add: 'Добавление товара', product_select: 'Выбор товара', product_description_edit: 'Описание товара', product_remove: 'Удаление товара',
  service_add: 'Добавление услуги', service_edit: 'Изменение услуги', service_remove: 'Удаление услуги', scenario_change: 'Смена сценария',
  autosave_toggle: 'Автосохранение', document_create: 'Создание документа', payment_add: 'Добавление оплаты',
};
const componentMetrics = new Set(['order_open', 'proposal_open', 'documents_open', 'work_open', 'payments_open', 'customer_open', 'equipment_open', 'attachments_open']);
const total = computed(() => report.value?.items.reduce((sum, item) => sum + item.count, 0) || 0);
const groupedItems = computed(() => {
  const items = report.value?.items || [];
  const groups = new Map<string, { day: string; opens: number; actions: number }>();
  for (const item of items) {
    const group = groups.get(item.day) || { day: item.day, opens: 0, actions: 0 };
    if (componentMetrics.has(item.metric)) group.opens += item.count;
    else group.actions += item.count;
    groups.set(item.day, group);
  }
  return [...groups.values()].sort((left, right) => left.day.localeCompare(right.day));
});
const maxDaily = computed(() => Math.max(1, ...groupedItems.value.flatMap(item => [item.opens, item.actions])));
const metricTotals = computed(() => {
  const totals = new Map<OrderWorkspaceUsageReportItem['metric'], number>();
  for (const item of report.value?.items || []) totals.set(item.metric, (totals.get(item.metric) || 0) + item.count);
  return [...totals.entries()]
    .map(([metric, count]) => ({ metric, count }))
    .sort((left, right) => right.count - left.count);
});
const maxMetric = computed(() => Math.max(1, ...metricTotals.value.map(item => item.count)));

const load = async () => {
  pendingRequest?.cancel();
  pendingRequest = null;
  if (!props.open || !reportScope.value || !canViewReport.value) {
    report.value = null;
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = '';
  const request = orderWorkspaceUsageApi.daily({
    days: days.value,
    workflow: workflow.value || undefined,
    party_kind: partyKind.value || undefined,
    viewport: viewport.value || undefined,
  });
  const requestScope = reportScope.value;
  pendingRequest = request;
  try {
    const response = await request;
    if (pendingRequest === request && props.open && requestScope === reportScope.value) report.value = response;
  } catch (requestError) {
    if (pendingRequest === request && !request.isCancelled) error.value = getApiErrorMessage(requestError) || 'Не удалось загрузить статистику';
  } finally {
    if (pendingRequest === request) {
      pendingRequest = null;
      loading.value = false;
    }
  }
};

watch(() => props.open, async (open) => {
  if (open) {
    captureFocus();
    void load();
    await nextTick();
    if (props.open) focusContainer();
  } else {
    pendingRequest?.cancel();
    pendingRequest = null;
    report.value = null;
    await nextTick();
    restoreFocus();
  }
}, { immediate: true });
watch([days, workflow, partyKind, viewport], () => {
  if (props.open) void load();
});
watch(reportScope, () => {
  pendingRequest?.cancel();
  pendingRequest = null;
  report.value = null;
  error.value = '';
  if (props.open) void load();
}, { flush: 'sync' });
watch(canViewReport, (allowed) => {
  if (!allowed && props.open) emit('close');
}, { flush: 'sync' });
onBeforeUnmount(() => pendingRequest?.cancel());
</script>

<template>
  <div v-if="open" ref="dialog" tabindex="-1" class="fixed inset-0 z-[70] overflow-y-auto bg-white p-4 outline-none dark:bg-slate-950 sm:p-6" role="dialog" aria-modal="true" aria-label="Отчёт по использованию" @keydown.stop="trapFocus" @keydown.esc.stop="emit('close')">
    <div class="mx-auto max-w-3xl">
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="flex items-center gap-2 text-slate-900 dark:text-white"><BarChart3 :size="20" aria-hidden="true" /><h2 class="text-lg font-semibold">Использование рабочей области</h2></div>
          <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">Только агрегированные действия без данных заказа или клиента.</p>
        </div>
        <button type="button" class="btn-mini-outline h-9 w-9 justify-center p-0" aria-label="Закрыть отчёт" @click="emit('close')"><X :size="17" /></button>
      </div>

      <div class="mt-5 grid gap-3 sm:grid-cols-4">
        <label class="field-label">Период<select v-model="days" class="field-input mt-1"><option :value="7">7 дней</option><option :value="30">30 дней</option><option :value="90">90 дней</option></select></label>
        <label class="field-label">Сценарий<select v-model="workflow" class="field-input mt-1"><option value="">Все</option><option value="sales_installation">Продажа с монтажом</option><option value="work">Работы</option><option value="maintenance">Обслуживание</option><option value="repair">Ремонт</option></select></label>
        <label class="field-label">Клиент<select v-model="partyKind" class="field-input mt-1"><option value="">Все</option><option value="company">Юрлицо</option><option value="individual">Физлицо</option><option value="individual_entrepreneur">ИП</option><option value="unknown">Не указан</option></select></label>
        <label class="field-label">Экран<select v-model="viewport" class="field-input mt-1"><option value="">Все</option><option value="desktop">Компьютер</option><option value="tablet">Планшет</option><option value="mobile">Телефон</option></select></label>
      </div>

      <p v-if="loading" class="mt-6 text-sm text-slate-500">Загружаем статистику…</p>
      <p v-else-if="error" class="mt-6 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      <template v-else-if="report">
        <div class="mt-6 flex flex-wrap items-baseline gap-x-3 gap-y-1"><strong class="text-2xl text-slate-900 dark:text-white">{{ total }}</strong><span class="text-sm text-slate-500">действий с {{ report.since }} по {{ report.through }} · {{ report.timezone }}</span></div>
        <div v-if="groupedItems.length" class="mt-4 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
          <div v-for="item in groupedItems" :key="item.day" class="grid grid-cols-[5.5rem_1fr_1fr] gap-2 border-b border-slate-100 px-3 py-2 text-xs last:border-0 dark:border-slate-800">
            <span class="text-slate-500">{{ item.day }}</span>
            <span class="rounded px-2 py-1 text-center text-slate-700 dark:text-slate-200" :style="{ backgroundColor: `rgb(13 148 136 / ${0.06 + 0.24 * item.opens / maxDaily})` }">Открытия {{ item.opens }}</span>
            <span class="rounded px-2 py-1 text-center text-slate-700 dark:text-slate-200" :style="{ backgroundColor: `rgb(59 130 246 / ${0.06 + 0.24 * item.actions / maxDaily})` }">Действия {{ item.actions }}</span>
          </div>
        </div>
        <p v-else class="mt-6 rounded-xl border border-dashed border-slate-300 p-5 text-sm text-slate-500 dark:border-slate-700">За выбранный период действий пока нет.</p>
        <div v-if="metricTotals.length" class="mt-6">
          <h3 class="text-sm font-semibold text-slate-900 dark:text-white">По действиям</h3>
          <div class="mt-2 space-y-2">
            <div v-for="item in metricTotals" :key="item.metric" class="grid grid-cols-[minmax(0,1fr)_3rem] items-center gap-3 text-xs">
              <div class="min-w-0"><div class="mb-1 flex justify-between gap-2"><span class="truncate text-slate-700 dark:text-slate-200">{{ metricLabels[item.metric] }}</span><span class="text-slate-500">{{ item.count }}</span></div><div class="h-1.5 overflow-hidden rounded bg-slate-100 dark:bg-slate-800"><div class="h-full rounded bg-teal-600" :style="{ width: `${Math.max(4, item.count / maxMetric * 100)}%` }" /></div></div>
              <span class="text-right text-slate-500">{{ componentMetrics.has(item.metric) ? 'раздел' : 'действие' }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
