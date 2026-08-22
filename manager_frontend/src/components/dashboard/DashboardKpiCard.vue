<script setup lang="ts">
import type { DashboardKpi } from '../../client';
import {
  dashboardKpiLabels,
  formatDashboardKpi,
  getDashboardTrend,
  type DashboardKpiKey,
} from '../../services/dashboard-overview';

const props = defineProps<{ metric: DashboardKpiKey; kpi: DashboardKpi; emphasized?: boolean }>();
const trend = () => getDashboardTrend(props.metric, props.kpi);
</script>

<template>
  <article class="rounded-xl border p-4" :class="emphasized ? 'border-teal-200 bg-teal-50/70 dark:border-teal-800 dark:bg-teal-950/20' : 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800'">
    <p class="text-sm font-medium text-slate-500 dark:text-slate-400">{{ dashboardKpiLabels[metric] }}</p>
    <p class="mt-2 text-2xl font-bold tracking-tight text-slate-900 dark:text-white">{{ formatDashboardKpi(metric, kpi) }}</p>
    <p class="mt-2 text-xs font-medium" :class="{
      'text-emerald-700 dark:text-emerald-400': trend().tone === 'positive',
      'text-rose-700 dark:text-rose-400': trend().tone === 'negative',
      'text-slate-500 dark:text-slate-400': trend().tone === 'neutral',
    }">{{ trend().label }}</p>
  </article>
</template>
