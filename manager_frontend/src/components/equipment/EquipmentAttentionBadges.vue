<script setup lang="ts">
import { computed } from 'vue';
import {
  CircleAlert,
  CircleCheck,
  Clock3,
  ShieldAlert,
  TriangleAlert,
} from 'lucide-vue-next';
import { sortAttentionReasons } from './registry';

const props = defineProps<{
  reasons: string[];
  warrantyStatus?: string | null;
}>();

const warrantyNeedsClarification = computed(() => (
  !props.warrantyStatus || ['none', 'unknown'].includes(props.warrantyStatus)
));
const visibleReasons = computed(() => sortAttentionReasons(props.reasons || []).filter((reason) => (
  !(warrantyNeedsClarification.value && reason === 'needs_decision')
)));

const reasonLabel = (reason: string) => {
  if (reason === 'needs_decision') return 'Гарантию нужно уточнить';
  if (reason === 'maintenance_overdue') return 'ТО просрочено';
  if (reason === 'maintenance_due_soon') return 'ТО скоро';
  if (reason === 'warranty_expired') return 'Гарантия истекла';
  if (reason === 'warranty_expiring') return 'Гарантия истекает';
  return 'Требует внимания';
};

const reasonClass = (reason: string) => {
  if (reason === 'needs_decision') {
    return 'border-red-200 bg-red-50 text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-300';
  }
  if (reason === 'maintenance_overdue') {
    return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-300';
  }
  if (reason === 'maintenance_due_soon') {
    return 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300';
  }
  if (reason === 'warranty_expired') {
    return 'border-gray-300 bg-gray-100 text-gray-700 dark:border-slate-500 dark:bg-slate-700 dark:text-slate-200';
  }
  if (reason === 'warranty_expiring') {
    return 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-500/40 dark:bg-sky-500/10 dark:text-sky-300';
  }
  return 'border-gray-200 bg-white text-gray-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200';
};

const reasonIcon = (reason: string) => {
  if (reason === 'needs_decision') return CircleAlert;
  if (reason === 'maintenance_overdue') return TriangleAlert;
  if (reason === 'maintenance_due_soon') return Clock3;
  return ShieldAlert;
};
</script>

<template>
  <div class="flex flex-wrap gap-1.5">
    <span
      v-if="!visibleReasons.length && !warrantyNeedsClarification"
      class="inline-flex min-h-6 items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-semibold leading-none text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/10 dark:text-emerald-300"
    >
      <CircleCheck class="h-3.5 w-3.5 shrink-0" />
      Без срочных действий
    </span>

    <span
      v-if="warrantyNeedsClarification"
      class="inline-flex min-h-6 items-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-semibold leading-none text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300"
    >
      <CircleAlert class="h-3.5 w-3.5 shrink-0" />
      Гарантию нужно уточнить
    </span>

    <span
      v-for="reason in visibleReasons"
      :key="reason"
      class="inline-flex min-h-6 items-center gap-1 rounded-md border px-2 py-1 text-xs font-semibold leading-none"
      :class="reasonClass(reason)"
    >
      <component :is="reasonIcon(reason)" class="h-3.5 w-3.5 shrink-0" />
      {{ reasonLabel(reason) }}
    </span>
  </div>
</template>
