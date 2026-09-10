<script setup lang="ts">
import { computed, ref } from 'vue';
import { BarChart3, ExternalLink, Search } from 'lucide-vue-next';
import type { DashboardMarketing, DashboardMarketingProvider, DashboardSearchDemand as DashboardSearchDemandModel } from '../../client';
import {
  dashboardMarketingStatus,
  formatDurationSeconds,
  formatMarketingProvider,
  formatMarketingValue,
} from '../../services/dashboard-overview';
import DashboardSearchDemand from './DashboardSearchDemand.vue';

const props = defineProps<{
  marketing: DashboardMarketing;
  searchDemand: DashboardSearchDemandModel;
  canManageIntegrations: boolean;
}>();
type TrafficProvider = Extract<DashboardMarketingProvider['provider'], 'yandex_metrika' | 'google_analytics'>;
type TrafficProviderState = Pick<DashboardMarketingProvider, 'provider' | 'status'> & Partial<DashboardMarketingProvider>;
const expectedProviders: TrafficProvider[] = ['yandex_metrika', 'google_analytics'];
const sourcesExpanded = ref(false);
const providers = computed<TrafficProviderState[]>(() => expectedProviders.map((name) => (
  props.marketing.providers?.find(provider => provider.provider === name) ?? { provider: name, status: 'unconfigured' }
)));
const activeProviders = computed(() => providers.value.filter(provider => provider.status !== 'unconfigured'));
const hasFreshProvider = computed(() => activeProviders.value.some(provider => provider.status === 'fresh'));
const hasProblemProvider = computed(() => activeProviders.value.some(provider => provider.status === 'error' || provider.status === 'stale'));
const panelStatus = computed(() => {
  if (!activeProviders.value.length) return 'unconfigured' as const;
  if (hasProblemProvider.value && hasFreshProvider.value) return 'stale' as const;
  if (activeProviders.value.every(provider => provider.status === 'error')) return 'error' as const;
  if (activeProviders.value.some(provider => provider.status === 'stale')) return 'stale' as const;
  return 'fresh' as const;
});
const trafficStatus = computed(() => (
  hasProblemProvider.value && hasFreshProvider.value
    ? { label: 'Частично доступно', message: 'Часть источников требует внимания.', tone: 'stale' as const }
    : dashboardMarketingStatus({ status: panelStatus.value })
));
const metrics = (provider: TrafficProviderState) => provider.provider === 'yandex_metrika'
  ? [['Визиты', formatMarketingValue(provider.visits)], ['Отказы', formatMarketingValue(provider.bounce_rate, 'percent')], ['Время на сайте', formatDurationSeconds(provider.average_session_duration_seconds)]]
  : [['Сеансы', formatMarketingValue(provider.sessions)], ['Пользователи', formatMarketingValue(provider.active_users)], ['Вовлечённость', formatMarketingValue(provider.engagement_rate, 'percent')], ['Средняя длительность', formatDurationSeconds(provider.average_session_duration_seconds)]];
const availableMetrics = (provider: TrafficProviderState) => metrics(provider).filter(([, value]) => value !== '—');
const providerMessage = (provider: TrafficProviderState) => provider.message || dashboardMarketingStatus(provider).message;
const updatedAt = (provider: TrafficProviderState) => {
  const value = provider.updated_at;
  return value ? new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Minsk' }).format(new Date(value)) : null;
};
const visibleSources = computed(() => sourcesExpanded.value ? props.marketing.sources || [] : (props.marketing.sources || []).slice(0, 6));
</script>

<template>
  <section class="space-y-6" aria-labelledby="site-seo-heading">
    <div class="flex flex-wrap items-start justify-between gap-3"><div><h2 id="site-seo-heading" class="text-lg font-semibold text-slate-900 dark:text-white">Сайт и SEO</h2><p class="mt-1 text-sm text-slate-500 dark:text-slate-400">Посещаемость сайта и запросы из поисковых систем.</p></div><a v-if="canManageIntegrations" href="/manager/integrations" class="inline-flex items-center gap-1 text-sm font-semibold text-teal-700 hover:text-teal-800 dark:text-teal-300"><ExternalLink class="h-4 w-4" aria-hidden="true" />Настроить подключения</a></div>
    <section class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800" aria-labelledby="traffic-heading">
      <div class="flex items-start justify-between gap-3"><div class="flex gap-2"><BarChart3 class="mt-0.5 h-5 w-5 text-teal-600 dark:text-teal-300" aria-hidden="true" /><div><h3 id="traffic-heading" class="font-semibold text-slate-900 dark:text-white">Посещаемость</h3><p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Метрика и Google Analytics 4</p></div></div><span class="rounded-full px-2 py-1 text-xs font-semibold" :class="{ 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300': panelStatus === 'fresh', 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300': panelStatus === 'stale', 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300': panelStatus === 'error', 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300': panelStatus === 'unconfigured' }">{{ trafficStatus.label }}</span></div>
      <div class="mt-4 grid gap-3 lg:grid-cols-2"><article v-for="provider in providers" :key="provider.provider" class="rounded-lg bg-slate-50 p-3 dark:bg-slate-900/40"><div class="flex flex-wrap items-start justify-between gap-2"><div class="min-w-0"><h4 class="text-sm font-semibold text-slate-900 dark:text-white">{{ formatMarketingProvider(provider.provider) }}</h4><p class="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{{ providerMessage(provider) }}</p></div><span class="text-xs font-medium text-slate-500 dark:text-slate-400">{{ dashboardMarketingStatus(provider).label }}</span></div><dl v-if="availableMetrics(provider).length" class="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-sm"><div v-for="([label, value]) in availableMetrics(provider)" :key="label"><dt class="text-xs text-slate-500 dark:text-slate-400">{{ label }}</dt><dd class="mt-1 font-semibold text-slate-900 dark:text-white">{{ value }}</dd></div></dl><p v-else-if="provider.status === 'fresh'" class="mt-3 text-sm text-slate-500 dark:text-slate-400">За этот период отчёт пуст.</p><p v-if="updatedAt(provider)" class="mt-3 text-xs text-slate-400 dark:text-slate-500">Последнее успешное обновление: {{ updatedAt(provider) }}</p></article></div>
      <div v-if="marketing.sources?.length" class="mt-4 border-t border-slate-100 pt-3 dark:border-slate-700"><p class="text-xs font-semibold uppercase tracking-wide text-slate-400">Основные источники трафика</p><div class="mt-2 space-y-2"><div v-for="source in visibleSources" :key="source.name" class="flex items-center justify-between gap-3 text-sm"><span class="min-w-0 truncate text-slate-600 dark:text-slate-300">{{ source.name }}</span><span class="shrink-0 font-medium text-slate-900 dark:text-white">{{ formatMarketingValue(source.visits) }} · {{ formatMarketingValue(source.share_pct, 'percent') }}</span></div></div><button v-if="marketing.sources.length > 6" type="button" class="mt-3 text-sm font-semibold text-teal-700 hover:text-teal-800 dark:text-teal-300" @click="sourcesExpanded = !sourcesExpanded">{{ sourcesExpanded ? 'Свернуть' : `Показать все (${marketing.sources.length})` }}</button></div>
    </section>
    <div class="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200"><Search class="h-5 w-5 text-teal-600 dark:text-teal-300" aria-hidden="true" />Поисковый спрос</div>
    <DashboardSearchDemand :demand="searchDemand" :can-manage-integrations="canManageIntegrations" />
  </section>
</template>
