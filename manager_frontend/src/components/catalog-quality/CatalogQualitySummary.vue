<script setup lang="ts">
import { AlertTriangle, Image as ImageIcon, ListChecks, PackageCheck, ShieldCheck, Truck } from 'lucide-vue-next';
import type { ManagerCatalogQualityReportResponse } from '../../api';

const props = defineProps<{
  report: ManagerCatalogQualityReportResponse;
  selectedIssueCode?: string;
}>();

const emit = defineEmits<{ selectIssue: [code: string] }>();

const formatNumber = (value?: number | null) => new Intl.NumberFormat('ru-RU').format(Number(value || 0));
const categoryIcon = (category: string) => {
  if (category === 'media') return ImageIcon;
  if (category === 'identity') return PackageCheck;
  if (category === 'specs') return ListChecks;
  if (category === 'supplier') return Truck;
  return AlertTriangle;
};
const severityTone = (severity: string) => {
  if (severity === 'critical') return 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-200';
  if (severity === 'warning') return 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200';
  return 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-200';
};
</script>

<template>
  <section class="border-b border-gray-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900 sm:px-5">
    <div class="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
      <div class="flex items-center gap-2">
        <ShieldCheck class="h-6 w-6 shrink-0 text-teal-700" />
        <div><p class="text-[11px] font-semibold uppercase text-gray-500 dark:text-slate-400">Средний score</p><p class="text-lg font-bold text-gray-950 dark:text-slate-100">{{ report.average_score }} / 100</p></div>
      </div>
      <div><p class="text-[11px] font-semibold uppercase text-gray-500 dark:text-slate-400">Товаров</p><p class="text-lg font-bold text-gray-950 dark:text-slate-100">{{ formatNumber(report.total_products) }}</p></div>
      <div><p class="text-[11px] font-semibold uppercase text-red-600">Критичных</p><p class="text-lg font-bold text-red-700">{{ formatNumber(report.critical_products) }}</p></div>
      <div><p class="text-[11px] font-semibold uppercase text-teal-700">Исправимо здесь</p><p class="text-lg font-bold text-teal-800">{{ formatNumber(report.fixable_products) }}</p></div>
    </div>

    <div v-if="report.summary.length" class="mt-3 flex flex-wrap items-center gap-1.5 border-t border-gray-100 pt-3 dark:border-slate-700">
      <span class="mr-1 text-xs font-semibold text-gray-500 dark:text-slate-400">Главные причины:</span>
      <button
        v-for="item in report.summary.slice(0, 6)"
        :key="item.code"
        class="inline-flex min-h-8 items-center gap-1.5 rounded-lg border px-2 py-1 text-xs font-semibold transition hover:brightness-95"
        :class="[severityTone(item.severity), selectedIssueCode === item.code ? 'ring-2 ring-teal-500 ring-offset-1' : '']"
        :title="`Показать ${formatNumber(item.count)} карточек с этой проблемой`"
        @click="emit('selectIssue', item.code)"
      >
        <component :is="categoryIcon(item.category)" class="h-3.5 w-3.5" />
        <span>{{ item.label }}</span>
        <strong>{{ formatNumber(item.count) }}</strong>
      </button>
    </div>
    <p v-else class="mt-3 border-t border-gray-100 pt-3 text-sm font-semibold text-emerald-700">По текущей выборке проблем нет.</p>
  </section>
</template>
