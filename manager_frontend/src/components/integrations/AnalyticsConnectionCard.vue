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

    <div v-if="connection.state === 'connected'" class="mt-4 rounded-xl bg-slate-50 px-3.5 py-3 text-sm dark:bg-slate-800">
      <p class="font-semibold text-slate-800 dark:text-slate-100">
        {{ connection.counter_name || `Счётчик ${connection.counter_id}` }}
      </p>
      <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
        {{ connection.site || 'Сайт не указан' }} · ID {{ connection.counter_id }}
      </p>
    </div>

    <div class="mt-auto flex items-center gap-2 pt-5">
      <button
        v-if="connection.available"
        type="button"
        class="rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-teal-700"
        @click="$emit('configure', connection)"
      >
        {{ connection.state === 'connected' ? 'Изменить' : 'Подключить' }}
      </button>
      <button
        v-if="connection.provider === 'yandex_metrika'"
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
