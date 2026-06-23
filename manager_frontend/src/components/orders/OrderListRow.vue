<script setup lang="ts">
import type { ManagerOrderListItemResponse } from '../../client';
import type { Segment } from '../../api';
import { STATUS_LABELS, formatDate, formatMoney, formatPhone, getOrderCustomerName, isOverdue } from './order-utils';
import OrderTitleEditor from './OrderTitleEditor.vue';

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

const customerName = (order: ManagerOrderListItemResponse) => getOrderCustomerName(order, props.segment);
</script>

<template>
  <tr class="border-t border-gray-100" :class="[isOverdue(order) ? 'bg-red-50' : '', nested ? 'bg-slate-50/60' : '']">
    <td v-if="selectable" class="w-10 px-3 py-3 align-top">
      <input
        type="checkbox"
        class="mt-1 h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600"
        :checked="selected"
        :aria-label="`Выбрать заказ #${order.id}`"
        @click.stop
        @change="emit('toggleSelect', { orderId: order.id, selected: ($event.target as HTMLInputElement).checked })"
      />
    </td>
    <td class="px-3 py-3">
      <div class="flex min-w-0 items-start gap-2">
        <span v-if="nested" class="mt-1 h-2 w-2 shrink-0 rounded-full bg-slate-300" />
        <div class="min-w-0">
          <OrderTitleEditor
            class="max-w-[260px]"
            :order-id="order.id"
            :title="order.title"
            :fallback-title="customerName(order)"
            text-class="text-sm"
            @rename="(payload) => emit('renameOrder', payload)"
          />
          <p v-if="order.title?.trim()" class="max-w-[260px] truncate text-xs text-gray-500">#{{ order.id }} · {{ customerName(order) }}</p>
          <div v-if="order.manager_labels?.length" class="mt-1 flex max-w-[260px] flex-wrap gap-1">
            <span
              v-for="label in order.manager_labels"
              :key="label"
              class="rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-[10px] font-semibold text-teal-800"
            >
              {{ label }}
            </span>
          </div>
        </div>
      </div>
    </td>
    <td class="px-3 py-3">
      <template v-if="segment === 'b2b'">
        <p>{{ customerName(order) }}</p>
        <p class="text-xs text-gray-500">УНП: {{ order.customer?.inn || '—' }}</p>
      </template>
      <template v-else>
        <p>{{ customerName(order) }}</p>
        <p class="text-xs text-gray-500">{{ formatPhone(order.customer?.phone) }}</p>
      </template>
    </td>
    <td class="px-3 py-3">
      <div class="mb-1">{{ STATUS_LABELS[order.status] || order.status }}</div>
      <div class="flex flex-col items-start gap-1">
        <span v-if="order.needs_attention" class="rounded-full bg-red-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-red-700">Внимание</span>
        <span v-if="order.awaiting_measurement" class="rounded-full bg-blue-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-blue-700">Замер</span>
        <span v-if="order.client_thinking" class="rounded-full bg-amber-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-700">Думают</span>
        <span v-if="order.ready_for_execution" class="rounded-full bg-green-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-green-700">Согласовано</span>
      </div>
    </td>
    <td class="px-3 py-3">{{ formatDate(order.next_followup_date) }}</td>
    <td class="px-3 py-3">{{ formatMoney(order.total_amount) }}</td>
    <td class="px-3 py-3 font-semibold text-teal-700">{{ formatMoney(order.margin) }}</td>
    <td
      class="px-3 py-3 font-semibold"
      :class="(order.balance_due || 0) > 0 ? 'text-red-600' : 'text-emerald-700'"
    >
      {{ formatMoney(order.balance_due || 0) }}
    </td>
    <td class="px-3 py-3">
      <div class="flex flex-wrap gap-2">
        <button
          v-if="segment === 'b2b'"
          class="btn-mini"
          @click="emit('generate', { orderId: order.id, docType: 'invoice' })"
        >
          Счет
        </button>
        <button
          v-if="segment === 'b2b'"
          class="btn-mini"
          @click="emit('generate', { orderId: order.id, docType: 'contract' })"
        >
          Договор
        </button>
        <button
          v-if="segment === 'b2c'"
          class="btn-mini"
          @click="emit('generate', { orderId: order.id, docType: 'work_order' })"
        >
          Наряд
        </button>
        <button
          v-if="segment === 'b2c'"
          class="btn-mini"
          @click="emit('generate', { orderId: order.id, docType: 'act' })"
        >
          Акт
        </button>
        <button class="btn-mini-outline" @click="emit('open', order.id)">Открыть</button>
      </div>
    </td>
  </tr>
</template>
