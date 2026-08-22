<script setup lang="ts">
import { computed, ref } from 'vue';
import type { DashboardSalesSeriesPoint } from '../../client';
import { formatDashboardCurrency, formatDashboardNumber } from '../../services/dashboard-overview';

const props = defineProps<{ series: DashboardSalesSeriesPoint[] }>();
const activeIndex = ref<number | null>(null);
const width = 640;
const height = 220;
const padding = { top: 16, right: 16, bottom: 32, left: 16 };
const chartHeight = height - padding.top - padding.bottom;
const chartWidth = width - padding.left - padding.right;
const maxRevenue = computed(() => Math.max(...props.series.map(point => point.revenue), 1));
const pointPosition = (point: DashboardSalesSeriesPoint, index: number) => ({
  x: padding.left + (props.series.length <= 1 ? chartWidth / 2 : (index / (props.series.length - 1)) * chartWidth),
  y: padding.top + chartHeight - (point.revenue / maxRevenue.value) * chartHeight,
});
const linePath = computed(() => props.series.map((point, index) => {
  const { x, y } = pointPosition(point, index);
  return `${index ? 'L' : 'M'} ${x} ${y}`;
}).join(' '));
const areaPath = computed(() => {
  const firstPoint = props.series[0];
  const lastPoint = props.series[props.series.length - 1];
  if (!firstPoint || !lastPoint) return '';
  const first = pointPosition(firstPoint, 0);
  const last = pointPosition(lastPoint, props.series.length - 1);
  return `${linePath.value} L ${last.x} ${height - padding.bottom} L ${first.x} ${height - padding.bottom} Z`;
});
const activePoint = computed(() => activeIndex.value == null ? null : props.series[activeIndex.value]);
const formatDate = (value: string) => new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' }).format(new Date(`${value}T00:00:00`));
const selectFromPointer = (event: MouseEvent) => {
  if (!props.series.length) return;
  const svg = event.currentTarget as SVGElement;
  const rect = svg.getBoundingClientRect();
  const relativeX = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
  const ratio = rect.width ? relativeX / rect.width : 0;
  activeIndex.value = Math.round(ratio * (props.series.length - 1));
};
</script>

<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h2 class="font-semibold text-slate-900 dark:text-white">Продажи по дням</h2>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Оплаты и закрытые продажи за текущий месяц</p>
      </div>
      <div v-if="activePoint" class="shrink-0 text-right text-xs text-slate-600 dark:text-slate-300">
        <p class="font-semibold">{{ formatDate(activePoint.date) }}</p>
        <p>{{ formatDashboardCurrency(activePoint.revenue) }} · {{ formatDashboardNumber(activePoint.sales) }} продаж</p>
      </div>
    </div>
    <div v-if="series.length" class="mt-4 overflow-hidden">
      <svg class="h-auto w-full" :viewBox="`0 0 ${width} ${height}`" role="img" aria-label="График оплат по дням" @mousemove="selectFromPointer" @mouseleave="activeIndex = null">
        <line v-for="fraction in [0, 0.5, 1]" :key="fraction" :x1="padding.left" :x2="width - padding.right" :y1="padding.top + chartHeight * fraction" :y2="padding.top + chartHeight * fraction" stroke="currentColor" class="text-slate-100 dark:text-slate-700" />
        <path :d="areaPath" fill="rgba(13, 148, 136, 0.14)" />
        <path :d="linePath" fill="none" stroke="#0d9488" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
        <g v-for="(point, index) in series" :key="point.date">
          <circle :cx="pointPosition(point, index).x" :cy="pointPosition(point, index).y" :r="activeIndex === index ? 5 : 3" fill="#0d9488">
            <title>{{ `${formatDate(point.date)}: ${formatDashboardCurrency(point.revenue)}, ${point.sales} продаж` }}</title>
          </circle>
          <text v-if="index === 0 || index === series.length - 1 || index === Math.floor(series.length / 2)" :x="pointPosition(point, index).x" :y="height - 10" text-anchor="middle" class="fill-slate-400 text-[11px]">{{ formatDate(point.date) }}</text>
        </g>
      </svg>
    </div>
    <div v-else class="mt-4 rounded-lg border border-dashed border-slate-200 py-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">За выбранный период пока нет оплат.</div>
  </section>
</template>
