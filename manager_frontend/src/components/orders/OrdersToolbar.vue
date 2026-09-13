<script setup lang="ts">
import { Download, Search, SlidersHorizontal, Upload, X } from 'lucide-vue-next';
import type { DashboardView, Segment } from '../../api';
import { STATUS_LABELS, STATUS_ORDER } from './order-utils';
import { ORDER_WORK_FILTERS, type OrderWorkFilter } from './order-work-filters';
import OrdersTabSwitcher from './OrdersTabSwitcher.vue';
import OrdersViewToggle from './OrdersViewToggle.vue';

const segment = defineModel<Segment>('segment', { required: true });
const view = defineModel<DashboardView>('view', { required: true });
const search = defineModel<string>('search', { required: true });
const statusFilter = defineModel<string>('statusFilter', { required: true });
const workFilter = defineModel<OrderWorkFilter>('workFilter', { required: true });
const groupByCustomer = defineModel<boolean>('groupByCustomer', { required: true });
const hideOnHold = defineModel<boolean>('hideOnHold', { required: true });
const filtersOpen = defineModel<boolean>('filtersOpen', { required: true });

defineProps<{
  counts: Record<OrderWorkFilter, number>;
  hiddenOnHoldCount: number;
  visibleCount: number;
  selectedCount: number;
  hasActiveFilters: boolean;
  loading: boolean;
  loadFailed: boolean;
  transferLoading: boolean;
}>();
const emit = defineEmits<{
  reset: [];
  searchNow: [];
  import: [];
  export: [];
  selectAll: [];
  clearSelection: [];
}>();
</script>

<template>
  <header class="mb-4 rounded-xl border border-gray-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
    <div class="flex flex-wrap items-center gap-3">
      <h1 class="text-xl font-bold dark:text-white">Заказы</h1>
      <OrdersTabSwitcher v-model="segment" />
      <div class="ml-auto flex items-center gap-2">
        <OrdersViewToggle v-model="view" />
        <button type="button" class="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-gray-200 px-2 text-sm text-gray-700 dark:border-slate-600 dark:text-slate-200"
          :aria-expanded="filtersOpen" aria-controls="orders-options" @click="filtersOpen = !filtersOpen">
          <SlidersHorizontal class="h-4 w-4" /> Опции
        </button>
      </div>
    </div>
    <form class="relative mt-3" role="search" @submit.prevent="emit('searchNow')">
      <Search class="pointer-events-none absolute left-3 top-3 h-4 w-4 text-gray-500" />
      <input v-model="search" type="search" aria-label="Поиск заказов" placeholder="Клиент, телефон, УНП, название или номер заказа"
        class="h-10 w-full min-w-0 rounded-lg border border-gray-300 bg-white pl-9 pr-10 text-sm text-gray-900 dark:border-slate-600 dark:bg-slate-900 dark:text-white" />
      <button v-if="search" type="button" aria-label="Очистить поиск заказов" class="absolute right-1 top-1 rounded p-2 text-gray-500" @click="search = ''">
        <X class="h-4 w-4" />
      </button>
    </form>
    <div class="mt-3 flex flex-wrap items-center gap-2" aria-label="Рабочие фильтры">
      <button v-for="filter in ORDER_WORK_FILTERS" :key="filter.value" type="button"
        class="inline-flex min-h-9 items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition"
        :class="workFilter === filter.value ? 'bg-brand-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-slate-700 dark:text-slate-200 dark:hover:bg-slate-600'"
        :aria-pressed="workFilter === filter.value" @click="workFilter = filter.value">
        {{ filter.label }} <span v-if="!loading && !loadFailed" class="text-xs tabular-nums">{{ counts[filter.value] }}</span>
      </button>
    </div>
    <div v-if="filtersOpen" id="orders-options" class="mt-3 flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-gray-200 pt-3 text-sm dark:border-slate-700">
      <label class="flex items-center gap-2">Этап
        <select v-model="statusFilter" class="rounded-lg border border-gray-300 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-900">
          <option value="">Все этапы</option>
          <option v-for="statusKey in STATUS_ORDER" :key="statusKey" :value="statusKey">{{ STATUS_LABELS[statusKey] }}</option>
        </select>
      </label>
      <label class="flex items-center gap-2"><input v-model="groupByCustomer" type="checkbox" /> По клиентам</label>
      <label class="flex items-center gap-2"><input v-model="hideOnHold" type="checkbox" /> Скрывать отложенные</label>
      <button type="button" class="ml-auto inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-gray-600 disabled:opacity-50 dark:text-slate-300"
        :disabled="transferLoading" @click="emit('import')"><Upload class="h-4 w-4" /> Импорт заказов</button>
    </div>
    <div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-gray-600 dark:text-slate-300">
      <span role="status">{{ loading ? 'Загрузка заказов…' : loadFailed ? 'Заказы не загружены' : `По фильтрам: ${visibleCount}` }}</span>
      <span v-if="statusFilter">Этап: {{ STATUS_LABELS[statusFilter] }}</span>
      <button v-if="hideOnHold" type="button" class="text-brand-700 hover:underline dark:text-brand-300" @click="hideOnHold = false">
        Отложенные скрыты<span v-if="!loading && !loadFailed">: {{ hiddenOnHoldCount }}</span> · Показать
      </button>
      <button v-if="hasActiveFilters" type="button" class="inline-flex items-center gap-1 hover:underline" @click="emit('reset')"><X class="h-3 w-3" /> Сбросить фильтры</button>
      <template v-if="view === 'list'">
        <button type="button" class="ml-auto text-brand-700 disabled:opacity-50 dark:text-brand-300" :disabled="!visibleCount || loading || loadFailed" @click="emit('selectAll')">Выбрать показанные</button>
        <template v-if="selectedCount">
          <span>Выбрано: {{ selectedCount }}</span>
          <button type="button" @click="emit('clearSelection')">Снять выбор</button>
        </template>
      </template>
      <button v-if="selectedCount" type="button" class="inline-flex items-center gap-1 text-brand-700 disabled:opacity-50 dark:text-brand-300" :disabled="transferLoading" @click="emit('export')"><Download class="h-4 w-4" /> Экспорт {{ selectedCount }}</button>
    </div>
    <p v-if="workFilter === 'unpaid'" class="mt-2 text-xs text-gray-500 dark:text-slate-400">Остаток — сумма заказа за вычетом оплат. Он не означает просрочку платежа.</p>
    <p v-else-if="workFilter === 'planning'" class="mt-2 text-xs text-gray-500 dark:text-slate-400">Согласованные предложения и заказы, для которых нужно назначить работы.</p>
    <p v-else-if="workFilter === 'followup'" class="mt-2 text-xs text-gray-500 dark:text-slate-400">Активные заказы, по которым прошла дата следующего контакта.</p>
  </header>
</template>
