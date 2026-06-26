<script setup lang="ts">
import { ref, watch } from 'vue';
import { Check, ChevronDown, ChevronUp, X } from 'lucide-vue-next';
import type { Segment } from '../../api';
import type { ManagerOrderListItemResponse } from '../../client';
import type { CustomerOrderGroup } from './order-utils';
import { formatMoney, formatOrderCount, getOrderSegment } from './order-utils';
import OrderCardB2B from './OrderCardB2B.vue';
import OrderCardB2C from './OrderCardB2C.vue';

const props = defineProps<{
  group: CustomerOrderGroup;
  segment: Segment;
  expanded: boolean;
  movingOrderIds: number[];
  expandedOrderId: number | null;
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  cancelOrder: [payload: { orderId: number }];
  quickStatus: [payload: { orderId: number; status: string }];
  closeDebt: [payload: { orderId: number }];
  dragStart: [payload: { orderId: number; oldStatus: string }];
  toggleExpanded: [orderId: number];
  toggleGroup: [groupId: string];
  renameCustomer: [payload: { customerId: number; alias: string | null }];
  renameOrder: [payload: { orderId: number; title: string | null }];
}>();

const editing = ref(false);
const aliasDraft = ref(props.group.customerName);

watch(
  () => props.group.customerName,
  (value) => {
    if (!editing.value) aliasDraft.value = value;
  },
);

const startEditing = () => {
  editing.value = true;
  aliasDraft.value = props.group.customerName;
};

const saveAlias = () => {
  const trimmed = aliasDraft.value.trim();
  emit('renameCustomer', { customerId: props.group.customerId, alias: trimmed || null });
  editing.value = false;
};

const cancelEditing = () => {
  editing.value = false;
  aliasDraft.value = props.group.customerName;
};

const onGroupClick = () => {
  if (!editing.value) emit('toggleGroup', props.group.id);
};

const cardComponentForOrder = (order: ManagerOrderListItemResponse) => {
  const segment = props.segment === 'all' ? getOrderSegment(order) : props.segment;
  return segment === 'b2b' ? OrderCardB2B : OrderCardB2C;
};
</script>

<template>
  <article
    class="rounded-2xl border bg-slate-50 p-3 shadow-sm transition dark:border-slate-700 dark:bg-slate-900/40"
    :class="group.hasOverdue ? 'border-red-200 ring-2 ring-red-500/40' : 'border-slate-200'"
  >
    <div
      class="flex w-full items-start gap-2 text-left"
      :aria-expanded="expanded"
      role="button"
      tabindex="0"
      @click="onGroupClick"
      @keydown.enter.prevent="onGroupClick"
      @keydown.space.prevent="onGroupClick"
    >
      <div class="min-w-0 flex-1">
        <div class="flex min-w-0 flex-wrap items-center gap-2">
          <div class="min-w-0 flex-1" @click.stop>
            <div v-if="editing" class="flex min-w-0 items-center gap-1">
              <input
                v-model="aliasDraft"
                class="min-w-0 flex-1 rounded-lg border border-teal-200 bg-white px-2 py-1 text-sm font-semibold text-slate-900 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-white"
                :placeholder="group.originalCustomerName"
                autofocus
                @blur="saveAlias"
                @keydown.enter.prevent="saveAlias"
                @keydown.esc.prevent="cancelEditing"
              />
              <button type="button" class="rounded-full p-1 text-teal-700 hover:bg-teal-50" @mousedown.prevent @click.stop="saveAlias">
                <Check class="h-3.5 w-3.5" />
              </button>
              <button type="button" class="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" @mousedown.prevent @click.stop="cancelEditing">
                <X class="h-3.5 w-3.5" />
              </button>
            </div>
            <p
              v-else
              class="min-w-0 truncate text-sm font-semibold text-slate-900 dark:text-white"
              title="Двойной клик — переименовать группу локально"
              @dblclick.stop="startEditing"
            >
              {{ group.customerName }}
            </p>
          </div>
          <span class="shrink-0 rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            {{ formatOrderCount(group.orders.length) }}
          </span>
        </div>
        <div class="mt-2 flex flex-wrap gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
          <span>Сумма: <strong class="text-slate-800 dark:text-slate-200">{{ formatMoney(group.totalAmount) }}</strong></span>
          <span>Маржа: <strong class="text-teal-700 dark:text-teal-300">{{ formatMoney(group.margin) }}</strong></span>
          <span>
            Долг:
            <strong :class="group.balanceDue > 0 ? 'text-red-600 dark:text-red-300' : 'text-emerald-700 dark:text-emerald-300'">
              {{ formatMoney(group.balanceDue) }}
            </strong>
          </span>
          <span v-if="group.needsAttention" class="font-semibold text-red-600 dark:text-red-300">Нужно внимание</span>
        </div>
      </div>
      <span class="shrink-0 rounded-full p-1 text-slate-400 transition hover:bg-white hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-white">
        <ChevronUp v-if="expanded" class="h-4 w-4" />
        <ChevronDown v-else class="h-4 w-4" />
      </span>
    </div>

    <Transition name="fade">
      <div v-if="expanded" class="mt-3 space-y-2 border-t border-slate-200 pt-3 dark:border-slate-700">
        <component
          :is="cardComponentForOrder(order)"
          v-for="order in group.orders"
          :key="order.id"
          :order="order"
          :expanded="expandedOrderId === order.id"
          :draggable-disabled="movingOrderIds.includes(order.id)"
          @open="(orderId) => emit('open', orderId)"
          @generate="(payload) => emit('generate', payload)"
          @cancel-order="(payload) => emit('cancelOrder', payload)"
          @quick-status="(payload) => emit('quickStatus', payload)"
          @close-debt="(payload) => emit('closeDebt', payload)"
          @drag-start="(payload) => emit('dragStart', payload)"
          @toggle-expanded="(orderId) => emit('toggleExpanded', orderId)"
          @rename-order="(payload) => emit('renameOrder', payload)"
        />
      </div>
    </Transition>
  </article>
</template>
