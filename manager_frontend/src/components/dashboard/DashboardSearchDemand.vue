<script setup lang="ts">
import { computed, ref } from 'vue';
import type { DashboardSearchDemand, DashboardSearchQuery } from '../../client';
import { formatMarketingValue, formatSearchDemandProvider } from '../../services/dashboard-overview';
import { downloadSearchDemandCsv } from '../../services/search-demand-export';

const props = defineProps<{ demand: DashboardSearchDemand }>();
type Source = 'all' | 'yandex_webmaster' | 'google_search_console';
type SortKey = 'query' | 'clicks' | 'impressions' | 'ctr' | 'avg_position';
type SortDirection = 'asc' | 'desc';

const activeSource = ref<Source>('all');
const expanded = ref(false);
const sortKey = ref<SortKey>('clicks');
const sortDirection = ref<SortDirection>('desc');
const tabs: Array<{ value: Source; label: string }> = [
  { value: 'all', label: 'Все источники' },
  { value: 'yandex_webmaster', label: 'Яндекс Вебмастер' },
  { value: 'google_search_console', label: 'Search Console' },
];
const sortOptions: Array<{ value: SortKey; label: string }> = [
  { value: 'clicks', label: 'Клики' },
  { value: 'impressions', label: 'Показы' },
  { value: 'ctr', label: 'CTR' },
  { value: 'avg_position', label: 'Позиция' },
];

const filteredQueries = computed(() => (props.demand.queries || []).filter(query => (
  activeSource.value === 'all' || query.provider === activeSource.value
)));
const sortedQueries = computed(() => [...filteredQueries.value].sort((left, right) => {
  const direction = sortDirection.value === 'asc' ? 1 : -1;
  if (sortKey.value === 'query') return left.query.localeCompare(right.query, 'ru') * direction;
  const leftValue = left[sortKey.value];
  const rightValue = right[sortKey.value];
  if (leftValue == null) return 1;
  if (rightValue == null) return -1;
  return (leftValue - rightValue) * direction;
}));
const visibleQueries = computed(() => expanded.value ? sortedQueries.value : sortedQueries.value.slice(0, 10));
const statusLabel = computed(() => ({
  fresh: 'Данные актуальны',
  stale: 'Данные обновляются с задержкой',
  error: 'Часть источников недоступна',
  unconfigured: 'Не подключено',
}[props.demand.status]));

const sourceAvailable = (source: Source) => source === 'all' || props.demand.providers?.some(provider => provider.provider === source);
const position = (value: number | null | undefined) => value == null ? '—' : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value);
const selectSource = (source: Source) => {
  activeSource.value = source;
  expanded.value = false;
};
const selectSort = (key: SortKey) => {
  if (sortKey.value === key) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc';
    return;
  }
  sortKey.value = key;
  sortDirection.value = key === 'query' || key === 'avg_position' ? 'asc' : 'desc';
};
const sortIndicator = (key: SortKey) => sortKey.value === key ? (sortDirection.value === 'asc' ? '↑' : '↓') : '';
const ariaSort = (key: SortKey) => sortKey.value === key ? (sortDirection.value === 'asc' ? 'ascending' : 'descending') : 'none';
const exportRows = () => downloadSearchDemandCsv(sortedQueries.value as DashboardSearchQuery[], activeSource.value);
</script>

<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div><h2 class="font-semibold text-slate-900 dark:text-white">Поисковый спрос</h2><p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Запросы, по которым люди находят сайт</p></div>
      <span class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-700 dark:text-slate-300">{{ statusLabel }}</span>
    </div>
    <p class="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600 dark:bg-slate-900/40 dark:text-slate-300">Поисковые системы передают агрегированные данные с задержкой, а редкие запросы могут скрываться для защиты приватности.</p>

    <div class="mt-4 flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Источник поисковых запросов">
      <button v-for="tab in tabs" :key="tab.value" type="button" role="tab" :aria-selected="activeSource === tab.value" :disabled="!sourceAvailable(tab.value)" class="shrink-0 rounded-lg px-3 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-45" :class="activeSource === tab.value ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-700'" @click="selectSource(tab.value)">{{ tab.label }}</button>
    </div>

    <div v-if="sortedQueries.length" class="mt-4">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-1 overflow-x-auto" aria-label="Сортировка запросов">
          <span class="mr-1 shrink-0 text-xs text-slate-500 dark:text-slate-400">Сортировать:</span>
          <button v-for="option in sortOptions" :key="option.value" type="button" class="shrink-0 rounded-md px-2 py-1 text-xs font-semibold" :class="sortKey === option.value ? 'bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300' : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700'" @click="selectSort(option.value)">{{ option.label }} {{ sortIndicator(option.value) }}</button>
        </div>
        <button type="button" class="shrink-0 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700" @click="exportRows">Скачать CSV ({{ sortedQueries.length }})</button>
      </div>

      <div class="hidden overflow-x-auto md:block">
        <table class="w-full min-w-[680px] text-left text-sm">
          <thead class="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400 dark:border-slate-700"><tr>
            <th class="px-3 py-2 font-semibold" :aria-sort="ariaSort('query')"><button type="button" @click="selectSort('query')">Запрос {{ sortIndicator('query') }}</button></th>
            <th class="px-3 py-2 font-semibold">Источник</th>
            <th class="px-3 py-2 text-right font-semibold" :aria-sort="ariaSort('clicks')"><button type="button" @click="selectSort('clicks')">Клики {{ sortIndicator('clicks') }}</button></th>
            <th class="px-3 py-2 text-right font-semibold" :aria-sort="ariaSort('impressions')"><button type="button" @click="selectSort('impressions')">Показы {{ sortIndicator('impressions') }}</button></th>
            <th class="px-3 py-2 text-right font-semibold" :aria-sort="ariaSort('ctr')"><button type="button" @click="selectSort('ctr')">CTR {{ sortIndicator('ctr') }}</button></th>
            <th class="px-3 py-2 text-right font-semibold" :aria-sort="ariaSort('avg_position')"><button type="button" @click="selectSort('avg_position')">Средняя позиция {{ sortIndicator('avg_position') }}</button></th>
          </tr></thead>
          <tbody><tr v-for="query in visibleQueries" :key="`${query.provider}:${query.query}`" class="border-b border-slate-100 last:border-0 dark:border-slate-700"><td class="max-w-sm px-3 py-3 font-medium text-slate-900 dark:text-white">{{ query.query }}</td><td class="px-3 py-3 text-slate-500 dark:text-slate-400">{{ formatSearchDemandProvider(query.provider) }}</td><td class="px-3 py-3 text-right text-slate-700 dark:text-slate-200">{{ formatMarketingValue(query.clicks) }}</td><td class="px-3 py-3 text-right text-slate-700 dark:text-slate-200">{{ formatMarketingValue(query.impressions) }}</td><td class="px-3 py-3 text-right text-slate-700 dark:text-slate-200">{{ formatMarketingValue(query.ctr, 'percent') }}</td><td class="px-3 py-3 text-right text-slate-700 dark:text-slate-200">{{ position(query.avg_position) }}</td></tr></tbody>
        </table>
      </div>
      <div class="space-y-3 md:hidden"><article v-for="query in visibleQueries" :key="`${query.provider}:${query.query}`" class="rounded-xl bg-slate-50 p-3 dark:bg-slate-900/40"><div class="flex items-start justify-between gap-3"><h3 class="min-w-0 font-semibold text-slate-900 dark:text-white">{{ query.query }}</h3><span class="shrink-0 text-xs text-slate-500 dark:text-slate-400">{{ formatSearchDemandProvider(query.provider) }}</span></div><dl class="mt-3 grid grid-cols-2 gap-3 text-sm"><div><dt class="text-xs text-slate-500 dark:text-slate-400">Клики</dt><dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{{ formatMarketingValue(query.clicks) }}</dd></div><div><dt class="text-xs text-slate-500 dark:text-slate-400">Показы</dt><dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{{ formatMarketingValue(query.impressions) }}</dd></div><div><dt class="text-xs text-slate-500 dark:text-slate-400">CTR</dt><dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{{ formatMarketingValue(query.ctr, 'percent') }}</dd></div><div><dt class="text-xs text-slate-500 dark:text-slate-400">Средняя позиция</dt><dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{{ position(query.avg_position) }}</dd></div></dl></article></div>
      <div v-if="sortedQueries.length > 10" class="mt-4 flex justify-center"><button type="button" class="rounded-lg bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-200 dark:hover:bg-slate-600" @click="expanded = !expanded">{{ expanded ? 'Свернуть до 10' : `Показать все (${sortedQueries.length})` }}</button></div>
    </div>
    <div v-else class="mt-4 rounded-xl border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">Подключите Яндекс Вебмастер или Google Search Console, чтобы увидеть запросы и позиции.</div>
  </section>
</template>
