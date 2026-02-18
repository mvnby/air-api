<script setup lang="ts">
import type { ManagerOrderListItemResponse } from '../../client';
import type { Segment } from '../../api';
import { STATUS_LABELS, formatDate, formatMoney, formatPhone, isOverdue } from './order-utils';

defineProps<{
  orders: ManagerOrderListItemResponse[];
  segment: Segment;
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
}>();
</script>

<template>
  <div class="overflow-x-auto rounded-[2rem] border border-gray-200 bg-white p-3">
    <table class="w-full min-w-[980px] text-sm text-gray-700">
      <thead>
        <tr class="text-left text-xs uppercase text-gray-500">
          <th class="px-3 py-2">Сделка</th>
          <th class="px-3 py-2">Клиент</th>
          <th class="px-3 py-2">Статус</th>
          <th class="px-3 py-2">След. касание</th>
          <th class="px-3 py-2">Сумма</th>
          <th class="px-3 py-2">Маржа</th>
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
          <td class="px-3 py-3">{{ STATUS_LABELS[order.status] || order.status }}</td>
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
