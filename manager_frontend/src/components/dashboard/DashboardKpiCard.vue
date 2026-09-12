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
  <article class="kitlane-kpi" :class="{ 'is-emphasized': emphasized }">
    <p class="text-sm font-medium text-[var(--kitlane-muted)] dark:text-slate-400">{{ dashboardKpiLabels[metric] }}</p>
    <p class="kitlane-kpi-value mt-2">{{ formatDashboardKpi(metric, kpi) }}</p>
    <p class="mt-2 text-xs font-medium" :class="{
      'text-emerald-700 dark:text-emerald-400': trend().tone === 'positive',
      'text-rose-700 dark:text-rose-400': trend().tone === 'negative',
      'text-[var(--kitlane-muted)] dark:text-slate-400': trend().tone === 'neutral',
    }">{{ trend().label }}</p>
  </article>
</template>

<style scoped>
.kitlane-kpi { min-width: 0; border: 1px solid var(--kitlane-border); border-radius: var(--kitlane-card-radius); background: var(--kitlane-surface); padding: 20px; }
.kitlane-kpi.is-emphasized { border-color: var(--kitlane-accent-text); background: var(--kitlane-accent-soft); }
.kitlane-kpi-value { font-size: clamp(24px, 2.2vw, 32px); line-height: 1.25; font-weight: 700; letter-spacing: -.6px; color: var(--kitlane-text); overflow-wrap: anywhere; }
@media (max-width: 767px) { .kitlane-kpi { padding: 16px; } }
</style>
