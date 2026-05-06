<script setup lang="ts">
import { computed, ref } from 'vue';
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-vue-next';
import type { ManagerOrderListItemResponse } from '../../client';
import { STATUS_LABELS, formatDate, formatMoney, formatPhone, isOverdue } from './order-utils';
import OrderTitleEditor from './OrderTitleEditor.vue';

const props = defineProps<{
  order: ManagerOrderListItemResponse;
  expanded: boolean;
  draggableDisabled?: boolean;
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  dragStart: [payload: { orderId: number; oldStatus: string }];
  toggleExpanded: [orderId: number];
  renameOrder: [payload: { orderId: number; title: string | null }];
}>();

const isDragging = ref(false);

const onDragStart = () => {
  isDragging.value = true;
  emit('dragStart', { orderId: props.order.id, oldStatus: props.order.status });
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

const customerName = computed(() => props.order.customer?.name || `Заказ #${props.order.id}`);
const hasCustomTitle = computed(() => Boolean(props.order.title?.trim()));
const objectLine = computed(() => {
  const parts: string[] = [];
  if (hasCustomTitle.value) parts.push(customerName.value);
  if (props.order.delivery_address) parts.push(props.order.delivery_address);
  return parts.join(' · ');
});
const compactLabels = computed(() => props.order.manager_labels?.slice(0, 2) ?? []);
const hiddenLabelsCount = computed(() => Math.max((props.order.manager_labels?.length ?? 0) - compactLabels.value.length, 0));
const dateSummary = computed(() => {
  if (isOverdue(props.order)) return { label: 'Касание', value: 'просрочено', className: 'text-red-600 dark:text-red-300' };
  if (props.order.next_followup_date) return { label: 'Касание', value: formatDate(props.order.next_followup_date), className: 'text-gray-600 dark:text-slate-300' };
  if (props.order.measurement_date) return { label: 'Замер', value: formatDate(props.order.measurement_date), className: 'text-gray-600 dark:text-slate-300' };
  if (props.order.installation_date) return { label: 'Монтаж', value: formatDate(props.order.installation_date), className: 'text-gray-600 dark:text-slate-300' };
  return null;
});
const statusFlags = computed(() => [
  props.order.needs_attention ? { label: 'Внимание', className: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300' } : null,
  props.order.awaiting_measurement ? { label: 'Замер', className: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300' } : null,
  props.order.client_thinking ? { label: 'Думают', className: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300' } : null,
  props.order.ready_for_execution ? { label: 'Согласовано', className: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300' } : null,
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
    class="group cursor-pointer rounded-2xl border bg-white p-3 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:bg-slate-800"
    :class="[
      expanded ? 'border-teal-300 ring-2 ring-teal-500/20 dark:border-teal-500' : 'border-gray-200 dark:border-slate-700',
      isOverdue(order) ? 'ring-2 ring-red-500/60' : '',
    ]"
    :draggable="!draggableDisabled"
    @click="onCardClick"
    @dragstart="onDragStart"
    @dragend="onDragEnd"
  >
    <header class="flex items-start gap-2">
      <div class="min-w-0 flex-1">
        <div class="flex min-w-0 items-center gap-2">
          <OrderTitleEditor
            class="min-w-0 flex-1"
            :order-id="order.id"
            :title="order.title"
            :fallback-title="customerName"
            text-class="text-sm"
            @rename="(payload) => emit('renameOrder', payload)"
          />
          <span class="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-700 dark:bg-slate-700 dark:text-slate-300">{{ STATUS_LABELS[order.status] || order.status }}</span>
        </div>
        <p v-if="objectLine" class="mt-1 truncate text-xs text-gray-500 dark:text-slate-400">{{ objectLine }}</p>
      </div>
      <button
        type="button"
        class="shrink-0 rounded-full p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-slate-700 dark:hover:text-white"
        :aria-label="expanded ? 'Свернуть заказ' : 'Раскрыть заказ'"
        @click.stop="emit('toggleExpanded', order.id)"
      >
        <ChevronUp v-if="expanded" class="h-4 w-4" />
        <ChevronDown v-else class="h-4 w-4" />
      </button>
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
      <span v-if="dateSummary" class="text-[11px] font-medium" :class="dateSummary.className">{{ dateSummary.label }}: {{ dateSummary.value }}</span>
      <span class="text-[11px] font-semibold" :class="paymentSummary.className">{{ paymentSummary.label }}</span>
    </div>

    <Transition name="fade">
      <section v-if="expanded" class="mt-3 border-t border-gray-100 pt-3 dark:border-slate-700">
        <div class="space-y-2 text-xs text-gray-600 dark:text-slate-300">
          <p v-if="order.delivery_address"><span class="font-semibold text-gray-800 dark:text-white">Адрес:</span> {{ order.delivery_address }}</p>
          <p v-if="order.customer?.phone"><span class="font-semibold text-gray-800 dark:text-white">Телефон:</span> {{ formatPhone(order.customer.phone) }}</p>
          <p v-if="hasComment" class="max-h-20 overflow-hidden"><span class="font-semibold text-gray-800 dark:text-white">Комментарий:</span> {{ order.comment }}</p>
        </div>

        <div class="mt-3 grid grid-cols-2 gap-2 text-xs">
          <p class="rounded-xl bg-gray-50 px-2 py-1.5 text-gray-700 dark:bg-slate-900/40 dark:text-slate-300">Сумма: <span class="font-semibold">{{ formatMoney(order.total_amount) }}</span></p>
          <p class="rounded-xl bg-gray-50 px-2 py-1.5 text-gray-700 dark:bg-slate-900/40 dark:text-slate-300">Маржа: <span class="font-semibold">{{ formatMoney(order.margin) }}</span></p>
          <p class="rounded-xl bg-gray-50 px-2 py-1.5 text-gray-700 dark:bg-slate-900/40 dark:text-slate-300">Оплата: <span :class="order.is_paid ? 'text-emerald-600 dark:text-emerald-300' : 'text-amber-600 dark:text-amber-300'">{{ order.is_paid ? 'Оплачено' : 'Ожидает' }}</span></p>
          <p v-if="order.next_followup_date" class="rounded-xl bg-gray-50 px-2 py-1.5 text-gray-700 dark:bg-slate-900/40 dark:text-slate-300">Касание: <span class="font-semibold">{{ formatDate(order.next_followup_date) }}</span></p>
          <p v-if="order.measurement_date" class="rounded-xl bg-gray-50 px-2 py-1.5 text-gray-700 dark:bg-slate-900/40 dark:text-slate-300">Замер: <span class="font-semibold">{{ formatDate(order.measurement_date) }}</span></p>
          <p v-if="order.installation_date" class="rounded-xl bg-gray-50 px-2 py-1.5 text-gray-700 dark:bg-slate-900/40 dark:text-slate-300">Монтаж: <span class="font-semibold">{{ formatDate(order.installation_date) }}</span></p>
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
          <button type="button" class="btn-mini" @click.stop="emit('generate', { orderId: order.id, docType: 'work_order' })">Наряд</button>
          <button type="button" class="btn-mini" @click.stop="emit('generate', { orderId: order.id, docType: 'act' })">Акт</button>
          <button type="button" class="btn-mini-outline inline-flex items-center gap-1" @click.stop="emit('open', order.id)">
            <ExternalLink class="h-3.5 w-3.5" />
            Открыть заказ
          </button>
        </footer>
      </section>
    </Transition>
  </article>
</template>
