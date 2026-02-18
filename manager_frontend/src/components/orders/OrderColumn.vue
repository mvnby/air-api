<script setup lang="ts">
import type { ManagerOrderListItemResponse } from '../../client';
import type { Segment } from '../../api';
import OrderCardB2B from './OrderCardB2B.vue';
import OrderCardB2C from './OrderCardB2C.vue';

defineProps<{
  status: string;
  label: string;
  orders: ManagerOrderListItemResponse[];
  segment: Segment;
  movingOrderIds: number[];
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  dragStart: [payload: { orderId: number; oldStatus: string }];
  dropTo: [status: string];
}>();

const onDrop = (event: DragEvent, status: string) => {
  event.preventDefault();
  emit('dropTo', status);
};
</script>

<template>
  <section
    class="min-h-[220px] w-[360px] shrink-0 rounded-[2rem] border border-gray-200 bg-white p-4"
    @dragover.prevent
    @drop="(event) => onDrop(event, status)"
  >
    <header class="mb-3 flex items-center justify-between">
      <h3 class="text-sm font-semibold uppercase tracking-wide text-gray-600">{{ label }}</h3>
      <span class="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700">{{ orders.length }}</span>
    </header>

    <div class="space-y-3">
      <component
        :is="segment === 'b2b' ? OrderCardB2B : OrderCardB2C"
        v-for="order in orders"
        :key="order.id"
        :order="order"
        :draggable-disabled="movingOrderIds.includes(order.id)"
        @open="(orderId) => emit('open', orderId)"
        @generate="(payload) => emit('generate', payload)"
        @drag-start="(payload) => emit('dragStart', payload)"
      />
    </div>
  </section>
</template>
