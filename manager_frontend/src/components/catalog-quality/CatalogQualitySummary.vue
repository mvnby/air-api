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
  if (severity === 'critical') return 'bg-red-50 text-red-700 border-red-200';
  if (severity === 'warning') return 'bg-amber-50 text-amber-800 border-amber-200';
  return 'bg-sky-50 text-sky-700 border-sky-200';
};
</script>

<template>
  <section class="border-b border-gray-200 bg-white px-4 py-4 sm:px-5">
    <div class="grid grid-cols-2 overflow-hidden rounded-lg border border-gray-200 xl:grid-cols-4">
      <div class="flex items-center gap-3 border-b border-r border-gray-200 px-3 py-3 xl:border-b-0">
        <ShieldCheck class="h-7 w-7 text-teal-700" />
        <div><p class="text-xs font-semibold text-gray-500">Средний score</p><p class="text-xl font-bold text-gray-950">{{ report.average_score }}</p></div>
      </div>
      <div class="border-b border-gray-200 px-3 py-3 xl:border-b-0 xl:border-r">
        <p class="text-xs font-semibold text-gray-500">Товаров в выборке</p><p class="text-xl font-bold text-gray-950">{{ formatNumber(report.total_products) }}</p>
      </div>
      <div class="border-r border-gray-200 px-3 py-3">
        <p class="text-xs font-semibold text-amber-700">Карточек с проблемами</p><p class="text-xl font-bold text-amber-800">{{ formatNumber(report.problem_products) }}</p>
      </div>
      <div class="px-3 py-3">
        <p class="text-xs font-semibold text-red-700">Критичных карточек</p><p class="text-xl font-bold text-red-800">{{ formatNumber(report.critical_products) }}</p>
      </div>
    </div>

    <div class="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-start">
      <div>
        <div class="flex items-baseline justify-between gap-3">
          <h2 class="text-sm font-bold text-gray-900">Главные причины в текущей выборке</h2>
          <p class="text-xs text-gray-500">Число на причине = количество нарушений</p>
        </div>
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            v-for="item in report.summary.slice(0, 8)"
            :key="item.code"
            class="inline-flex h-9 items-center gap-2 rounded-lg border px-2.5 text-xs font-semibold transition hover:brightness-95"
            :class="[severityTone(item.severity), selectedIssueCode === item.code ? 'ring-2 ring-teal-500 ring-offset-1' : '']"
            @click="emit('selectIssue', item.code)"
          >
            <component :is="categoryIcon(item.category)" class="h-4 w-4" />
            <span>{{ item.label }}</span>
            <strong>{{ formatNumber(item.count) }}</strong>
          </button>
          <p v-if="!report.summary.length" class="text-sm font-semibold text-emerald-700">По текущей выборке проблем нет.</p>
        </div>
      </div>

      <div class="grid grid-cols-3 gap-2 text-center text-xs">
        <div class="rounded-lg bg-red-50 px-3 py-2 text-red-800"><strong class="block text-base">{{ formatNumber(report.severity_product_counts?.critical) }}</strong>карточек<br>критично</div>
        <div class="rounded-lg bg-amber-50 px-3 py-2 text-amber-800"><strong class="block text-base">{{ formatNumber(report.severity_product_counts?.warning) }}</strong>карточек<br>с замечаниями</div>
        <div class="rounded-lg bg-sky-50 px-3 py-2 text-sky-800"><strong class="block text-base">{{ formatNumber(report.severity_issue_counts?.info) }}</strong>заметок<br>всего</div>
      </div>
    </div>
  </section>
</template>
