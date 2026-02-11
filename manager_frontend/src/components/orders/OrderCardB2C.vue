<script setup lang="ts">
import type { ManagerOrderListItemResponse } from '../../client';
import { STATUS_LABELS, formatDate, formatMoney, formatPhone, isOverdue } from './order-utils';

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
    class="rounded-[2rem] border border-slate-700 bg-slate-800 p-5 shadow-lg"
    :class="isOverdue(order) ? 'ring-2 ring-red-500/70' : 'ring-1 ring-transparent'"
    :draggable="!draggableDisabled"
    @dragstart="onDragStart"
  >
    <header class="mb-3 flex items-start justify-between gap-3">
      <div>
        <p class="text-lg font-semibold text-white">{{ order.customer?.name || `Заказ #${order.id}` }}</p>
        <p class="text-sm text-slate-300">{{ formatPhone(order.customer?.phone) }}</p>
      </div>
      <span class="rounded-full bg-slate-700 px-2 py-1 text-xs text-slate-200">{{ STATUS_LABELS[order.status] || order.status }}</span>
    </header>

    <div class="space-y-1 text-sm text-slate-200">
      <p>Замер: {{ formatDate(order.assessment_date) }}</p>
      <p>Монтаж: {{ formatDate(order.installation_date) }}</p>
      <p class="font-semibold text-teal-300">Маржа: {{ formatMoney(order.margin) }}</p>
      <p v-if="isOverdue(order)" class="font-semibold text-red-400">Просрочено касание</p>
    </div>

    <footer class="mt-4 flex flex-wrap gap-2">
      <button class="btn-mini" @click="emit('generate', { orderId: order.id, docType: 'work_order' })">Наряд на монтаж</button>
      <button class="btn-mini" @click="emit('generate', { orderId: order.id, docType: 'act' })">Акт</button>
      <button class="btn-mini-outline" @click="emit('open', order.id)">Открыть</button>
    </footer>
  </article>
</template>
