<script setup lang="ts">
import { computed } from 'vue';
import type { ManagerOrderListItemResponse } from '../../client';
import type { Segment } from '../../api';
import { formatDate, formatMoney, formatPhone, getOrderBoardLabel, getOrderCustomerName, getOrderExecutionLabel, getOrderNegotiationLabel, getOrderSegment, isOverdue } from './order-utils';
import OrderTitleEditor from './OrderTitleEditor.vue';
import { useDemoReadOnly } from '../../services/manager-demo';

const props = defineProps<{
  order: ManagerOrderListItemResponse;
  segment: Segment;
  nested?: boolean;
  selectable?: boolean;
  selected?: boolean;
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  renameOrder: [payload: { orderId: number; title: string | null }];
  toggleSelect: [payload: { orderId: number; selected: boolean }];
}>();

const rowSegment = computed(() => (props.segment === 'all' ? getOrderSegment(props.order) : props.segment));
const customerName = computed(() => getOrderCustomerName(props.order, rowSegment.value));
const hasTitle = computed(() => Boolean(props.order.title?.trim()));
const stage = computed(() => {
  if (props.order.status === 'negotiation') return { label: 'Переговоры', detail: getOrderNegotiationLabel(props.order) };
  if (props.order.status === 'execution') return { label: 'Работы', detail: getOrderExecutionLabel(props.order) };
  return { label: getOrderBoardLabel(props.order), detail: null };
});
const balanceDue = computed(() => Number(props.order.balance_due || 0));
const demoReadOnly = useDemoReadOnly();
</script>

<template>
  <tr class="border-t border-gray-100 dark:border-slate-700" :class="[isOverdue(order) ? 'bg-red-50 dark:bg-red-500/10' : '', nested ? 'bg-slate-50/60 dark:bg-slate-800/50' : '']">
    <td v-if="selectable" class="w-10 px-3 py-3 align-top">
      <input
        type="checkbox"
        class="mt-1 h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-600"
        :checked="selected"
        :aria-label="`Выбрать заказ #${order.id}`"
        @click.stop
        @change="emit('toggleSelect', { orderId: order.id, selected: ($event.target as HTMLInputElement).checked })"
      />
    </td>
    <td class="px-3 py-2.5 align-top">
      <div class="flex min-w-0 items-start gap-2">
        <span v-if="nested" class="mt-1 h-2 w-2 shrink-0 rounded-full bg-slate-300" />
        <div class="min-w-0">
          <p class="text-xs font-semibold text-slate-500 dark:text-slate-400">#{{ order.id }}</p>
          <OrderTitleEditor
            class="max-w-full"
            :order-id="order.id"
            :title="order.title"
            :fallback-title="customerName"
            text-class="text-sm leading-5"
            multiline
            @rename="(payload) => emit('renameOrder', payload)"
          />
          <p v-if="hasTitle" class="mt-0.5 line-clamp-2 text-xs leading-4 text-gray-600 dark:text-slate-300" :title="customerName">{{ customerName }}</p>
          <p v-if="rowSegment === 'b2b' && order.customer?.inn" class="text-xs text-gray-500 dark:text-slate-400">УНП: {{ order.customer.inn }}</p>
          <p v-else-if="rowSegment === 'b2c' && order.customer?.phone" class="text-xs text-gray-500 dark:text-slate-400">{{ formatPhone(order.customer.phone) }}</p>
          <div v-if="order.manager_labels?.length" class="mt-1 flex flex-wrap gap-1">
            <span
              v-for="label in order.manager_labels"
              :key="label"
              class="rounded-full border border-brand-200 bg-brand-50 px-2 py-0.5 text-[10px] font-semibold text-brand-800"
            >
              {{ label }}
            </span>
          </div>
        </div>
      </div>
    </td>
    <td class="px-3 py-2.5 align-top">
      <div class="font-medium text-gray-900 dark:text-white">{{ stage.label }}</div>
      <div v-if="stage.detail" class="mt-0.5 text-xs text-gray-600 dark:text-slate-300">{{ stage.detail }}</div>
      <div class="flex flex-col items-start gap-1">
        <span v-if="order.needs_attention" class="rounded-full bg-red-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-red-700">Внимание</span>
        <span v-if="order.awaiting_measurement" class="rounded-full bg-blue-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-blue-700">Замер</span>
        <span v-if="order.client_thinking" class="rounded-full bg-amber-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-700">Думают</span>
        <span v-if="order.ready_for_execution" class="rounded-full bg-green-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-green-700">Согласовано</span>
      </div>
    </td>
    <td class="px-3 py-2.5 align-top text-xs">
      <p><span class="text-gray-500 dark:text-slate-400">Касание:</span> {{ formatDate(order.next_followup_date) }}</p>
      <p><span class="text-gray-500 dark:text-slate-400">Работы:</span> {{ formatDate(order.installation_date) }}</p>
    </td>
    <td class="px-3 py-2.5 align-top text-xs">
      <p class="font-semibold text-gray-900 dark:text-white">{{ formatMoney(order.total_amount) }}</p>
      <p v-if="!demoReadOnly" class="mt-0.5 text-brand-700 dark:text-brand-300">Маржа: {{ formatMoney(Number(order.margin || 0)) }}</p>
    </td>
    <td class="px-3 py-2.5 align-top text-xs">
      <p class="font-semibold" :class="balanceDue > 0 ? 'text-amber-800 dark:text-amber-300' : 'text-gray-900 dark:text-white'">{{ formatMoney(balanceDue) }}</p>
    </td>
    <td class="px-3 py-2.5 align-top">
      <div class="flex flex-col items-start gap-1.5">
        <button class="btn-mini-outline whitespace-nowrap" @click="emit('open', order.id)">Открыть</button>
        <details class="relative text-xs">
          <summary class="cursor-pointer text-brand-700 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200">Документы</summary>
          <div class="mt-1 flex w-full flex-col gap-1">
            <template v-if="rowSegment === 'b2b'">
              <button class="btn-mini whitespace-nowrap" @click="emit('generate', { orderId: order.id, docType: 'invoice' })">Счет</button>
              <button class="btn-mini whitespace-nowrap" @click="emit('generate', { orderId: order.id, docType: 'contract' })">Договор</button>
            </template>
            <template v-else>
              <button class="btn-mini whitespace-nowrap" @click="emit('generate', { orderId: order.id, docType: 'work_order' })">Наряд</button>
              <button class="btn-mini whitespace-nowrap" @click="emit('generate', { orderId: order.id, docType: 'act' })">Акт</button>
            </template>
          </div>
        </details>
      </div>
    </td>
  </tr>
</template>
