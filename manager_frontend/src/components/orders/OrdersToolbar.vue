<script setup lang="ts">
import { computed, nextTick, ref, watch, onMounted, onBeforeUnmount } from 'vue';
import { Download, Search, Upload, X } from 'lucide-vue-next';
import type { DashboardView, Segment } from '../../api';
import { STATUS_LABELS, STATUS_ORDER } from './order-utils';
import { ORDER_WORK_FILTERS, type OrderWorkFilter } from './order-work-filters';
import OrdersTabSwitcher from './OrdersTabSwitcher.vue';
import OrdersViewToggle from './OrdersViewToggle.vue';
import ManagerContextHeader from '../manager/ManagerContextHeader.vue';
import OrderDropTargets from './OrderDropTargets.vue';
import { useSharedOrderBoardDrag } from '../../composables/useOrderBoardDrag';

const assignedToMe = defineModel<boolean>('assignedToMe', { default: false });
const segment = defineModel<Segment>('segment', { required: true });
const view = defineModel<DashboardView>('view', { required: true });
const search = defineModel<string>('search', { required: true });
const statusFilter = defineModel<string>('statusFilter', { required: true });
const workFilter = defineModel<OrderWorkFilter>('workFilter', { required: true });
const groupByCustomer = defineModel<boolean>('groupByCustomer', { required: true });
const filtersOpen = defineModel<boolean>('filtersOpen', { required: true });
const props = defineProps<{
  canFilterMine?: boolean;
  counts: Record<OrderWorkFilter, number>;
  hiddenOnHoldCount: number;
  visibleCount: number;
  selectedCount: number;
  hasActiveFilters: boolean;
  extraSummary?: string[];
  loading: boolean;
  loadFailed: boolean;
  transferLoading: boolean;
}>();
const emit = defineEmits<{
  move: [payload: { orderId: number; oldStatus: string; newStatus: string }];
  reset: []; searchNow: []; import: []; export: []; selectAll: []; clearSelection: [];
}>();
const drag = useSharedOrderBoardDrag();
watch(() => drag?.source.value, source => { if (source) filtersOpen.value = false; }, { flush: 'sync' });
const toolbar = ref<HTMLElement | null>(null);
const searchInput = ref<HTMLInputElement | null>(null);
const toggleButton = ref<HTMLButtonElement | null>(null);
const summary = computed(() => [
  { all: 'Все клиенты', b2b: 'B2B', b2c: 'B2C' }[segment.value],
  assignedToMe.value ? 'Мои заказы' : '',
  workFilter.value !== 'all' ? ORDER_WORK_FILTERS.find(filter => filter.value === workFilter.value)?.label : '',
  statusFilter.value ? `Этап: ${STATUS_LABELS[statusFilter.value]}` : '',
  groupByCustomer.value ? 'По клиентам' : '',
  view.value === 'list' ? 'Таблица' : '',
  search.value.trim() ? `Поиск: «${search.value.trim()}» — все очереди` : '',
  ...(props.extraSummary || []),
].filter(Boolean).join(' · '));
const openFilters = async () => {
  filtersOpen.value = true;
  await nextTick(); searchInput.value?.focus({ preventScroll: true });
};
const closeFilters = async () => {
  filtersOpen.value = false;
  await nextTick(); toggleButton.value?.focus({ preventScroll: true });
};
const outside = (event: MouseEvent) => {
  if (filtersOpen.value && event.target instanceof Node && !toolbar.value?.contains(event.target)) filtersOpen.value = false;
};
onMounted(() => document.addEventListener('click', outside, true));
onBeforeUnmount(() => document.removeEventListener('click', outside, true));
</script>

<template>
  <ManagerContextHeader>
  <div ref="toolbar" class="orders-toolbar">
    <h1 class="sr-only">Заказы</h1>
    <div class="orders-primary-controls">
      <OrderDropTargets v-if="drag?.source.value" :drag="drag" @move="emit('move', $event)" />
      <div v-else class="min-w-0 flex-1"><slot name="queues" /></div>
      <button ref="toggleButton" type="button" class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-gray-200 px-2 text-sm text-gray-700 dark:border-slate-600 dark:text-slate-200"
        aria-label="Поиск и фильтры" :aria-expanded="filtersOpen" aria-controls="orders-options" @click="filtersOpen ? closeFilters() : openFilters()">
        <X v-if="filtersOpen" class="h-4 w-4" /><Search v-else class="h-4 w-4" /><span class="orders-search-label">{{ filtersOpen ? 'Закрыть' : 'Поиск и фильтры' }}</span>
      </button>
    </div>
    <div class="orders-secondary-controls">
      <OrdersTabSwitcher v-model="segment" />
      <button type="button" class="orders-condition-summary min-w-0 flex-1 truncate text-left hover:text-brand-700" :title="summary" :aria-label="`Условия: ${summary}. Открыть фильтры`" @click="openFilters">{{ summary }}</button>
      <span role="status" class="orders-result-count shrink-0 text-[11px]">{{ loading ? 'Загрузка заказов…' : loadFailed ? 'Ошибка загрузки' : `По фильтрам: ${visibleCount}` }}</span>
    </div>
    <section v-show="filtersOpen" id="orders-options" aria-label="Поиск и настройки заказов" class="orders-filter-panel space-y-3 text-sm" @keydown.esc.stop.prevent="closeFilters">
      <form class="relative" role="search" @submit.prevent="emit('searchNow')">
        <Search class="pointer-events-none absolute left-3 top-3 h-4 w-4 text-gray-500" />
        <input ref="searchInput" v-model="search" type="search" aria-label="Поиск заказов" placeholder="Клиент, телефон, УНП, название или номер заказа"
          class="h-10 w-full min-w-0 rounded-lg border border-gray-300 bg-white pl-9 pr-10 text-sm text-gray-900 dark:border-slate-600 dark:bg-slate-900 dark:text-white" />
        <button v-if="search" type="button" aria-label="Очистить поиск заказов" class="absolute right-1 top-1 rounded p-2 text-gray-500" @click="search = ''"><X class="h-4 w-4" /></button>
      </form>
      <p v-if="search.trim()" class="text-xs text-gray-500">Поиск во всех очередях. Очередь указана рядом с заказом.</p>
      <div class="flex flex-wrap items-center gap-2">
        <button type="button" class="inline-flex min-h-9 items-center rounded-lg border px-3 py-1.5 text-sm font-semibold disabled:opacity-40" :class="assignedToMe ? 'border-brand-600 bg-brand-600 text-white' : 'border-gray-200 text-gray-700 dark:border-slate-600 dark:text-slate-200'" :aria-pressed="assignedToMe" :disabled="!canFilterMine" :title="canFilterMine ? 'Показать заказы, где вы назначены ответственным' : 'Нужна личная учётная запись'" @click="assignedToMe = !assignedToMe">Мои заказы</button>
        <OrdersViewToggle v-model="view" />
      </div>
      <div class="flex flex-wrap items-center gap-2" aria-label="Рабочие фильтры">
        <button v-for="filter in ORDER_WORK_FILTERS" :key="filter.value" type="button" class="inline-flex min-h-9 items-center gap-2 rounded-lg px-3 py-1.5 text-sm"
          :class="workFilter === filter.value ? 'bg-brand-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-slate-700 dark:text-slate-200'" :aria-pressed="workFilter === filter.value" @click="workFilter = filter.value">
          {{ filter.label }} <span v-if="!loading && !loadFailed" class="text-xs tabular-nums">{{ counts[filter.value] }}</span>
        </button>
      </div>
      <div class="flex flex-wrap items-center gap-x-5 gap-y-3">
        <label class="flex items-center gap-2">Этап <select v-model="statusFilter" class="rounded-lg border border-gray-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900"><option value="">Все этапы</option><option v-for="statusKey in STATUS_ORDER" :key="statusKey" :value="statusKey">{{ STATUS_LABELS[statusKey] }}</option></select></label>
        <label class="flex items-center gap-2"><input v-model="groupByCustomer" type="checkbox" /> По клиентам</label>
        <slot name="filters" />
      </div>
      <div class="flex flex-wrap items-center gap-x-3 gap-y-2 border-t pt-2 text-xs dark:border-slate-700">
        <button v-if="hasActiveFilters" type="button" class="inline-flex min-h-9 items-center gap-1 hover:underline" @click="emit('reset')"><X class="h-3 w-3" /> Сбросить фильтры</button>
        <template v-if="view === 'list'">
          <button type="button" class="min-h-9 text-brand-700 disabled:opacity-50 dark:text-brand-300" :disabled="!visibleCount || loading || loadFailed" @click="emit('selectAll')">Выбрать показанные</button>
          <template v-if="selectedCount"><span>Выбрано: {{ selectedCount }}</span><button type="button" class="min-h-9" @click="emit('clearSelection')">Снять выбор</button></template>
        </template>
        <button v-if="selectedCount" type="button" class="inline-flex min-h-9 items-center gap-1 text-brand-700 disabled:opacity-50 dark:text-brand-300" :disabled="transferLoading" @click="emit('export')"><Download class="h-4 w-4" /> Экспорт {{ selectedCount }}</button>
        <button type="button" class="inline-flex min-h-9 items-center gap-1.5 text-gray-600 disabled:opacity-50 dark:text-slate-300" :disabled="transferLoading" @click="emit('import')"><Upload class="h-4 w-4" /> Импорт заказов</button>
        <button type="button" class="ml-auto min-h-9 rounded-lg bg-brand-600 px-3 text-sm font-semibold text-white" aria-label="Закрыть фильтры" @click="closeFilters">К заказам</button>
      </div>
      <p v-if="workFilter === 'unpaid'" class="text-xs text-gray-500">Остаток — сумма заказа за вычетом оплат. Он не означает просрочку платежа.</p>
      <p v-else-if="workFilter === 'planning'" class="text-xs text-gray-500">Согласованные предложения и заказы, для которых нужно назначить работы.</p>
      <p v-else-if="workFilter === 'followup'" class="text-xs text-gray-500">Контакты из активных и ожидающих заказов. Ожидание не снимается.</p>
    </section>
  </div>
  </ManagerContextHeader>
</template>

<style scoped>
.orders-toolbar { position:relative; min-width:0; }
.orders-primary-controls { display:flex; align-items:center; gap:0.5rem; min-width:0; }
.orders-secondary-controls { display:flex; align-items:center; gap:0.5rem; min-width:0; margin-top:0.25rem; font-size:0.75rem; color:var(--kitlane-muted); }
.orders-filter-panel { position:absolute; top:calc(100% + 0.5rem); left:0; z-index:45; width:min(640px, 100%); max-height:calc(100dvh - var(--kitlane-sticky-header-height, var(--kitlane-header-height)) - 24px); overflow-y:auto; padding:0.75rem; border:1px solid var(--kitlane-border); border-radius:0.75rem; background:var(--kitlane-surface); box-shadow:0 16px 40px rgb(15 23 42 / 0.2); color:var(--kitlane-text); }
.orders-search-label { display:none; }
@media (min-width:1440px) { .orders-search-label { display:inline; } }
@media (max-width:767px) {
  .orders-secondary-controls { gap:0.375rem; }
}
</style>
