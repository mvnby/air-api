<script setup lang="ts">
import type { Segment } from '../../api';
import type { OrderRenderItem } from './order-utils';
import OrderCardB2B from './OrderCardB2B.vue';
import OrderCardB2C from './OrderCardB2C.vue';
import OrderCustomerGroupCard from './OrderCustomerGroupCard.vue';

const props = defineProps<{
  status: string;
  label: string;
  items: OrderRenderItem[];
  segment: Segment;
  movingOrderIds: number[];
  expandedOrderId: number | null;
  expandedGroupIds: string[];
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  dragStart: [payload: { orderId: number; oldStatus: string }];
  dropTo: [status: string];
  toggleExpanded: [orderId: number];
  toggleGroup: [groupId: string];
  renameCustomer: [payload: { customerId: number; alias: string | null }];
  renameOrder: [payload: { orderId: number; title: string | null }];
}>();

const orderCount = () => props.items.reduce((total, item) => total + (item.type === 'group' ? item.group.orders.length : 1), 0);

const onDrop = (event: DragEvent, status: string) => {
  event.preventDefault();
  emit('dropTo', status);
};
</script>

<template>
  <section
    class="min-h-[220px] w-[calc(100vw-2rem)] max-w-[320px] shrink-0 rounded-2xl border border-gray-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800 sm:w-[320px] md:w-[350px] md:max-w-[350px] lg:w-[380px] lg:max-w-[380px]"
    @dragover.prevent
    @drop="(event) => onDrop(event, status)"
  >
    <header class="mb-3 flex items-center justify-between">
      <h3 class="text-sm font-semibold uppercase tracking-wide text-gray-600 dark:text-slate-400">{{ label }}</h3>
      <span class="rounded-full bg-gray-100 dark:bg-slate-700 px-2 py-0.5 text-xs text-gray-700 dark:text-slate-300">{{ orderCount() }}</span>
    </header>

    <div class="space-y-3">
      <template v-for="item in items" :key="item.type === 'group' ? item.group.id : item.order.id">
        <OrderCustomerGroupCard
          v-if="item.type === 'group'"
          :group="item.group"
          :segment="segment"
          :expanded="expandedGroupIds.includes(item.group.id)"
          :moving-order-ids="movingOrderIds"
          :expanded-order-id="expandedOrderId"
          @open="(orderId) => emit('open', orderId)"
          @generate="(payload) => emit('generate', payload)"
          @drag-start="(payload) => emit('dragStart', payload)"
          @toggle-expanded="(orderId) => emit('toggleExpanded', orderId)"
          @toggle-group="(groupId) => emit('toggleGroup', groupId)"
          @rename-customer="(payload) => emit('renameCustomer', payload)"
          @rename-order="(payload) => emit('renameOrder', payload)"
        />
        <component
          :is="segment === 'b2b' ? OrderCardB2B : OrderCardB2C"
          v-else
          :order="item.order"
          :expanded="expandedOrderId === item.order.id"
          :draggable-disabled="movingOrderIds.includes(item.order.id)"
          @open="(orderId) => emit('open', orderId)"
          @generate="(payload) => emit('generate', payload)"
          @drag-start="(payload) => emit('dragStart', payload)"
          @toggle-expanded="(orderId) => emit('toggleExpanded', orderId)"
          @rename-order="(payload) => emit('renameOrder', payload)"
        />
      </template>
    </div>
  </section>
</template>
