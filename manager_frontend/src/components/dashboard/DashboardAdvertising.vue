<script setup lang="ts">
import { computed } from 'vue';
import { AlertCircle, ExternalLink, Megaphone } from 'lucide-vue-next';
import type { DashboardMarketing, DashboardMarketingProvider } from '../../client';
import {
  dashboardMarketingStatus,
  formatMarketingCurrency,
  formatMarketingProvider,
  formatMarketingValue,
} from '../../services/dashboard-overview';

const props = defineProps<{ marketing: DashboardMarketing; canManageIntegrations: boolean }>();
type AdvertisingProvider = Extract<DashboardMarketingProvider['provider'], 'yandex_direct' | 'google_ads'>;
type AdvertisingProviderState = Pick<DashboardMarketingProvider, 'provider' | 'status'> & Partial<DashboardMarketingProvider>;
const expectedProviders: AdvertisingProvider[] = ['yandex_direct', 'google_ads'];
const providers = computed(() => expectedProviders.map((name) => (
  props.marketing.providers?.find(provider => provider.provider === name) ?? { provider: name, status: 'unconfigured' as const }
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
const status = computed(() => (
  hasProblemProvider.value && hasFreshProvider.value
    ? { label: 'Частично доступно', message: 'Часть рекламных источников требует внимания. Остальные данные получены.', tone: 'stale' as const }
    : dashboardMarketingStatus({ status: panelStatus.value })
));
const providerMessage = (provider: AdvertisingProviderState) => (
  provider.message || dashboardMarketingStatus(provider).message
);
const metrics = (provider: AdvertisingProviderState) => [
  ['Расход', formatMarketingCurrency(provider.ad_spend, provider.currency)],
  ['Клики', formatMarketingValue(provider.clicks)],
  ['Показы', formatMarketingValue(provider.impressions)],
  ['CTR', formatMarketingValue(provider.ctr, 'percent')],
  ['Целевые действия платформы', formatMarketingValue(provider.platform_conversions)],
].filter(([, value]) => value !== '—');
const updatedAt = (provider: AdvertisingProviderState) => {
  const value = provider.updated_at;
  return value ? new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Minsk' }).format(new Date(value)) : null;
};
</script>

<template>
  <section class="space-y-4" aria-labelledby="advertising-heading">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div><h2 id="advertising-heading" class="text-lg font-semibold text-slate-900 dark:text-white">Эффективность рекламы</h2><p class="mt-1 text-sm text-slate-500 dark:text-slate-400">Данные рекламных кабинетов; продажи CRM не сопоставляются без атрибуции.</p></div>
      <a v-if="canManageIntegrations" href="/manager/integrations" class="inline-flex items-center gap-1 text-sm font-semibold text-teal-700 hover:text-teal-800 dark:text-teal-300"><ExternalLink class="h-4 w-4" aria-hidden="true" />Настроить подключения</a>
    </div>
    <div v-if="panelStatus === 'error' || panelStatus === 'stale'" class="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-100"><AlertCircle class="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" /><p>{{ status.message }}</p></div>
    <div class="grid gap-3 lg:grid-cols-2">
      <article v-for="provider in providers" :key="provider.provider" class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
        <div class="flex flex-wrap items-start justify-between gap-2"><div class="flex min-w-0 gap-2"><Megaphone class="mt-0.5 h-5 w-5 shrink-0 text-teal-600 dark:text-teal-300" aria-hidden="true" /><div class="min-w-0"><h3 class="font-semibold text-slate-900 dark:text-white">{{ formatMarketingProvider(provider.provider) }}</h3><p class="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{{ providerMessage(provider) }}</p></div></div><span class="rounded-full px-2 py-1 text-xs font-semibold" :class="{ 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300': provider.status === 'fresh', 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300': provider.status === 'stale', 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300': provider.status === 'error', 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300': provider.status === 'unconfigured' }">{{ dashboardMarketingStatus(provider).label }}</span></div>
        <dl v-if="metrics(provider).length" class="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm"><div v-for="([label, value]) in metrics(provider)" :key="label"><dt class="text-xs text-slate-500 dark:text-slate-400">{{ label }}</dt><dd class="mt-1 font-semibold text-slate-900 dark:text-white">{{ value }}</dd></div></dl>
        <p v-else-if="provider.status === 'fresh'" class="mt-4 text-sm text-slate-500 dark:text-slate-400">За этот период рекламный кабинет не вернул показателей.</p>
        <p v-if="updatedAt(provider)" class="mt-4 text-xs text-slate-400 dark:text-slate-500">Последнее успешное обновление: {{ updatedAt(provider) }}</p>
      </article>
    </div>
  </section>
</template>
