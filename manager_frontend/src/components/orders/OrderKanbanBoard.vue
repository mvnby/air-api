<script setup lang="ts">
import { ref } from 'vue';
import type { OrderBoardState } from '../../services/order-navigation';
import type { Segment } from '../../api';
import type { OrderRenderItem } from './order-utils';
import OrderColumn from './OrderColumn.vue';
import { BOARD_COLUMNS, BOARD_COLUMN_LABELS, EXECUTION_STATUS_OPTIONS, NEGOTIATION_STATUS_OPTIONS } from './order-utils';

defineProps<{
  groupedItems: Record<string, OrderRenderItem[]>;
  segment: Segment;
  movingOrderIds: number[];
  filterReset?: number;
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  move: [payload: { orderId: number; oldStatus: string; newStatus: string }];
  cancelOrder: [payload: { orderId: number }];
  closeDebt: [payload: { orderId: number }];
  renameCustomer: [payload: { customerId: number; alias: string | null }];
  renameOrder: [payload: { orderId: number; title: string | null }];
}>();

const scroller = ref<HTMLElement | null>(null);
const columns = ref<InstanceType<typeof OrderColumn>[]>([]);
const dragContext = ref<{ orderId: number; oldStatus: string } | null>(null);
const expandedOrderId = ref<number | null>(null);
const expandedGroupIds = ref<string[]>([]);

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

const onToggleGroup = (groupId: string) => {
  expandedGroupIds.value = expandedGroupIds.value.includes(groupId)
    ? expandedGroupIds.value.filter((id) => id !== groupId)
    : [...expandedGroupIds.value, groupId];
};
defineExpose({
  captureState: (): OrderBoardState => ({
    expandedOrderId: expandedOrderId.value, expandedGroupIds: [...expandedGroupIds.value],
    columnFilters: Object.fromEntries(columns.value.map(column => [column.$props.status, column.getFilter()])),
    scrollLeft: scroller.value?.scrollLeft || 0,
  }),
  restoreState: (state: OrderBoardState) => {
    expandedOrderId.value = state.expandedOrderId;
    expandedGroupIds.value = [...state.expandedGroupIds];
    columns.value.forEach(column => column.restoreFilter(state.columnFilters[column.$props.status] || ''));
    if (scroller.value) scroller.value.scrollLeft = state.scrollLeft;
  },
});
</script>

<template>
  <div ref="scroller" class="flex gap-4 overflow-x-auto pb-4">
    <OrderColumn
      v-for="column in BOARD_COLUMNS"
      ref="columns"
      :key="column.value"
      :status="column.value"
      :label="BOARD_COLUMN_LABELS[column.value] || column.label"
      :icon="column.icon"
      :filter-kind="column.value === 'negotiation' ? 'negotiation' : column.value === 'execution' ? 'execution' : undefined"
      :filter-options="column.value === 'negotiation' ? NEGOTIATION_STATUS_OPTIONS : column.value === 'execution' ? EXECUTION_STATUS_OPTIONS : undefined"
      :items="groupedItems[column.value] || []"
      :filter-reset="filterReset"
      :segment="segment"
      :moving-order-ids="movingOrderIds"
      :expanded-order-id="expandedOrderId"
      :expanded-group-ids="expandedGroupIds"
      @open="(orderId) => emit('open', orderId)"
      @generate="(payload) => emit('generate', payload)"
      @cancel-order="(payload) => emit('cancelOrder', payload)"
      @quick-status="(payload) => emit('move', { orderId: payload.orderId, oldStatus: '', newStatus: payload.status })"
      @close-debt="(payload) => emit('closeDebt', payload)"
      @drag-start="(payload) => onDragStart(payload)"
      @drop-to="(dropStatus) => onDropTo(dropStatus)"
      @toggle-expanded="onToggleExpanded"
      @toggle-group="onToggleGroup"
      @rename-customer="(payload) => emit('renameCustomer', payload)"
      @rename-order="(payload) => emit('renameOrder', payload)"
    />
  </div>
</template>
