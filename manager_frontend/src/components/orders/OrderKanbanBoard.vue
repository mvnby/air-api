<script setup lang="ts">
import { ref } from 'vue';
import type { ManagerOrderListItemResponse } from '../../client';
import type { Segment } from '../../api';
import OrderColumn from './OrderColumn.vue';
import { STATUS_LABELS, STATUS_ORDER } from './order-utils';

defineProps<{
  groupedOrders: Record<string, ManagerOrderListItemResponse[]>;
  segment: Segment;
  movingOrderIds: number[];
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  move: [payload: { orderId: number; oldStatus: string; newStatus: string }];
}>();

const dragContext = ref<{ orderId: number; oldStatus: string } | null>(null);
const expandedOrderId = ref<number | null>(null);

const onToggleExpanded = (orderId: number) => {
  expandedOrderId.value = expandedOrderId.value === orderId ? null : orderId;
};

const onDropTo = (newStatus: string) => {
  if (!dragContext.value) return;
  if (dragContext.value.oldStatus === newStatus) {
    dragContext.value = null;
    return;
  }
  emit('move', {
    orderId: dragContext.value.orderId,
    oldStatus: dragContext.value.oldStatus,
    newStatus,
  });
  dragContext.value = null;
};

const onDragStart = (payload: { orderId: number; oldStatus: string }) => {
  dragContext.value = payload;
};
</script>

<template>
  <div class="flex gap-4 overflow-x-auto pb-4">
    <OrderColumn
      v-for="status in STATUS_ORDER"
      :key="status"
      :status="status"
      :label="STATUS_LABELS[status] || status"
      :orders="groupedOrders[status] || []"
      :segment="segment"
      :moving-order-ids="movingOrderIds"
      :expanded-order-id="expandedOrderId"
      @open="(orderId) => emit('open', orderId)"
      @generate="(payload) => emit('generate', payload)"
      @drag-start="(payload) => onDragStart(payload)"
      @drop-to="(dropStatus) => onDropTo(dropStatus)"
      @toggle-expanded="onToggleExpanded"
    />
  </div>
</template>
