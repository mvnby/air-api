<script setup lang="ts">
import { computed, ref } from 'vue';
import type { Segment } from '../../api';
import type { OrderRenderItem } from './order-utils';
import { STATUS_LABELS, formatMoney, formatOrderCount } from './order-utils';
import OrderListRow from './OrderListRow.vue';

const props = defineProps<{
  items: OrderRenderItem[];
  segment: Segment;
  sort?: string;
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  'update:sort': [value: string];
  renameOrder: [payload: { orderId: number; title: string | null }];
}>();

const toggleSort = (key: string) => {
  if (props.sort === `${key}_desc`) emit('update:sort', `${key}_asc`);
  else emit('update:sort', `${key}_desc`);
};

const expandedGroupIds = ref<string[]>([]);

const toggleGroup = (groupId: string) => {
  expandedGroupIds.value = expandedGroupIds.value.includes(groupId)
    ? expandedGroupIds.value.filter((id) => id !== groupId)
    : [...expandedGroupIds.value, groupId];
};

const groupStatusSummary = (item: OrderRenderItem) => (
  item.type === 'group'
    ? item.group.statusCounts.map((status) => `${status.count} ${STATUS_LABELS[status.status] || status.status}`).join(' · ')
    : ''
);

const totalOrderCount = computed(() => props.items.reduce((total, item) => total + (item.type === 'group' ? item.group.orders.length : 1), 0));
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
        <template v-for="item in items" :key="item.type === 'group' ? item.group.id : item.order.id">
          <template v-if="item.type === 'group'">
            <tr class="border-t border-gray-100 bg-slate-50">
              <td class="px-3 py-3">
                <button type="button" class="flex w-full min-w-0 items-center gap-2 text-left" @click="toggleGroup(item.group.id)">
                  <span class="material-icons-round text-[18px] text-slate-500">{{ expandedGroupIds.includes(item.group.id) ? 'expand_less' : 'expand_more' }}</span>
                  <div class="min-w-0">
                    <p class="max-w-[320px] truncate font-semibold text-gray-900">{{ item.group.customerName }}</p>
                    <p class="text-xs text-gray-500">{{ formatOrderCount(item.group.orders.length) }} · {{ groupStatusSummary(item) }}</p>
                  </div>
                </button>
              </td>
              <td class="px-3 py-3">
                <p class="max-w-[260px] truncate">{{ item.group.addresses.join(' · ') || '—' }}</p>
                <p class="text-xs text-gray-500">Всего: {{ formatOrderCount(item.group.orders.length) }}</p>
              </td>
              <td class="px-3 py-3">
                <span v-if="item.group.needsAttention" class="rounded-full bg-red-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-red-700">Внимание</span>
                <span v-else-if="item.group.hasOverdue" class="rounded-full bg-amber-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-700">Есть просрочка</span>
                <span v-else class="text-xs text-gray-500">Без срочных флагов</span>
              </td>
              <td class="px-3 py-3 text-xs text-gray-500">Группа клиента</td>
              <td class="px-3 py-3">{{ formatMoney(item.group.totalAmount) }}</td>
              <td class="px-3 py-3 font-semibold text-teal-700">{{ formatMoney(item.group.margin) }}</td>
              <td class="px-3 py-3">
                <button class="btn-mini-outline" type="button" @click="toggleGroup(item.group.id)">
                  {{ expandedGroupIds.includes(item.group.id) ? 'Скрыть' : 'Показать' }}
                </button>
              </td>
            </tr>
            <OrderListRow
              v-for="order in expandedGroupIds.includes(item.group.id) ? item.group.orders : []"
              :key="`group-${item.group.id}-order-${order.id}`"
              :order="order"
              :segment="segment"
              nested
              @open="(orderId) => emit('open', orderId)"
              @generate="(payload) => emit('generate', payload)"
              @rename-order="(payload) => emit('renameOrder', payload)"
            />
          </template>
          <OrderListRow
            v-else
            :order="item.order"
            :segment="segment"
            @open="(orderId) => emit('open', orderId)"
            @generate="(payload) => emit('generate', payload)"
            @rename-order="(payload) => emit('renameOrder', payload)"
          />
        </template>
        <tr v-if="!totalOrderCount">
          <td colspan="7" class="px-3 py-8 text-center text-sm text-gray-500">Заказы не найдены</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
