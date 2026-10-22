<script setup lang="ts">
import { computed, nextTick, ref } from 'vue';
import type { ManagerOrderBoardPage } from '../../client';
import type { Segment } from '../../api';
import type { OrderBoardState } from '../../services/order-navigation';
import { orderQueueLabel } from '../../services/order-board';
import { formatDate, formatMoney, NEGOTIATION_STATUS_OPTIONS, EXECUTION_STATUS_OPTIONS, getOrderSegment } from './order-utils';
import OrdersListTable from './OrdersListTable.vue';
import { promptDialog } from '../../services/ui-feedback';
import OrderCardB2B from './OrderCardB2B.vue';
import OrderCardB2C from './OrderCardB2C.vue';

const props = defineProps<{
  phases: Record<string, string>; pages: Record<string, ManagerOrderBoardPage>; columns: string[];
  busy: Record<string, boolean>; errors: Record<string, string>;
  listMode?: boolean; sort?: string; selectedOrderIds?: number[]; customerAliases?: Record<number, string>;
  segment: Segment; movingOrderIds: number[]; compact: boolean; showQueue: boolean;
}>();
const emit = defineEmits<{
  'update:sort': [sort: string]; toggleSelect: [payload: { orderId: number; selected: boolean }];
  toggleSelectMany: [payload: { orderIds: number[]; selected: boolean }];
  renameCustomer: [payload: { customerId: number; alias: string | null }];
  open: [id: number]; generate: [payload: { orderId: number; docType: string }];
  move: [payload: { orderId: number; oldStatus: string; newStatus: string }];
  cancelOrder: [payload: { orderId: number }]; closeDebt: [payload: { orderId: number }];
  renameOrder: [payload: { orderId: number; title: string | null }];
  more: [column: string, group?: string]; phase: [column: string, phase: string];
}>();
const expanded = ref<string[]>([]);
const expandedOrder = ref<number | null>(null);
const mobileColumn = ref('negotiation');
const scrollers = new Map<string, HTMLElement>();
const renameGroup = async (id: number, name: string) => {
  const alias = await promptDialog({ title: 'Название группы', inputLabel: 'Локальное название', initialValue: props.customerAliases?.[id] || name });
  if (alias !== null) emit('renameCustomer', { customerId: id, alias: alias.trim() || null });
};
const labels: Record<string, string> = { negotiation: 'Переговоры', execution: 'Работы', '': 'Заказы' };
const drag = ref<{ orderId: number; oldStatus: string } | null>(null);
const isBoard = computed(() => props.columns.length > 1);
const toggle = (column: string, key: string) => {
  const id = `${column}/${key}`;
  if (expanded.value.includes(id)) expanded.value = expanded.value.filter(value => value !== id);
  else { expanded.value.push(id); if (!props.pages[id]) emit('more', column, key); }
};
const drop = (column: string) => {
  if (drag.value) emit('move', { ...drag.value, newStatus: props.phases[column] ? column === 'execution' ? `execution:${props.phases[column]}` : props.phases[column]! : column });
  drag.value = null;
};
defineExpose({
  captureState: (): OrderBoardState => ({ expandedOrderId: expandedOrder.value, expandedGroupIds: [...expanded.value], columnFilters: { ...props.phases }, scrollLeft: 0,
    columnScrollTops: Object.fromEntries([...scrollers].map(([key, element]) => [key, element.scrollTop])),
    loadedPages: Object.fromEntries(Object.entries(props.pages).map(([key, value]) => [key, value.page])), mobileColumn: mobileColumn.value }),
  restoreState: async (state: OrderBoardState) => {
    expandedOrder.value = state.expandedOrderId;
    expanded.value = [...state.expandedGroupIds];
    mobileColumn.value = state.mobileColumn || 'negotiation';
    await nextTick();
    for (const [key, top] of Object.entries(state.columnScrollTops || {})) {
      const element = scrollers.get(key); if (element) element.scrollTop = top;
    }
  },
});
</script>

<template>
  <div class="queue-workspace">
    <label v-if="listMode && Object.values(pages).some(page => page.groups?.length)" class="mb-2 text-sm">Сортировка
      <select :value="sort" aria-label="Сортировка заказов" class="rounded border bg-white p-2 dark:bg-slate-800" @change="emit('update:sort', ($event.target as HTMLSelectElement).value)"><option value="created_at_desc">Сначала новые</option><option value="created_at_asc">Сначала старые</option><option value="followup_asc">Ближайший контакт</option><option value="margin_desc">По марже</option></select>
    </label>
    <label v-if="isBoard" class="mb-2 flex items-center gap-2 text-sm md:hidden">Колонка
      <select v-model="mobileColumn" aria-label="Колонка доски" class="rounded border bg-white p-2 dark:bg-slate-800">
        <option v-for="column in columns" :key="column" :value="column">{{ labels[column] }}</option>
      </select>
    </label>
    <div class="queue-columns" :class="{ 'queue-columns-board': isBoard }">
      <section v-for="column in columns" :key="column" class="queue-column rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800"
        :class="{ 'mobile-inactive': isBoard && mobileColumn !== column }" @dragover.prevent @drop.prevent="drop(column)">
        <header class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b p-3 font-semibold dark:border-slate-700">
          <h2>{{ labels[column] }} <span v-if="pages[column]" class="text-sm tabular-nums">{{ pages[column].total_orders }}</span></h2>
          <select v-if="column" :value="phases[column] || ''" :aria-label="`Подэтап: ${labels[column]}`" class="max-w-[180px] rounded border bg-white p-1 text-sm dark:bg-slate-800" @change="emit('phase', column, ($event.target as HTMLSelectElement).value)">
            <option value="">Все подэтапы</option>
            <option v-for="option in column === 'negotiation' ? NEGOTIATION_STATUS_OPTIONS : EXECUTION_STATUS_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </header>
        <div :ref="element => { if (element) scrollers.set(column, element as HTMLElement); else scrollers.delete(column); }" class="queue-scroll space-y-3 p-3">
          <div v-if="errors[column]" role="alert" class="text-red-700">{{ errors[column] }} <button v-if="!pages[column]" type="button" class="rounded border px-3 py-2" @click="emit('more', column)">Повторить</button></div>
          <p v-if="!pages[column] && busy[column]" role="status">Загрузка…</p>
          <template v-if="pages[column]">
            <template v-for="group in pages[column].groups" :key="`${column}/${group.key}`">
              <template v-if="group.count === 1 && pages[column].items?.some(order => order.id === group.order_id)">
                <OrdersListTable v-if="listMode" :items="(pages[column].items || []).filter(order => order.id === group.order_id).map(order => ({ type: 'order' as const, order }))" :segment="segment" :sort="sort" :selected-order-ids="selectedOrderIds" :show-queue="showQueue" @open="emit('open', $event)" @generate="emit('generate', $event)" @rename-order="emit('renameOrder', $event)" @update:sort="emit('update:sort', $event)" @toggle-select="emit('toggleSelect', $event)" />
                <template v-for="order in listMode ? [] : (pages[column].items || []).filter(order => order.id === group.order_id)" :key="order.id">
                  <component :is="getOrderSegment(order) === 'b2b' ? OrderCardB2B : OrderCardB2C" :order="order" :expanded="expandedOrder === order.id" :draggable-disabled="movingOrderIds.includes(order.id)"
                    @open="emit('open', $event)" @toggle-expanded="expandedOrder = expandedOrder === $event ? null : $event" @generate="emit('generate', $event)" @quick-status="emit('move', { orderId: $event.orderId, oldStatus: order.status, newStatus: $event.status })" @cancel-order="emit('cancelOrder', $event)" @close-debt="emit('closeDebt', $event)" @rename-order="emit('renameOrder', $event)" @drag-start="drag = $event" />
                  <p v-if="order.is_on_hold && order.status !== 'closed'" class="text-xs text-amber-800 dark:text-amber-300">Ожидание: {{ order.on_hold_reason || 'Причина не указана' }} · {{ order.next_followup_date ? `Контакт ${formatDate(order.next_followup_date)}` : 'Без срока контакта' }}<template v-if="order.installation_date"> · Выезд {{ formatDate(order.installation_date) }}</template></p>
                </template>
              </template>
            <article v-else class="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-600 dark:bg-slate-900">
              <button type="button" class="w-full text-left" :aria-expanded="expanded.includes(`${column}/${group.key}`)" @click="toggle(column, group.key)">
                <strong class="block break-words">{{ group.customer_id && customerAliases?.[group.customer_id] || group.customer_name }}</strong>
                <span class="text-xs">{{ group.count }} заказов · Сумма {{ formatMoney(group.total_amount) }} · Остаток {{ formatMoney(group.balance_due) }}<template v-if="group.margin != null"> · Маржа {{ formatMoney(group.margin) }}</template></span>
                <span class="mt-1 block text-xs text-brand-700">{{ expanded.includes(`${column}/${group.key}`) ? 'Свернуть' : 'Показать заказы' }}</span>
              </button>
              <button v-if="group.customer_id" type="button" class="mt-1 text-xs text-slate-500 underline" @click="renameGroup(group.customer_id, group.customer_name)">Переименовать группу</button>
              <div v-if="expanded.includes(`${column}/${group.key}`)" class="mt-3 space-y-2">
                <OrdersListTable v-if="listMode && pages[`${column}/${group.key}`]?.items?.length" :items="(pages[`${column}/${group.key}`]?.items || []).map(order => ({ type: 'order' as const, order }))" :segment="segment" :sort="sort" :selected-order-ids="selectedOrderIds" :show-queue="showQueue" @open="emit('open', $event)" @generate="emit('generate', $event)" @rename-order="emit('renameOrder', $event)" @update:sort="emit('update:sort', $event)" @toggle-select="emit('toggleSelect', $event)" @toggle-select-many="emit('toggleSelectMany', $event)" />
                <div v-for="order in listMode ? [] : pages[`${column}/${group.key}`]?.items || []" :key="order.id">
                  <label v-if="listMode" class="flex items-center gap-2 text-xs"><input type="checkbox" :aria-label="`Выбрать заказ ${order.id}`" :checked="selectedOrderIds?.includes(order.id)" @change="emit('toggleSelect', { orderId: order.id, selected: ($event.target as HTMLInputElement).checked })" /> #{{ order.id }}</label>
                  <p v-if="showQueue" class="text-xs text-slate-500">{{ orderQueueLabel(order) }}</p>
                  <component :is="getOrderSegment(order) === 'b2b' ? OrderCardB2B : OrderCardB2C" :order="order" :expanded="expandedOrder === order.id" :draggable-disabled="movingOrderIds.includes(order.id)"
                    @open="emit('open', $event)" @toggle-expanded="expandedOrder = expandedOrder === $event ? null : $event" @generate="emit('generate', $event)" @quick-status="emit('move', { orderId: $event.orderId, oldStatus: order.status, newStatus: $event.status })" @cancel-order="emit('cancelOrder', $event)" @close-debt="emit('closeDebt', $event)" @rename-order="emit('renameOrder', $event)" @drag-start="drag = $event" />
                  <p v-if="order.is_on_hold && order.status !== 'closed'" class="mt-1 text-xs text-amber-800 dark:text-amber-300">Ожидание: {{ order.on_hold_reason || 'Причина не указана' }} · {{ order.next_followup_date ? `Контакт ${formatDate(order.next_followup_date)}` : 'Без срока контакта' }}<template v-if="order.installation_date"> · Выезд {{ formatDate(order.installation_date) }}</template></p>
                </div>
                <p v-if="errors[`${column}/${group.key}`]" role="alert" class="text-sm text-red-700">{{ errors[`${column}/${group.key}`] }}</p>
                <p class="text-xs text-slate-500">Загружено {{ pages[`${column}/${group.key}`]?.items?.length || 0 }} из {{ group.count }}. Итоги выше — по всей группе.</p>
                <button v-if="!pages[`${column}/${group.key}`] || pages[`${column}/${group.key}`]?.has_more" type="button" class="rounded border px-3 py-2 text-sm" :disabled="busy[`${column}/${group.key}`]" @click="emit('more', column, group.key)">{{ busy[`${column}/${group.key}`] ? 'Загрузка…' : errors[`${column}/${group.key}`] ? 'Повторить' : 'Ещё заказы' }}</button>
              </div>
            </article>
            </template>
            <OrdersListTable v-if="listMode && !compact && !pages[column].groups?.length && pages[column].items?.length" :items="(pages[column].items || []).map(order => ({ type: 'order' as const, order }))" :segment="segment" :sort="sort" :selected-order-ids="selectedOrderIds" :show-queue="showQueue" @open="emit('open', $event)" @generate="emit('generate', $event)" @rename-order="emit('renameOrder', $event)" @update:sort="emit('update:sort', $event)" @toggle-select="emit('toggleSelect', $event)" @toggle-select-many="emit('toggleSelectMany', $event)" />
            <div v-for="order in pages[column].groups?.length || listMode && !compact ? [] : pages[column].items" :key="order.id">
              <label v-if="listMode" class="flex items-center gap-2 text-xs"><input type="checkbox" :aria-label="`Выбрать заказ ${order.id}`" :checked="selectedOrderIds?.includes(order.id)" @change="emit('toggleSelect', { orderId: order.id, selected: ($event.target as HTMLInputElement).checked })" /> Выбрать</label>
              <p v-if="showQueue" class="mb-1 text-xs text-slate-500">{{ orderQueueLabel(order) }}</p>
              <button v-if="compact || order.status === 'closed'" type="button" class="flex w-full flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border p-3 text-left text-sm hover:bg-slate-50 dark:border-slate-600 dark:hover:bg-slate-700" @click="emit('open', order.id)">
                <strong class="min-w-0 flex-1 break-words">#{{ order.id }} · {{ order.title || order.customer?.name || 'Без названия' }}</strong>
                <span>{{ order.closing_result === 'won' ? 'Успех' : order.closing_result === 'lost' ? 'Отказ' : 'Результат не указан' }}</span>
                <span>{{ order.closed_at ? formatDate(order.closed_at) : 'Дата закрытия не указана' }}</span>
                <span>{{ formatMoney(order.total_amount) }}</span>
              </button>
              <template v-else>
                <component :is="getOrderSegment(order) === 'b2b' ? OrderCardB2B : OrderCardB2C" :order="order" :expanded="expandedOrder === order.id" :draggable-disabled="movingOrderIds.includes(order.id)"
                  @open="emit('open', $event)" @toggle-expanded="expandedOrder = expandedOrder === $event ? null : $event" @generate="emit('generate', $event)" @quick-status="emit('move', { orderId: $event.orderId, oldStatus: order.status, newStatus: $event.status })" @cancel-order="emit('cancelOrder', $event)" @close-debt="emit('closeDebt', $event)" @rename-order="emit('renameOrder', $event)" @drag-start="drag = $event" />
                <p v-if="order.is_on_hold && order.status !== 'closed'" class="mt-1 text-xs text-amber-800 dark:text-amber-300">Ожидание: {{ order.on_hold_reason || 'Причина не указана' }} · {{ order.next_followup_date ? `Контакт ${formatDate(order.next_followup_date)}` : 'Без срока контакта' }}<template v-if="order.installation_date"> · Выезд {{ formatDate(order.installation_date) }}</template></p>
              </template>
            </div>
            <p v-if="!pages[column].total" class="py-6 text-center text-sm text-slate-500">Заказов под выбранный фильтр нет.</p>
            <button v-if="pages[column]?.has_more" type="button" class="w-full rounded-lg border px-3 py-2 text-sm" :disabled="busy[column]" @click="emit('more', column)">{{ busy[column] ? 'Загрузка…' : errors[column] ? 'Повторить загрузку' : 'Показать ещё' }}</button>
          </template>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.queue-workspace { display:flex; flex:1; min-height:0; flex-direction:column; }
.queue-columns { display:flex; flex:1; min-height:0; gap:1rem; }
.queue-column { display:flex; flex:1; min-width:0; min-height:0; flex-direction:column; }
.queue-scroll { position:relative; overflow-y:auto; min-height:0; flex:1; overscroll-behavior:contain; }
@media (max-width:767px) {
  .mobile-inactive { display:none; }
  .queue-workspace, .queue-columns { flex:none; }
  .queue-column { flex:none; width:100%; }
  .queue-scroll { overflow:visible; flex:none; }
  .queue-column > header { position:sticky; top:var(--kitlane-header-height); z-index:10; background:var(--kitlane-surface); }
}
</style>
