<script setup lang="ts">
import { computed, ref } from 'vue';
import { Check, ChevronDown } from 'lucide-vue-next';
import type { Segment } from '../../api';
import type { ManagerOrderListItemResponse } from '../../client';
import type { OrderRenderItem } from './order-utils';
import OrderCardB2B from './OrderCardB2B.vue';
import OrderCardB2C from './OrderCardB2C.vue';
import OrderCustomerGroupCard from './OrderCustomerGroupCard.vue';
import { BOARD_COLUMN_TONE_CLASSES, createCustomerOrderGroup, getOrderNegotiationStatus, getOrderSegment } from './order-utils';

const props = defineProps<{
  status: string;
  label: string;
  icon?: string;
  filterKind?: 'negotiation';
  filterOptions?: ReadonlyArray<{ value: string; label: string; icon?: string }>;
  items: OrderRenderItem[];
  segment: Segment;
  movingOrderIds: number[];
  expandedOrderId: number | null;
  expandedGroupIds: string[];
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  cancelOrder: [payload: { orderId: number }];
  quickStatus: [payload: { orderId: number; status: string }];
  closeDebt: [payload: { orderId: number }];
  dragStart: [payload: { orderId: number; oldStatus: string }];
  dropTo: [status: string];
  toggleExpanded: [orderId: number];
  toggleGroup: [groupId: string];
  renameCustomer: [payload: { customerId: number; alias: string | null }];
  renameOrder: [payload: { orderId: number; title: string | null }];
}>();

const activeFilter = ref('');
const filterOpen = ref(false);

const getFilterValue = (order: ManagerOrderListItemResponse) => {
  if (props.filterKind === 'negotiation') return getOrderNegotiationStatus(order);
  return '';
};

const allOrderCount = computed(() => props.items.reduce((total, item) => total + (item.type === 'group' ? item.group.orders.length : 1), 0));

const filterCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const option of props.filterOptions || []) counts[option.value] = 0;
  for (const item of props.items) {
    const orders = item.type === 'group' ? item.group.orders : [item.order];
    for (const order of orders) {
      const value = getFilterValue(order);
      if (value) counts[value] = (counts[value] || 0) + 1;
    }
  }
  return counts;
});

const visibleItems = computed<OrderRenderItem[]>(() => {
  if (!activeFilter.value || !props.filterKind) return props.items;
  const nextItems: OrderRenderItem[] = [];
  for (const item of props.items) {
    if (item.type === 'order') {
      if (getFilterValue(item.order) === activeFilter.value) nextItems.push(item);
      continue;
    }
    const filteredOrders = item.group.orders.filter((order) => getFilterValue(order) === activeFilter.value);
    if (filteredOrders.length) {
      const alias = item.group.customerName !== item.group.originalCustomerName ? item.group.customerName : undefined;
      nextItems.push({
        type: 'group',
        group: createCustomerOrderGroup(item.group.customerId, filteredOrders, props.segment, alias),
      });
    }
  }
  return nextItems;
});

const visibleOrderCount = computed(() => visibleItems.value.reduce((total, item) => total + (item.type === 'group' ? item.group.orders.length : 1), 0));
const activeFilterLabel = computed(() => props.filterOptions?.find((option) => option.value === activeFilter.value)?.label || 'Все');

const setFilter = (value: string) => {
  activeFilter.value = value;
  filterOpen.value = false;
};

const onDrop = (event: DragEvent, status: string) => {
  event.preventDefault();
  emit('dropTo', status);
};

const cardComponentForOrder = (order: ManagerOrderListItemResponse) => (
  getOrderSegment(order) === 'b2b' ? OrderCardB2B : OrderCardB2C
);
</script>

<template>
  <section
    class="min-h-[220px] w-[calc(100vw-2rem)] max-w-[320px] shrink-0 rounded-2xl border border-gray-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800 sm:w-[340px] sm:max-w-[340px] md:w-[420px] md:max-w-[420px] xl:w-[460px] xl:max-w-[460px]"
    :class="BOARD_COLUMN_TONE_CLASSES[status]?.column"
    @dragover.prevent
    @drop="(event) => onDrop(event, status)"
  >
    <header class="relative mb-3 flex items-center justify-between gap-2">
      <button
        v-if="filterOptions?.length"
        type="button"
        class="inline-flex min-w-0 items-center gap-1.5 rounded-xl px-1.5 py-1 text-left text-sm font-semibold uppercase tracking-wide transition hover:bg-white/70 dark:hover:bg-slate-700/70"
        :class="BOARD_COLUMN_TONE_CLASSES[status]?.text || 'text-gray-600 dark:text-slate-400'"
        :aria-expanded="filterOpen"
        :title="`Фильтр: ${activeFilterLabel}`"
        @click="filterOpen = !filterOpen"
      >
        <span v-if="icon" class="material-icons-round text-[17px]">{{ icon }}</span>
        <span class="truncate">{{ label }}</span>
        <span v-if="activeFilter" class="hidden rounded-full bg-white/70 px-1.5 py-0.5 text-[10px] normal-case tracking-normal text-current shadow-sm sm:inline">
          {{ activeFilterLabel }}
        </span>
        <ChevronDown class="h-3.5 w-3.5 shrink-0 transition" :class="filterOpen ? 'rotate-180' : ''" />
      </button>
      <h3 v-else class="inline-flex min-w-0 items-center gap-1.5 text-sm font-semibold uppercase tracking-wide" :class="BOARD_COLUMN_TONE_CLASSES[status]?.text || 'text-gray-600 dark:text-slate-400'">
        <span v-if="icon" class="material-icons-round text-[17px]">{{ icon }}</span>
        <span class="truncate">{{ label }}</span>
      </h3>
      <span class="rounded-full bg-gray-100 dark:bg-slate-700 px-2 py-0.5 text-xs text-gray-700 dark:text-slate-300">
        {{ activeFilter ? `${visibleOrderCount}/${allOrderCount}` : allOrderCount }}
      </span>
      <div
        v-if="filterOptions?.length && filterOpen"
        class="absolute left-0 top-9 z-20 w-72 rounded-2xl border border-gray-200 bg-white p-2 text-sm shadow-xl dark:border-slate-700 dark:bg-slate-800"
      >
        <button
          type="button"
          class="flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left font-semibold text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
          @click="setFilter('')"
        >
          <span class="inline-flex items-center gap-2">
            <span class="material-icons-round text-[16px]">{{ icon || 'filter_list' }}</span>
            Все
          </span>
          <span class="inline-flex items-center gap-2 text-xs text-slate-500">
            {{ allOrderCount }}
            <Check v-if="!activeFilter" class="h-4 w-4 text-teal-600" />
          </span>
        </button>
        <button
          v-for="option in filterOptions"
          :key="option.value"
          type="button"
          class="flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left font-semibold text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
          @click="setFilter(option.value)"
        >
          <span class="inline-flex min-w-0 items-center gap-2">
            <span v-if="option.icon" class="material-icons-round text-[16px]">{{ option.icon }}</span>
            <span class="truncate">{{ option.label }}</span>
          </span>
          <span class="inline-flex items-center gap-2 text-xs text-slate-500">
            {{ filterCounts[option.value] || 0 }}
            <Check v-if="activeFilter === option.value" class="h-4 w-4 text-teal-600" />
          </span>
        </button>
      </div>
    </header>

    <div class="space-y-3">
      <template v-for="item in visibleItems" :key="item.type === 'group' ? item.group.id : item.order.id">
        <OrderCustomerGroupCard
          v-if="item.type === 'group'"
          :group="item.group"
          :segment="segment"
          :expanded="expandedGroupIds.includes(item.group.id)"
          :moving-order-ids="movingOrderIds"
          :expanded-order-id="expandedOrderId"
          @open="(orderId) => emit('open', orderId)"
          @generate="(payload) => emit('generate', payload)"
          @cancel-order="(payload) => emit('cancelOrder', payload)"
          @quick-status="(payload) => emit('quickStatus', payload)"
          @close-debt="(payload) => emit('closeDebt', payload)"
          @drag-start="(payload) => emit('dragStart', payload)"
          @toggle-expanded="(orderId) => emit('toggleExpanded', orderId)"
          @toggle-group="(groupId) => emit('toggleGroup', groupId)"
          @rename-customer="(payload) => emit('renameCustomer', payload)"
          @rename-order="(payload) => emit('renameOrder', payload)"
        />
        <component
          :is="cardComponentForOrder(item.order)"
          v-else
          :order="item.order"
          :expanded="expandedOrderId === item.order.id"
          :draggable-disabled="movingOrderIds.includes(item.order.id)"
          @open="(orderId) => emit('open', orderId)"
          @generate="(payload) => emit('generate', payload)"
          @cancel-order="(payload) => emit('cancelOrder', payload)"
          @quick-status="(payload) => emit('quickStatus', payload)"
          @close-debt="(payload) => emit('closeDebt', payload)"
          @drag-start="(payload) => emit('dragStart', payload)"
          @toggle-expanded="(orderId) => emit('toggleExpanded', orderId)"
          @rename-order="(payload) => emit('renameOrder', payload)"
        />
      </template>
      <div v-if="!visibleItems.length" class="rounded-xl border border-dashed border-gray-200 bg-white/70 px-3 py-6 text-center text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-400">
        В этой колонке нет заказов под выбранный фильтр.
      </div>
    </div>
  </section>
</template>
