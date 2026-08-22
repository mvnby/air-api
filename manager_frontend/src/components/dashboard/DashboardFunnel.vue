<script setup lang="ts">
import { computed } from 'vue';
import type { DashboardFunnelStage } from '../../client';
import { formatDashboardNumber } from '../../services/dashboard-overview';

const props = defineProps<{ stages: DashboardFunnelStage[] }>();
const formatPercent = (value: number | null | undefined) => value == null ? '—' : `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)}%`;
const formatDays = (value: number | null | undefined) => value == null ? '—' : `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)} дн.`;
const maxCount = computed(() => Math.max(0, ...props.stages.flatMap(stage => stage.current == null ? [] : [stage.current])));
const barWidth = (value: number | null | undefined) => {
  if (value == null || maxCount.value === 0) return '0%';
  return `${Math.max(4, (value / maxCount.value) * 100)}%`;
};
</script>

<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
    <h2 class="font-semibold text-slate-900 dark:text-white">Воронка</h2>
    <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">События за месяц, не когортная воронка</p>
    <ol v-if="stages.length" class="mt-4 space-y-2">
      <li v-for="(stage, index) in stages" :key="stage.stage" class="rounded-lg border border-slate-100 px-3 py-2.5 dark:border-slate-700/70">
        <div class="flex items-baseline justify-between gap-3"><span class="text-sm font-medium text-slate-700 dark:text-slate-200">{{ stage.label }}</span><span class="font-semibold text-slate-950 dark:text-white">{{ formatDashboardNumber(stage.current) }}</span></div>
        <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700" :aria-label="`${stage.label}: ${formatDashboardNumber(stage.current)}`"><div class="h-full rounded-full bg-teal-500 transition-[width]" :style="{ width: barWidth(stage.current) }" /></div>
        <div class="mt-1 flex flex-wrap gap-x-3 text-xs text-slate-500 dark:text-slate-400"><span v-if="index">Конверсия: {{ formatPercent(stage.conversion_from_previous_pct) }}</span><span>Цикл: {{ formatDays(stage.avg_cycle_days) }}</span></div>
      </li>
    </ol>
    <div v-else class="mt-4 rounded-lg border border-dashed border-slate-200 py-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">Воронка появится после первых событий.</div>
  </section>
</template>
