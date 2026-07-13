<script setup lang="ts">
import { ref } from 'vue';
import { CircleAlert, ExternalLink, LoaderCircle, ShieldCheck } from 'lucide-vue-next';
import {
  ManagerWarrantiesService,
  type ManagerEquipmentLinkedOrderResponse,
  type ManagerEquipmentWarrantyCoverageResponse,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{
  coverages: ManagerEquipmentWarrantyCoverageResponse[];
  linkedOrders: ManagerEquipmentLinkedOrderResponse[];
}>();

const emit = defineEmits<{
  updated: [coverage: ManagerEquipmentWarrantyCoverageResponse];
}>();

const decisionCoverageId = ref<number | null>(null);
const decisionAction = ref<'voided' | 'restored'>('voided');
const decisionReason = ref('');
const saving = ref(false);
const error = ref('');

const coverageTitle = (type: string) => ({
  supplier: 'Гарантия оборудования',
  mvn_work: 'Гарантия MVN на работы',
  legacy: 'Ранее указанная гарантия',
}[type] || 'Гарантийное покрытие');
const orderRoleLabel = (role: string) => ({
  sale: 'Продажа',
  installation: 'Монтаж',
  maintenance: 'ТО',
  repair: 'Ремонт',
  diagnostic: 'Диагностика',
  warranty_case: 'Гарантийный случай',
  other: 'Связанный заказ',
}[role] || role);
const statusLabel = (coverage: ManagerEquipmentWarrantyCoverageResponse) => {
  if (coverage.decision_status === 'voided') return 'Снята решением менеджера';
  if (coverage.time_status === 'expired') return 'Срок истёк';
  if (coverage.maintenance_status === 'overdue') return 'ТО просрочено';
  if (coverage.maintenance_status === 'due_soon') return 'ТО скоро';
  if (coverage.time_status === 'active') return 'Действует';
  return 'Нужно уточнить';
};
const statusClass = (coverage: ManagerEquipmentWarrantyCoverageResponse) => {
  if (coverage.decision_status === 'voided' || coverage.time_status === 'expired' || coverage.maintenance_status === 'overdue') {
    return 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-200';
  }
  if (coverage.maintenance_status === 'due_soon' || coverage.time_status === 'unknown') {
    return 'bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200';
  }
  return 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200';
};
const formatDate = (value?: string | null) => value ? new Date(value).toLocaleDateString('ru-RU') : 'не указана';

const beginDecision = (coverage: ManagerEquipmentWarrantyCoverageResponse, action: 'voided' | 'restored') => {
  decisionCoverageId.value = coverage.id;
  decisionAction.value = action;
  decisionReason.value = '';
  error.value = '';
};

const saveDecision = async () => {
  if (!decisionCoverageId.value || !decisionReason.value.trim() || saving.value) return;
  saving.value = true;
  error.value = '';
  try {
    const updated = await ManagerWarrantiesService.decideManagerWarrantyCoverage(decisionCoverageId.value, {
      action: decisionAction.value,
      reason: decisionReason.value.trim(),
    });
    emit('updated', updated);
    decisionCoverageId.value = null;
    decisionReason.value = '';
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <div class="mt-4 grid gap-3 xl:grid-cols-2">
    <section class="rounded-xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-3">
      <div class="flex items-center gap-2">
        <ShieldCheck class="h-4 w-4 text-teal-500" />
        <h3 class="text-sm font-semibold text-[var(--mv-text)]">Гарантийные покрытия</h3>
      </div>

      <p v-if="!coverages.length" class="mt-3 text-sm text-amber-700 dark:text-amber-200">Гарантийные условия нужно уточнить.</p>
      <article v-for="coverage in coverages" :key="coverage.id" class="mt-3 rounded-lg border border-[var(--mv-border)] bg-[var(--mv-surface)] p-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <p class="text-sm font-semibold text-[var(--mv-text)]">{{ coverageTitle(coverage.coverage_type) }}</p>
          <span class="rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="statusClass(coverage)">{{ statusLabel(coverage) }}</span>
        </div>
        <p class="mt-2 text-xs text-[var(--mv-text-muted)]">
          {{ formatDate(coverage.starts_at) }} — {{ formatDate(coverage.expires_at) }}
        </p>
        <p v-if="coverage.maintenance_required" class="mt-1 text-xs text-[var(--mv-text-muted)]">
          ТО обязательно<span v-if="coverage.maintenance_interval_months"> каждые {{ coverage.maintenance_interval_months }} мес.</span>
          <span v-if="coverage.next_maintenance_due_at"> · следующее {{ formatDate(coverage.next_maintenance_due_at) }}</span>
        </p>
        <p v-if="coverage.terms_snapshot" class="mt-2 break-words text-xs text-[var(--mv-text-muted)]">{{ coverage.terms_snapshot }}</p>

        <div class="mt-2 flex flex-wrap gap-2">
          <button v-if="coverage.decision_status !== 'voided'" type="button" class="btn-mini-outline text-xs text-red-700 dark:text-red-200" @click="beginDecision(coverage, 'voided')">Снять с гарантии</button>
          <button v-else type="button" class="btn-mini-outline text-xs" @click="beginDecision(coverage, 'restored')">Восстановить</button>
        </div>

        <form v-if="decisionCoverageId === coverage.id" class="mt-3 rounded-lg border border-[var(--mv-border)] p-2" @submit.prevent="saveDecision">
          <label class="field-label">
            Причина решения
            <textarea v-model="decisionReason" class="field-input min-h-16" required placeholder="Почему гарантия снята или восстановлена" />
          </label>
          <p v-if="error" class="mt-2 flex items-start gap-1 text-xs text-red-700 dark:text-red-200"><CircleAlert class="h-4 w-4 shrink-0" />{{ error }}</p>
          <div class="mt-2 flex justify-end gap-2">
            <button type="button" class="btn-mini-outline text-xs" :disabled="saving" @click="decisionCoverageId = null">Отмена</button>
            <button type="submit" class="btn-mini text-xs" :disabled="saving || !decisionReason.trim()">
              <LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" />
              Подтвердить
            </button>
          </div>
        </form>
      </article>
    </section>

    <section class="rounded-xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-3">
      <h3 class="text-sm font-semibold text-[var(--mv-text)]">Связанные заказы</h3>
      <p v-if="!linkedOrders.length" class="mt-3 text-sm text-[var(--mv-text-muted)]">Заказы пока не связаны.</p>
      <a
        v-for="order in linkedOrders"
        :key="`${order.order_id}-${order.role}`"
        :href="`/manager/orders/kanban?orderId=${order.order_id}`"
        class="mt-2 flex items-center gap-2 rounded-lg border border-[var(--mv-border)] bg-[var(--mv-surface)] px-3 py-2 text-sm hover:border-teal-500"
      >
        <span class="min-w-0 flex-1">
          <span class="block truncate font-semibold text-[var(--mv-text)]">#{{ order.order_id }} · {{ order.title }}</span>
          <span class="block text-xs text-[var(--mv-text-muted)]">{{ orderRoleLabel(order.role) }}</span>
        </span>
        <ExternalLink class="h-4 w-4 shrink-0 text-[var(--mv-text-muted)]" />
      </a>
    </section>
  </div>
</template>
