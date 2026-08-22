<script setup lang="ts">
import type { DashboardMarketing } from '../../client';
import {
  dashboardMarketingStatus,
  formatMarketingProvider,
  formatMarketingValue,
} from '../../services/dashboard-overview';

const props = defineProps<{ marketing: DashboardMarketing }>();
const status = () => dashboardMarketingStatus(props.marketing);
const metrics = () => [
  ['Расход', formatMarketingValue(props.marketing.ad_spend, 'currency')],
  ['Клики', formatMarketingValue(props.marketing.clicks)],
  ['Показы', formatMarketingValue(props.marketing.impressions)],
  ['CTR', formatMarketingValue(props.marketing.ctr, 'percent')],
  ['CPL', formatMarketingValue(props.marketing.cost_per_lead, 'currency')],
  ['CAC', formatMarketingValue(props.marketing.customer_acquisition_cost, 'currency')],
];
</script>

<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="font-semibold text-slate-900 dark:text-white">Маркетинг</h2>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{{ formatMarketingProvider(marketing.provider) }}</p>
      </div>
      <span class="rounded-full px-2.5 py-1 text-xs font-semibold" :class="{ 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300': status().tone === 'fresh', 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300': status().tone === 'stale', 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300': status().tone === 'error', 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300': status().tone === 'unconfigured' }">{{ status().label }}</span>
    </div>
    <p class="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:bg-slate-900/40 dark:text-slate-300">{{ status().message }}</p>
    <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3"><div class="rounded-lg bg-slate-50 p-3 dark:bg-slate-900/40"><p class="text-xs text-slate-500 dark:text-slate-400">Визиты</p><p class="mt-1 text-lg font-semibold text-slate-900 dark:text-white">{{ formatMarketingValue(marketing.visits) }}</p></div><div v-for="([label, value]) in metrics()" :key="label" class="rounded-lg bg-slate-50 p-3 dark:bg-slate-900/40"><p class="text-xs text-slate-500 dark:text-slate-400">{{ label }}</p><p class="mt-1 text-lg font-semibold text-slate-900 dark:text-white">{{ value }}</p></div></div>
    <div v-if="marketing.sources?.length" class="mt-4 border-t border-slate-100 pt-3 dark:border-slate-700"><p class="text-xs font-semibold uppercase tracking-wide text-slate-400">Источники</p><div class="mt-2 space-y-2"><div v-for="source in marketing.sources" :key="source.name" class="flex items-center justify-between gap-3 text-sm"><span class="min-w-0 truncate text-slate-600 dark:text-slate-300">{{ source.name }}</span><span class="shrink-0 font-medium text-slate-900 dark:text-white">{{ formatMarketingValue(source.visits) }} · {{ formatMarketingValue(source.share_pct, 'percent') }}</span></div></div></div>
    <p v-else class="mt-4 text-sm text-slate-500 dark:text-slate-400">Источники не подключены.</p>
  </section>
</template>
