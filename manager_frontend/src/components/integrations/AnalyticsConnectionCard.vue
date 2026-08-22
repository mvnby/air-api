<script setup lang="ts">
import { BarChart3, CheckCircle2, CircleDashed, HelpCircle, TriangleAlert } from 'lucide-vue-next';

import type { AnalyticsConnectionItem } from '../../client';

defineProps<{ connection: AnalyticsConnectionItem }>();
defineEmits<{
  configure: [connection: AnalyticsConnectionItem];
  help: [connection: AnalyticsConnectionItem];
}>();

const stateLabel = (state: AnalyticsConnectionItem['state']) => ({
  connected: 'Подключено',
  not_configured: 'Не подключено',
  coming_soon: 'Скоро',
  error: 'Нужна проверка',
}[state]);

const configurationLabels: Record<string, string> = {
  client_login: 'Логин клиента',
  site_url: 'Сайт',
  primary_hostname: 'Домен',
  property_id: 'Property ID',
  customer_id: 'Customer ID',
  login_customer_id: 'MCC',
  site_property: 'Ресурс',
  currency: 'Валюта',
};
const hiddenConfiguration = new Set(['user_id', 'host_id', 'campaigns_checked']);
const configurationEntries = (connection: AnalyticsConnectionItem) => (
  Object.entries(connection.configuration || {})
    .filter(([key, value]) => Boolean(value) && !hiddenConfiguration.has(key))
    .map(([key, value]) => [configurationLabels[key] || key, value])
);
</script>

<template>
  <article class="flex min-h-64 flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
    <div class="flex items-start justify-between gap-4">
      <div class="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-900 text-white">
        <BarChart3 class="h-5 w-5" />
      </div>
      <span
        class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold"
        :class="{
          'bg-emerald-50 text-emerald-700': connection.state === 'connected',
          'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300': connection.state === 'not_configured' || connection.state === 'coming_soon',
          'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300': connection.state === 'error',
        }"
      >
        <CheckCircle2 v-if="connection.state === 'connected'" class="h-3.5 w-3.5" />
        <TriangleAlert v-else-if="connection.state === 'error'" class="h-3.5 w-3.5" />
        <CircleDashed v-else class="h-3.5 w-3.5" />
        {{ stateLabel(connection.state) }}
      </span>
    </div>

    <h2 class="mt-5 text-lg font-bold text-slate-950 dark:text-white">{{ connection.label }}</h2>
    <p class="mt-1.5 text-sm leading-6 text-slate-500 dark:text-slate-400">{{ connection.description }}</p>

    <div v-if="connection.state === 'connected' && (connection.counter_name || connection.counter_id)" class="mt-4 rounded-xl bg-slate-50 px-3.5 py-3 text-sm dark:bg-slate-800">
      <p class="font-semibold text-slate-800 dark:text-slate-100">
        {{ connection.counter_name || `Счётчик ${connection.counter_id}` }}
      </p>
      <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
        {{ connection.site || 'Сайт не указан' }} · ID {{ connection.counter_id }}
      </p>
    </div>
    <dl v-else-if="connection.state === 'connected' && configurationEntries(connection).length" class="mt-4 space-y-1.5 rounded-xl bg-slate-50 px-3.5 py-3 text-sm dark:bg-slate-800">
      <div v-for="([label, value]) in configurationEntries(connection)" :key="label" class="flex items-baseline justify-between gap-3">
        <dt class="min-w-0 truncate text-xs text-slate-500 dark:text-slate-400">{{ label }}</dt>
        <dd class="min-w-0 truncate text-right font-semibold text-slate-800 dark:text-slate-100">{{ value }}</dd>
      </div>
    </dl>

    <div class="mt-auto flex flex-wrap items-center gap-2 pt-5">
      <button
        v-if="connection.available"
        type="button"
        class="min-w-0 flex-1 rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-teal-700 sm:flex-none"
        @click="$emit('configure', connection)"
      >
        {{ connection.state === 'connected' ? 'Изменить' : 'Подключить' }}
      </button>
      <button
        v-if="connection.available"
        data-testid="analytics-help-button"
        type="button"
        class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-slate-200 text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        aria-label="Где взять данные для подключения?"
        title="Где взять данные для подключения?"
        @click="$emit('help', connection)"
      >
        <HelpCircle class="h-4 w-4" />
      </button>
    </div>
  </article>
</template>
