<script setup lang="ts">
import { computed, ref } from 'vue';
import type { DashboardSearchDemand } from '../../client';
import { formatMarketingValue, formatSearchDemandProvider } from '../../services/dashboard-overview';

const props = defineProps<{ demand: DashboardSearchDemand }>();
type Source = 'all' | 'yandex_webmaster' | 'google_search_console';
const activeSource = ref<Source>('all');
const tabs: Array<{ value: Source; label: string }> = [
  { value: 'all', label: 'Все источники' },
  { value: 'yandex_webmaster', label: 'Яндекс Вебмастер' },
  { value: 'google_search_console', label: 'Search Console' },
];
const queries = computed(() => (props.demand.queries || []).filter(query => (
  activeSource.value === 'all' || query.provider === activeSource.value
)));
const statusLabel = computed(() => ({
  fresh: 'Данные актуальны',
  stale: 'Данные обновляются с задержкой',
  error: 'Часть источников недоступна',
  unconfigured: 'Не подключено',
}[props.demand.status]));
const sourceAvailable = (source: Source) => source === 'all' || props.demand.providers?.some(provider => provider.provider === source);
const position = (value: number | null | undefined) => value == null ? '—' : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value);
</script>

<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div><h2 class="font-semibold text-slate-900 dark:text-white">Поисковый спрос</h2><p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Запросы, по которым люди находят сайт</p></div>
      <span class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-700 dark:text-slate-300">{{ statusLabel }}</span>
    </div>
    <p class="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600 dark:bg-slate-900/40 dark:text-slate-300">Поисковые системы передают агрегированные данные с задержкой, а редкие запросы могут скрываться для защиты приватности.</p>

    <div class="mt-4 flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Источник поисковых запросов">
      <button v-for="tab in tabs" :key="tab.value" type="button" role="tab" :aria-selected="activeSource === tab.value" :disabled="!sourceAvailable(tab.value)" class="shrink-0 rounded-lg px-3 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-45" :class="activeSource === tab.value ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-700'" @click="activeSource = tab.value">{{ tab.label }}</button>
    </div>

    <div v-if="queries.length" class="mt-4">
      <div class="hidden overflow-x-auto md:block"><table class="w-full min-w-[680px] text-left text-sm"><thead class="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400 dark:border-slate-700"><tr><th class="px-3 py-2 font-semibold">Запрос</th><th class="px-3 py-2 font-semibold">Источник</th><th class="px-3 py-2 text-right font-semibold">Клики</th><th class="px-3 py-2 text-right font-semibold">Показы</th><th class="px-3 py-2 text-right font-semibold">CTR</th><th class="px-3 py-2 text-right font-semibold">Средняя позиция</th></tr></thead><tbody><tr v-for="query in queries" :key="`${query.provider}:${query.query}`" class="border-b border-slate-100 last:border-0 dark:border-slate-700"><td class="max-w-sm px-3 py-3 font-medium text-slate-900 dark:text-white">{{ query.query }}</td><td class="px-3 py-3 text-slate-500 dark:text-slate-400">{{ formatSearchDemandProvider(query.provider) }}</td><td class="px-3 py-3 text-right text-slate-700 dark:text-slate-200">{{ formatMarketingValue(query.clicks) }}</td><td class="px-3 py-3 text-right text-slate-700 dark:text-slate-200">{{ formatMarketingValue(query.impressions) }}</td><td class="px-3 py-3 text-right text-slate-700 dark:text-slate-200">{{ formatMarketingValue(query.ctr, 'percent') }}</td><td class="px-3 py-3 text-right text-slate-700 dark:text-slate-200">{{ position(query.avg_position) }}</td></tr></tbody></table></div>
      <div class="space-y-3 md:hidden"><article v-for="query in queries" :key="`${query.provider}:${query.query}`" class="rounded-xl bg-slate-50 p-3 dark:bg-slate-900/40"><div class="flex items-start justify-between gap-3"><h3 class="min-w-0 font-semibold text-slate-900 dark:text-white">{{ query.query }}</h3><span class="shrink-0 text-xs text-slate-500 dark:text-slate-400">{{ formatSearchDemandProvider(query.provider) }}</span></div><dl class="mt-3 grid grid-cols-2 gap-3 text-sm"><div><dt class="text-xs text-slate-500 dark:text-slate-400">Клики</dt><dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{{ formatMarketingValue(query.clicks) }}</dd></div><div><dt class="text-xs text-slate-500 dark:text-slate-400">Показы</dt><dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{{ formatMarketingValue(query.impressions) }}</dd></div><div><dt class="text-xs text-slate-500 dark:text-slate-400">CTR</dt><dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{{ formatMarketingValue(query.ctr, 'percent') }}</dd></div><div><dt class="text-xs text-slate-500 dark:text-slate-400">Средняя позиция</dt><dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{{ position(query.avg_position) }}</dd></div></dl></article></div>
    </div>
    <div v-else class="mt-4 rounded-xl border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">Подключите Яндекс Вебмастер или Google Search Console, чтобы увидеть запросы и позиции.</div>
  </section>
</template>
