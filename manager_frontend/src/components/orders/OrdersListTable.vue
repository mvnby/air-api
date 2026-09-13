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
  selectedOrderIds?: number[];
}>();

const emit = defineEmits<{
  open: [orderId: number];
  generate: [payload: { orderId: number; docType: string }];
  'update:sort': [value: string];
  renameOrder: [payload: { orderId: number; title: string | null }];
  toggleSelect: [payload: { orderId: number; selected: boolean }];
  toggleSelectMany: [payload: { orderIds: number[]; selected: boolean }];
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
const selectedSet = computed(() => new Set(props.selectedOrderIds || []));
const groupOrderIds = (item: OrderRenderItem) => (item.type === 'group' ? item.group.orders.map((order) => order.id) : []);
const isGroupSelected = (item: OrderRenderItem) => {
  const ids = groupOrderIds(item);
  return ids.length > 0 && ids.every((id) => selectedSet.value.has(id));
};
</script>

<template>
  <div class="overflow-x-auto rounded-[2rem] border border-gray-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900 sm:p-3">
    <table class="w-full min-w-[960px] table-fixed text-sm text-gray-700 dark:text-slate-200">
      <colgroup>
        <col class="w-10" />
        <col class="w-[280px]" />
        <col class="w-[155px]" />
        <col class="w-[135px]" />
        <col class="w-[120px]" />
        <col class="w-[100px]" />
        <col class="w-[90px]" />
      </colgroup>
      <thead>
        <tr class="text-left text-xs uppercase text-slate-500 dark:text-slate-400">
          <th class="w-10 px-3 py-2"></th>
          <th class="px-3 py-2" :aria-sort="sort === 'created_at_asc' ? 'ascending' : sort === 'created_at_desc' ? 'descending' : 'none'">
            <button type="button" class="rounded px-1 py-0.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800" @click="toggleSort('created_at')">
              Заказ и клиент {{ sort === 'created_at_desc' ? '↓' : sort === 'created_at_asc' ? '↑' : '' }}
            </button>
          </th>
          <th class="px-3 py-2">Статус</th>
          <th class="px-3 py-2" :aria-sort="sort === 'followup_asc' ? 'ascending' : 'none'">
            <button type="button" class="rounded px-1 py-0.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800" @click="emit('update:sort', sort === 'followup_asc' ? 'created_at_desc' : 'followup_asc')">
              Контакт {{ sort === 'followup_asc' ? '↑' : '' }}
            </button>
          </th>
          <th class="px-3 py-2" :aria-sort="sort === 'margin_desc' ? 'descending' : 'none'">
            Сумма
            <button type="button" class="block rounded px-1 py-0.5 text-left text-[10px] normal-case text-brand-700 hover:bg-slate-100 dark:text-brand-300 dark:hover:bg-slate-800" @click="emit('update:sort', sort === 'margin_desc' ? 'created_at_desc' : 'margin_desc')">
              Маржа {{ sort === 'margin_desc' ? '↓' : '↕' }}
            </button>
          </th>
          <th class="px-3 py-2">Остаток</th>
          <th class="px-3 py-2">Действия</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="item in items" :key="item.type === 'group' ? item.group.id : item.order.id">
          <template v-if="item.type === 'group'">
            <tr class="border-t border-gray-100 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/70">
              <td class="w-10 px-3 py-3 align-top">
                <input
                  type="checkbox"
                  class="mt-1 h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-600"
                  :checked="isGroupSelected(item)"
                  :aria-label="`Выбрать группу ${item.group.customerName}`"
                  @change="emit('toggleSelectMany', { orderIds: groupOrderIds(item), selected: ($event.target as HTMLInputElement).checked })"
                />
              </td>
              <td class="px-3 py-3">
                <button type="button" class="flex w-full min-w-0 items-center gap-2 text-left" @click="toggleGroup(item.group.id)">
                  <span class="material-icons-round text-[18px] text-slate-500">{{ expandedGroupIds.includes(item.group.id) ? 'expand_less' : 'expand_more' }}</span>
                  <div class="min-w-0">
                    <p class="max-w-[320px] truncate font-semibold text-gray-900 dark:text-white" :title="item.group.customerName">{{ item.group.customerName }}</p>
                    <p class="text-xs text-gray-500 dark:text-slate-400">{{ formatOrderCount(item.group.orders.length) }} · {{ groupStatusSummary(item) }}</p>
                  </div>
                </button>
              </td>
              <td class="px-3 py-3">
                <span v-if="item.group.needsAttention" class="rounded-full bg-red-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-red-700">Внимание</span>
                <span v-else-if="item.group.hasOverdue" class="rounded-full bg-amber-100 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-700">Пора связаться</span>
                <span v-else class="text-xs text-gray-500 dark:text-slate-400">Без срочных флагов</span>
              </td>
              <td class="px-3 py-3 text-xs text-gray-500 dark:text-slate-400">Сводка по клиенту</td>
              <td class="px-3 py-3 text-xs"><p class="font-semibold text-gray-900 dark:text-white">{{ formatMoney(item.group.totalAmount) }}</p><p class="mt-0.5 text-brand-700 dark:text-brand-300">Маржа: {{ formatMoney(item.group.margin) }}</p></td>
              <td
                class="px-3 py-3 text-xs"
              >
                <p class="font-semibold" :class="item.group.balanceDue > 0 ? 'text-amber-800 dark:text-amber-300' : 'text-gray-900 dark:text-white'">{{ formatMoney(item.group.balanceDue) }}</p>
              </td>
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
              selectable
              :selected="selectedSet.has(order.id)"
              @open="(orderId) => emit('open', orderId)"
              @generate="(payload) => emit('generate', payload)"
              @rename-order="(payload) => emit('renameOrder', payload)"
              @toggle-select="(payload) => emit('toggleSelect', payload)"
            />
          </template>
          <OrderListRow
            v-else
            :order="item.order"
            :segment="segment"
            selectable
            :selected="selectedSet.has(item.order.id)"
            @open="(orderId) => emit('open', orderId)"
            @generate="(payload) => emit('generate', payload)"
            @rename-order="(payload) => emit('renameOrder', payload)"
            @toggle-select="(payload) => emit('toggleSelect', payload)"
          />
        </template>
        <tr v-if="!totalOrderCount">
          <td colspan="7" class="px-3 py-8 text-center text-sm text-gray-500 dark:text-slate-400">Заказы не найдены</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
