<script setup lang="ts">
import type { ManagerOrderListItemResponse } from '../../client';
import type { Segment } from '../../api';
import { STATUS_LABELS, formatDate, formatMoney, formatPhone, isOverdue } from './order-utils';

const props = defineProps<{
  orders: ManagerOrderListItemResponse[];
  segment: Segment;
  sort?: string;
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  'update:sort': [value: string];
}>();

const toggleSort = (key: string) => {
  if (props.sort === `${key}_desc`) emit('update:sort', `${key}_asc`);
  else emit('update:sort', `${key}_desc`);
};
</script>

<template>
  <div class="overflow-x-auto rounded-[2rem] border border-gray-200 bg-white p-3">
    <table class="w-full min-w-[980px] text-sm text-gray-700">
      <thead>
        <tr class="text-left text-xs uppercase text-slate-500">
          <th class="px-3 py-2 cursor-pointer hover:bg-slate-100 rounded select-none group" @click="toggleSort('created_at')">
            Сделка
            <span class="inline-block ml-1 opacity-50 group-hover:opacity-100" :class="sort?.startsWith('created_at') ? 'text-teal-600 opacity-100' : ''">
              {{ sort === 'created_at_desc' ? '↓' : '↑' }}
            </span>
          </th>
          <th class="px-3 py-2">Клиент</th>
          <th class="px-3 py-2">Статус</th>
          <th class="px-3 py-2 cursor-pointer hover:bg-slate-100 rounded select-none group" @click="emit('update:sort', sort === 'followup_asc' ? 'created_at_desc' : 'followup_asc')">
            След. касание
            <span class="inline-block ml-1 opacity-50 text-teal-600 transition-opacity" :class="sort === 'followup_asc' ? 'opacity-100 font-bold' : 'opacity-0 group-hover:opacity-50'">↑</span>
          </th>
          <th class="px-3 py-2">Сумма</th>
          <th class="px-3 py-2 cursor-pointer hover:bg-slate-100 rounded select-none group" @click="emit('update:sort', sort === 'margin_desc' ? 'created_at_desc' : 'margin_desc')">
            Маржа
            <span class="inline-block ml-1 opacity-50 text-teal-600 transition-opacity" :class="sort === 'margin_desc' ? 'opacity-100 font-bold' : 'opacity-0 group-hover:opacity-50'">↓</span>
          </th>
          <th class="px-3 py-2">Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="order in orders"
          :key="order.id"
          class="border-t border-gray-100"
          :class="isOverdue(order) ? 'bg-red-50' : ''"
        >
          <td class="px-3 py-3 font-semibold">#{{ order.id }}</td>
          <td class="px-3 py-3">
            <template v-if="segment === 'b2b'">
              <p>{{ order.customer?.full_legal_name || order.customer?.name || '—' }}</p>
              <p class="text-xs text-gray-500">УНП: {{ order.customer?.inn || '—' }}</p>
            </template>
            <template v-else>
              <p>{{ order.customer?.name || '—' }}</p>
              <p class="text-xs text-gray-500">{{ formatPhone(order.customer?.phone) }}</p>
            </template>
          </td>
          <td class="px-3 py-3">
            <div class="mb-1">{{ STATUS_LABELS[order.status] || order.status }}</div>
            <div class="flex flex-col gap-1 items-start">
              <span v-if="order.needs_attention" class="rounded-full bg-red-100 text-red-700 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider">🔴 Внимание</span>
              <span v-if="order.awaiting_measurement" class="rounded-full bg-blue-100 text-blue-700 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider">🕒 Замер</span>
              <span v-if="order.client_thinking" class="rounded-full bg-amber-100 text-amber-700 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider">⏳ Думают</span>
              <span v-if="order.ready_for_execution" class="rounded-full bg-green-100 text-green-700 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider">✅ Согласовано</span>
            </div>
          </td>
          <td class="px-3 py-3">{{ formatDate(order.next_followup_date) }}</td>
          <td class="px-3 py-3">{{ formatMoney(order.total_amount) }}</td>
          <td class="px-3 py-3 font-semibold text-teal-700">{{ formatMoney(order.margin) }}</td>
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
      </tbody>
    </table>
  </div>
</template>
