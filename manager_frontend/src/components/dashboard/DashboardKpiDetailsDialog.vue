<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { ChevronRight, Loader2, X } from 'lucide-vue-next';
import type { DashboardDetailItem, DashboardDetailResponse, DashboardPeriodRange } from '../../client';
import { useDialogA11y } from '../../composables/useDialogA11y';
import { useDocumentScrollLock } from '../../composables/useDocumentScrollLock';
import { getDashboardDetails } from '../../services/dashboard-details-api';
import { dashboardKpiLabels, formatDashboardNumber, formatDashboardUpdatedAt, formatPeriodRange, type DashboardKpiKey } from '../../services/dashboard-overview';
import { getApiErrorMessage } from '../../utils/api-errors';
import MoneyAmount from '../money/MoneyAmount.vue';

const props = defineProps<{ metric: DashboardKpiKey; period: DashboardPeriodRange }>();
const emit = defineEmits<{ close: [] }>();
const dialogRef = ref<HTMLElement | null>(null);
const open = ref(true);
const data = ref<DashboardDetailResponse | null>(null);
const loading = ref(false);
const error = ref('');
let generation = 0;
const snapshot = props.metric === 'active_tasks' || props.metric === 'receivables';
const explanations: Record<DashboardKpiKey, string> = {
  revenue: 'Оплаты в BYN по финансово подтверждённым заказам, по дате платежа.',
  sales: 'Успешно закрытые заказы, по дате закрытия.',
  receivables: 'Положительный остаток к оплате в BYN по подтверждённым заказам. Срок оплаты может ещё не наступить.',
  new_leads: 'Входящие обращения, созданные за этот период, включая уже обработанные.',
  installations: 'Завершённые этапы «Монтаж». Если дата завершения не записана, используется дата изменения заказа.',
  active_tasks: 'Касания по открытым заказам и активным входящим, для которых назначена дата связи.',
};
const load = async (offset = 0) => {
  const current = ++generation;
  loading.value = true; error.value = '';
  try {
    const result = await getDashboardDetails(props.metric, props.period, offset);
    if (generation === current) data.value = result;
  } catch (caught) {
    if (generation === current) { data.value = null; error.value = getApiErrorMessage(caught); }
  } finally { if (generation === current) loading.value = false; }
};
const href = (item: DashboardDetailItem) => item.entity_type === 'lead'
  ? `/manager/leads?incomingId=${item.entity_id}`
  : `/manager/orders/${item.entity_id}?returnTo=${encodeURIComponent('/manager')}`;
const sourceLabel = (item: DashboardDetailItem) => `${item.entity_type === 'lead' ? 'Входящее' : 'Заказ'} #${item.entity_id}`;
useDialogA11y({ open, dialogRef, close: () => emit('close') });
useDocumentScrollLock(() => open.value);
onMounted(() => { void load(); });
onBeforeUnmount(() => { generation++; open.value = false; });
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-[70] flex justify-end bg-slate-950/40" @click.self="emit('close')">
      <section ref="dialogRef" role="dialog" aria-modal="true" aria-labelledby="dashboard-detail-title" tabindex="-1" class="flex h-full w-full max-w-xl flex-col bg-[var(--kitlane-surface)] text-[var(--kitlane-text)] shadow-xl">
        <header class="shrink-0 border-b border-[var(--kitlane-border)] p-4 sm:p-5">
          <div class="flex items-start justify-between gap-3"><h2 id="dashboard-detail-title" class="text-xl font-semibold">{{ dashboardKpiLabels[metric] }}</h2><button type="button" aria-label="Закрыть детализацию" class="rounded-lg p-2 hover:bg-[var(--kitlane-accent-soft)]" @click="emit('close')"><X class="h-5 w-5" /></button></div>
          <p class="mt-1 text-sm text-[var(--kitlane-muted)]">{{ snapshot ? 'Срез на сейчас' : formatPeriodRange(period.start, period.end) }}</p>
          <p class="mt-3 text-sm text-[var(--kitlane-muted)]">{{ explanations[metric] }}</p>
        </header>
        <div class="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5" :aria-busy="loading">
          <div v-if="loading" class="flex justify-center py-8" role="status"><Loader2 class="h-6 w-6 animate-spin" /><span class="sr-only">Загрузка записей</span></div>
          <div v-else-if="error" role="alert"><p>{{ error }}</p><button type="button" class="mt-3 font-semibold text-[var(--kitlane-accent-text)]" @click="load()">Повторить</button></div>
          <template v-else-if="data">
            <div class="mb-4"><p class="text-2xl font-bold"><MoneyAmount v-if="data.unit === 'byn'" :value="data.value" /><template v-else>{{ formatDashboardNumber(data.value) }}</template></p><p class="mt-1 text-xs text-[var(--kitlane-muted)]">Проверено: {{ formatDashboardUpdatedAt(data.generated_at) }} · Записей: {{ data.total }}</p></div>
            <p v-if="!data.items.length" class="py-6 text-center text-[var(--kitlane-muted)]">Записей нет.</p>
            <ul v-else class="divide-y divide-[var(--kitlane-border)]">
              <li v-for="item in data.items" :key="`${item.entity_type}-${item.record_id}`">
                <a :href="href(item)" class="flex items-center gap-3 rounded-lg py-4 hover:bg-[var(--kitlane-accent-soft)]">
                  <span class="min-w-0 flex-1"><strong class="block text-sm text-[var(--kitlane-accent-text)]">{{ sourceLabel(item) }}</strong><span v-if="item.title" class="mt-1 block break-words text-sm">{{ item.title }}</span><span v-if="item.occurred_at" class="mt-1 block text-xs text-[var(--kitlane-muted)]"><template v-if="metric === 'revenue'">Платёж #{{ item.record_id }} · </template><template v-if="metric === 'installations'">Этап #{{ item.record_id }} · </template>{{ formatDashboardUpdatedAt(item.occurred_at) }}</span></span>
                  <MoneyAmount v-if="item.amount != null" :value="item.amount" class="shrink-0 text-sm font-semibold" /><ChevronRight class="h-4 w-4 shrink-0 text-[var(--kitlane-muted)]" />
                </a>
              </li>
            </ul>
          </template>
        </div>
        <footer v-if="data && data.total > data.limit" class="flex shrink-0 items-center justify-between gap-2 border-t border-[var(--kitlane-border)] p-4">
          <button type="button" :disabled="loading || data.offset === 0" class="rounded-lg border border-[var(--kitlane-control-border)] px-3 py-2 text-sm disabled:opacity-40" @click="load(Math.max(0, data.offset - data.limit))">Назад</button><span class="text-xs text-[var(--kitlane-muted)]">{{ data.offset + 1 }}–{{ data.offset + data.items.length }} из {{ data.total }}</span><button type="button" :disabled="loading || data.offset + data.limit >= data.total" class="rounded-lg border border-[var(--kitlane-control-border)] px-3 py-2 text-sm disabled:opacity-40" @click="load(data.offset + data.limit)">Далее</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
