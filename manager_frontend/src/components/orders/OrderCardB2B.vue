<script setup lang="ts">
import { computed, ref } from 'vue';
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-vue-next';
import type { ManagerOrderListItemResponse } from '../../client';
import { BOARD_CARD_ACCENT_CLASSES, BOARD_COLUMN_TONE_CLASSES, compactLegalName, formatDate, formatMoney, formatPhone, formatRelativeAge, getOrderBoardColumn, getOrderBoardLabel, getOrderExecutionLabel, getOrderExecutionStatus, getOrderNegotiationLabel, getOrderNegotiationStatus, isOverdue } from './order-utils';
import OrderCardActionsMenu from './OrderCardActionsMenu.vue';
import OrderTitleEditor from './OrderTitleEditor.vue';

const props = defineProps<{
  order: ManagerOrderListItemResponse;
  expanded: boolean;
  draggableDisabled?: boolean;
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  cancelOrder: [payload: { orderId: number }];
  quickStatus: [payload: { orderId: number; status: string }];
  closeDebt: [payload: { orderId: number }];
  dragStart: [payload: { orderId: number; oldStatus: string }];
  toggleExpanded: [orderId: number];
  renameOrder: [payload: { orderId: number; title: string | null }];
}>();

const isDragging = ref(false);

const onDragStart = () => {
  isDragging.value = true;
  emit('dragStart', { orderId: props.order.id, oldStatus: getOrderBoardColumn(props.order) });
};

const onDragEnd = () => {
  window.setTimeout(() => {
    isDragging.value = false;
  }, 0);
};

const onCardClick = () => {
  if (isDragging.value) return;
  emit('toggleExpanded', props.order.id);
};

const customerName = computed(() => compactLegalName(props.order.customer?.full_legal_name || props.order.customer?.name || `Заказ #${props.order.id}`));
const hasCustomTitle = computed(() => Boolean(props.order.title?.trim()));
const objectLine = computed(() => {
  const parts: string[] = [];
  if (hasCustomTitle.value) parts.push(customerName.value);
  if (props.order.delivery_address) parts.push(props.order.delivery_address);
  return parts.join(' · ');
});
const compactLabels = computed(() => props.order.manager_labels?.slice(0, 2) ?? []);
const hiddenLabelsCount = computed(() => Math.max((props.order.manager_labels?.length ?? 0) - compactLabels.value.length, 0));
const boardColumn = computed(() => getOrderBoardColumn(props.order));
const badgeColumn = computed(() => {
  if (props.order.status === 'negotiation') return getOrderNegotiationStatus(props.order);
  if (props.order.status === 'execution') return getOrderExecutionStatus(props.order);
  return boardColumn.value;
});
const boardLabel = computed(() => {
  if (props.order.status === 'negotiation') return getOrderNegotiationLabel(props.order);
  if (props.order.status === 'execution') return getOrderExecutionLabel(props.order);
  return getOrderBoardLabel(props.order);
});
const fallbackBoardTone = {
  column: 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800',
  badge: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
  text: 'text-slate-700 dark:text-slate-200',
};
const boardTone = computed(() => BOARD_COLUMN_TONE_CLASSES[badgeColumn.value] ?? fallbackBoardTone);
const boardBadgeClass = computed(() => boardTone.value.badge);
const boardTextClass = computed(() => boardTone.value.text);
const cardAccentClass = computed(() => BOARD_CARD_ACCENT_CLASSES[badgeColumn.value] || BOARD_CARD_ACCENT_CLASSES.negotiation);
const statusAge = computed(() => {
  const sourceDate = props.order.status === 'negotiation'
    ? props.order.negotiation_status_changed_at || props.order.status_changed_at || props.order.updated_at || props.order.created_at
    : props.order.status === 'execution'
      ? props.order.execution_status_changed_at || props.order.status_changed_at || props.order.updated_at || props.order.created_at
    : props.order.status_changed_at || props.order.updated_at || props.order.created_at;
  return formatRelativeAge(sourceDate);
});
const dateSummary = computed(() => {
  if (isOverdue(props.order)) return { label: 'Касание', value: 'просрочено', className: 'text-red-600 dark:text-red-300' };
  if (props.order.next_followup_date) return { label: 'Касание', value: formatDate(props.order.next_followup_date), className: 'text-gray-600 dark:text-slate-300' };
  if (props.order.measurement_date) return { label: 'Замер', value: formatDate(props.order.measurement_date), className: 'text-gray-600 dark:text-slate-300' };
  if (props.order.installation_date) return { label: 'Работы', value: formatDate(props.order.installation_date), className: 'text-gray-600 dark:text-slate-300' };
  return null;
});
const statusFlags = computed(() => [
  props.order.needs_attention ? { label: 'Внимание', className: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300' } : null,
  props.order.awaiting_measurement ? { label: 'Замер', className: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300' } : null,
  props.order.auto_execution_on_payment ? { label: 'Авто после оплаты', className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' } : null,
  props.order.auto_close_on_payment ? { label: 'Авто закрытие', className: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300' } : null,
  props.order.execution_without_payment ? { label: 'Без оплаты', className: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' } : null,
].filter(Boolean) as { label: string; className: string }[]);
const hasComment = computed(() => Boolean(props.order.comment?.trim()));
const paymentSummary = computed(() => {
  const balance = Number(props.order.balance_due || 0);
  if (balance > 0) {
    return { label: `Долг: ${formatMoney(balance)}`, className: 'text-red-600 dark:text-red-300' };
  }
  if (props.order.total_amount > 0) {
    return { label: 'Долг: нет', className: 'text-teal-700 dark:text-teal-300' };
  }
  return { label: 'Без суммы', className: 'text-gray-500 dark:text-slate-400' };
});
</script>

<template>
  <article
    class="group cursor-pointer rounded-2xl border p-3 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
    :class="[
      expanded ? 'border-teal-300 bg-white ring-2 ring-teal-500/20 dark:border-teal-500 dark:bg-slate-800' : cardAccentClass,
      isOverdue(order) ? 'ring-2 ring-red-500/60' : '',
    ]"
    :draggable="!draggableDisabled"
    @click="onCardClick"
    @dragstart="onDragStart"
    @dragend="onDragEnd"
  >
    <header class="space-y-1.5">
      <div class="flex min-w-0 items-center justify-between gap-2">
        <span class="-ml-1 shrink-0 rounded-r-full bg-white/80 px-2 py-0.5 text-[10px] font-bold text-slate-500 dark:bg-slate-900/40 dark:text-slate-400">№{{ order.id }}</span>
        <span class="-mr-1 max-w-[70%] truncate rounded-l-full px-2 py-0.5 text-[10px] font-semibold" :class="boardBadgeClass">{{ boardLabel }}</span>
      </div>
      <div class="flex min-w-0 items-start gap-1">
        <div class="min-w-0 flex-1">
          <OrderTitleEditor
            class="min-w-0"
            :order-id="order.id"
            :title="order.title"
            :fallback-title="customerName"
            text-class="text-[15px] leading-5"
            multiline
            @rename="(payload) => emit('renameOrder', payload)"
          />
          <p v-if="objectLine" class="mt-1 line-clamp-2 text-xs leading-4 text-gray-500 dark:text-slate-400">{{ objectLine }}</p>
        </div>
        <div class="relative flex shrink-0 items-center gap-0.5">
          <OrderCardActionsMenu
            :order="order"
            @cancel-order="(payload) => emit('cancelOrder', payload)"
            @quick-status="(payload) => emit('quickStatus', payload)"
          />
          <button
            type="button"
            class="rounded-full p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-slate-700 dark:hover:text-white"
            :aria-label="expanded ? 'Свернуть заказ' : 'Раскрыть заказ'"
            @click.stop="emit('toggleExpanded', order.id)"
          >
            <ChevronUp v-if="expanded" class="h-4 w-4" />
            <ChevronDown v-else class="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>

    <div v-if="compactLabels.length || hiddenLabelsCount" class="mt-2 flex flex-wrap gap-1">
      <span
        v-for="label in compactLabels"
        :key="label"
        class="rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-[10px] font-semibold text-teal-800 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-200"
      >
        {{ label }}
      </span>
      <span v-if="hiddenLabelsCount" class="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gray-600 dark:bg-slate-700 dark:text-slate-300">+{{ hiddenLabelsCount }}</span>
    </div>

    <div class="mt-2 flex flex-wrap items-center gap-1.5">
      <span
        v-for="flag in statusFlags"
        :key="flag.label"
        class="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide"
        :class="flag.className"
      >
        {{ flag.label }}
      </span>
      <span class="text-[11px] font-medium" :class="boardTextClass">В статусе: {{ statusAge }}</span>
      <span v-if="dateSummary" class="text-[11px] font-medium" :class="dateSummary.className">{{ dateSummary.label }}: {{ dateSummary.value }}</span>
      <span class="text-[11px] font-semibold" :class="paymentSummary.className">{{ paymentSummary.label }}</span>
    </div>

    <Transition name="fade">
      <section v-if="expanded" class="mt-3 border-t border-gray-100 pt-3 dark:border-slate-700">
        <div class="space-y-2 text-xs text-gray-600 dark:text-slate-300">
          <p v-if="order.delivery_address"><span class="font-semibold text-gray-800 dark:text-white">Объект:</span> {{ order.delivery_address }}</p>
          <p v-if="order.customer?.phone"><span class="font-semibold text-gray-800 dark:text-white">Телефон:</span> {{ formatPhone(order.customer.phone) }}</p>
          <p v-if="order.customer?.inn"><span class="font-semibold text-gray-800 dark:text-white">УНП:</span> {{ order.customer.inn }}</p>
          <p v-if="hasComment" class="max-h-20 overflow-hidden"><span class="font-semibold text-gray-800 dark:text-white">Комментарий:</span> {{ order.comment }}</p>
        </div>

        <div class="mt-3 grid grid-cols-2 gap-2 text-xs">
          <p class="rounded-xl bg-gray-50 px-2 py-1.5 text-gray-700 dark:bg-slate-900/40 dark:text-slate-300">Сумма: <span class="font-semibold">{{ formatMoney(order.total_amount) }}</span></p>
          <p class="rounded-xl bg-gray-50 px-2 py-1.5 text-gray-700 dark:bg-slate-900/40 dark:text-slate-300">Маржа: <span class="font-semibold">{{ formatMoney(order.margin) }}</span></p>
          <p v-if="order.next_followup_date" class="rounded-xl bg-gray-50 px-2 py-1.5 text-gray-700 dark:bg-slate-900/40 dark:text-slate-300">Касание: <span class="font-semibold">{{ formatDate(order.next_followup_date) }}</span></p>
          <p v-if="order.measurement_date" class="rounded-xl bg-gray-50 px-2 py-1.5 text-gray-700 dark:bg-slate-900/40 dark:text-slate-300">Замер: <span class="font-semibold">{{ formatDate(order.measurement_date) }}</span></p>
          <p v-if="order.installation_date" class="rounded-xl bg-gray-50 px-2 py-1.5 text-gray-700 dark:bg-slate-900/40 dark:text-slate-300">Работы: <span class="font-semibold">{{ formatDate(order.installation_date) }}</span></p>
        </div>

        <div v-if="order.manager_labels?.length" class="mt-3 flex flex-wrap gap-1">
          <span
            v-for="label in order.manager_labels"
            :key="label"
            class="rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-[10px] font-semibold text-teal-800 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-200"
          >
            {{ label }}
          </span>
        </div>

        <footer class="mt-3 flex flex-wrap gap-2">
          <button type="button" class="btn-mini-outline inline-flex items-center gap-1" @click.stop="emit('open', order.id)">
            <ExternalLink class="h-3.5 w-3.5" />
            Открыть заказ
          </button>
        </footer>
      </section>
    </Transition>
  </article>
</template>
