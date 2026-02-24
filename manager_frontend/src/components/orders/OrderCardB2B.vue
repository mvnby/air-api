<script setup lang="ts">
import type { ManagerOrderListItemResponse } from '../../client';
import { STATUS_LABELS, formatMoney, isOverdue } from './order-utils';

const props = defineProps<{
  order: ManagerOrderListItemResponse;
  draggableDisabled?: boolean;
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  dragStart: [payload: { orderId: number; oldStatus: string }];
}>();

const onDragStart = () => {
  emit('dragStart', { orderId: props.order.id, oldStatus: props.order.status });
};
</script>

<template>
  <article
    class="rounded-[2rem] border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5 shadow-lg"
    :class="isOverdue(order) ? 'ring-2 ring-red-500/70' : 'ring-1 ring-transparent'"
    :draggable="!draggableDisabled"
    @dragstart="onDragStart"
  >
    <header class="mb-3 flex items-start justify-between gap-3">
      <div>
        <p class="text-lg font-semibold text-gray-900 dark:text-white">{{ order.customer?.full_legal_name || order.customer?.name || `Заказ #${order.id}` }}</p>
        <p class="text-sm text-gray-500 dark:text-slate-400">УНП: {{ order.customer?.inn || '—' }}</p>
      </div>
      <span class="rounded-full bg-gray-100 dark:bg-slate-700 px-2 py-1 text-xs text-gray-700 dark:text-slate-300">{{ STATUS_LABELS[order.status] || order.status }}</span>
    </header>

    <div class="mb-3 flex flex-wrap gap-1">
      <span v-if="order.needs_attention" class="rounded-full bg-red-100 text-red-700 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider">🔴 Внимание (замер)</span>
      <span v-if="order.awaiting_measurement" class="rounded-full bg-blue-100 text-blue-700 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider">🕒 Замер</span>
      <span v-if="order.client_thinking" class="rounded-full bg-amber-100 text-amber-700 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider">⏳ Думают</span>
      <span v-if="order.ready_for_execution" class="rounded-full bg-green-100 text-green-700 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider">✅ Согласовано</span>
    </div>

    <div class="space-y-1 text-sm text-gray-700 dark:text-slate-300">
      <p>
        Счет:
        <span :class="order.is_paid ? 'text-emerald-300' : 'text-amber-300'">{{ order.is_paid ? 'Оплачен' : 'Ожидает оплаты' }}</span>
      </p>
      <p class="font-semibold text-teal-700 dark:text-teal-400">Маржа: {{ formatMoney(order.margin) }}</p>
      <p v-if="isOverdue(order)" class="font-semibold text-red-400">Просрочено касание</p>
    </div>

    <footer class="mt-4 flex flex-wrap gap-2">
      <button class="btn-mini" @click="emit('generate', { orderId: order.id, docType: 'invoice' })">Счет</button>
      <button class="btn-mini" @click="emit('generate', { orderId: order.id, docType: 'contract' })">Договор</button>
      <button class="btn-mini-outline" @click="emit('open', order.id)">Открыть</button>
    </footer>
  </article>
</template>
