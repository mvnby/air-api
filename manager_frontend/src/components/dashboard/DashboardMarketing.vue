<script setup lang="ts">
import type { DashboardMarketing, DashboardMarketingProvider } from '../../client';
import {
  dashboardMarketingStatus,
  formatMarketingCurrency,
  formatMarketingProvider,
  formatMarketingValue,
} from '../../services/dashboard-overview';

const props = defineProps<{ marketing: DashboardMarketing }>();
const status = () => dashboardMarketingStatus(props.marketing);
const platformMetrics = () => [
  ['Расход', formatMarketingCurrency(props.marketing.ad_spend, props.marketing.currency)],
  ['Клики', formatMarketingValue(props.marketing.clicks)],
  ['Показы', formatMarketingValue(props.marketing.impressions)],
  ['CTR', formatMarketingValue(props.marketing.ctr, 'percent')],
  ['Конверсии платформ', formatMarketingValue(props.marketing.platform_conversions)],
];
const crmMetrics = () => [
  ['Заявки в CRM', formatMarketingValue(props.marketing.leads)],
  ['CPL по CRM', formatMarketingCurrency(props.marketing.cost_per_lead, props.marketing.currency)],
  ['CAC по CRM', formatMarketingCurrency(props.marketing.customer_acquisition_cost, props.marketing.currency)],
];
const providerStatus = (provider: DashboardMarketingProvider) => dashboardMarketingStatus(provider);
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

    <div v-if="marketing.providers?.length" class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <article v-for="provider in marketing.providers" :key="provider.provider" class="rounded-xl border border-slate-100 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900/40">
        <div class="flex items-start justify-between gap-2"><h3 class="text-sm font-semibold text-slate-900 dark:text-white">{{ formatMarketingProvider(provider.provider) }}</h3><span class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="{ 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300': provider.status === 'fresh', 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300': provider.status === 'stale', 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300': provider.status === 'error', 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300': provider.status === 'unconfigured' }">{{ providerStatus(provider).label }}</span></div>
        <dl class="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs"><div><dt class="text-slate-500 dark:text-slate-400">Визиты</dt><dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{{ formatMarketingValue(provider.visits) }}</dd></div><div><dt class="text-slate-500 dark:text-slate-400">Расход</dt><dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{{ formatMarketingCurrency(provider.ad_spend, provider.currency) }}</dd></div><div><dt class="text-slate-500 dark:text-slate-400">Клики</dt><dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{{ formatMarketingValue(provider.clicks) }}</dd></div><div><dt class="text-slate-500 dark:text-slate-400">Конверсии</dt><dd class="mt-0.5 font-semibold text-slate-900 dark:text-white">{{ formatMarketingValue(provider.platform_conversions) }}</dd></div></dl>
      </article>
    </div>

    <div class="mt-4 grid gap-4 lg:grid-cols-2">
      <div class="rounded-xl bg-slate-50 p-3 dark:bg-slate-900/40"><p class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Рекламные платформы</p><div class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3"><div v-for="([label, value]) in platformMetrics()" :key="label"><p class="text-xs text-slate-500 dark:text-slate-400">{{ label }}</p><p class="mt-1 text-base font-semibold text-slate-900 dark:text-white">{{ value }}</p></div></div></div>
      <div class="rounded-xl border border-teal-100 bg-teal-50/60 p-3 dark:border-teal-900/50 dark:bg-teal-950/20"><p class="text-xs font-semibold uppercase tracking-wide text-teal-700 dark:text-teal-300">Результат в CRM</p><div class="mt-3 grid grid-cols-3 gap-3"><div v-for="([label, value]) in crmMetrics()" :key="label"><p class="text-xs text-slate-500 dark:text-slate-400">{{ label }}</p><p class="mt-1 text-base font-semibold text-slate-900 dark:text-white">{{ value }}</p></div></div></div>
    </div>

    <div v-if="marketing.sources?.length" class="mt-4 border-t border-slate-100 pt-3 dark:border-slate-700"><p class="text-xs font-semibold uppercase tracking-wide text-slate-400">Источники</p><div class="mt-2 space-y-2"><div v-for="source in marketing.sources" :key="source.name" class="flex items-center justify-between gap-3 text-sm"><span class="min-w-0 truncate text-slate-600 dark:text-slate-300">{{ source.name }}</span><span class="shrink-0 font-medium text-slate-900 dark:text-white">{{ formatMarketingValue(source.visits) }} · {{ formatMarketingValue(source.share_pct, 'percent') }}</span></div></div></div>
    <p v-else class="mt-4 text-sm text-slate-500 dark:text-slate-400">Источники не подключены.</p>
  </section>
</template>
