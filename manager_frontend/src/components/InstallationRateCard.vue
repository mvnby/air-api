<script setup lang="ts">
import { computed } from 'vue';
import type { ManagerInstallationRateResponse } from '../client';

const props = defineProps<{
  rate: ManagerInstallationRateResponse;
}>();

const emit = defineEmits<{
  (event: 'edit', rate: ManagerInstallationRateResponse): void;
}>();

const isAutomatic = computed(() => props.rate.selection_status === 'automatic_fixed');
const isUnsupported = computed(() => props.rate.selection_status === 'unsupported');
const isManualQuote = computed(() => (
  props.rate.selection_status === 'matched_manual_quote'
  || props.rate.selection_status === 'legacy_manual_quote'
));

const statusLabel = computed(() => {
  if (props.rate.selection_status === 'automatic_fixed') return 'Считается автоматически';
  if (props.rate.selection_status === 'matched_manual_quote') return 'Подбирается, цену уточнит менеджер';
  if (props.rate.selection_status === 'legacy_manual_quote') return 'Резервное legacy-правило';
  return 'Не участвует в автоподборе';
});

const statusClass = computed(() => {
  if (props.rate.selection_status === 'automatic_fixed') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300';
  }
  if (props.rate.selection_status === 'matched_manual_quote') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200';
  }
  return 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-600 dark:bg-slate-700/50 dark:text-slate-300';
});

const iconClass = computed(() => {
  if (isAutomatic.value) return 'bg-teal-50 text-teal-600 dark:bg-teal-500/10 dark:text-teal-300';
  if (isUnsupported.value) return 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-300';
  return 'bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-200';
});

const categoryIcon = computed(() => {
  const normalized = props.rate.category.trim().toLowerCase();
  if (normalized === 'wall') return 'home';
  if (normalized === 'cassette') return 'grid_view';
  if (normalized === 'duct') return 'air';
  if (normalized === 'ceiling' || normalized === 'floor-ceiling') return 'vertical_align_top';
  if (normalized === 'multisplit') return 'account_tree';
  return 'construction';
});

const mappingTarget = computed(() => (
  isUnsupported.value ? 'не подключено к публичному подбору' : props.rate.title
));
</script>

<template>
  <article class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-slate-700/60 dark:bg-[#1e293b]">
    <div class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 items-start gap-3">
        <div :class="iconClass" class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
          <span class="material-icons-round">{{ categoryIcon }}</span>
        </div>
        <div class="min-w-0">
          <h3 class="font-semibold text-gray-900 dark:text-slate-100">{{ rate.title }}</h3>
          <div class="mt-1 text-xs text-gray-500 dark:text-slate-400">{{ rate.power_label }}</div>
        </div>
      </div>
      <button
        v-if="!isUnsupported"
        class="rounded-lg border border-gray-200 p-2 text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-900 dark:border-slate-600 dark:hover:bg-slate-700 dark:hover:text-white"
        title="Изменить цену"
        @click="emit('edit', rate)"
      >
        <span class="material-icons-round text-lg">edit</span>
      </button>
      <span v-else class="material-icons-round p-2 text-lg text-slate-400" title="Редактирование отключено">lock</span>
    </div>

    <div class="mt-4 rounded-lg border border-gray-100 bg-gray-50 p-3 dark:border-slate-700 dark:bg-slate-800/70">
      <div class="flex items-center gap-2 text-xs text-gray-500 dark:text-slate-400">
        <span>{{ rate.equipment_label }}</span>
        <span class="material-icons-round text-sm text-teal-500">arrow_forward</span>
        <span class="font-medium text-gray-800 dark:text-slate-200">{{ mappingTarget }}</span>
      </div>
      <p v-if="!isAutomatic" class="mt-2 text-xs text-gray-500 dark:text-slate-400">{{ rate.selection_note }}</p>
    </div>

    <div class="mt-4">
      <div class="text-2xl font-bold text-gray-900 dark:text-white">
        <span v-if="isManualQuote">от </span>{{ rate.base_price }} BYN
      </div>
      <div v-if="isAutomatic" class="mt-1 text-xs text-gray-500 dark:text-slate-400">
        Включено {{ rate.included_pipe_meters }} м · далее {{ rate.extra_pipe_price }} BYN/м
      </div>
      <div v-else-if="isManualQuote" class="mt-1 text-xs text-gray-500 dark:text-slate-400">
        Ориентир для витрины · точную стоимость подтвердит менеджер
      </div>
      <div v-else class="mt-1 text-xs text-gray-500 dark:text-slate-400">
        Служебное legacy-значение · сайт его не использует
      </div>
    </div>

    <div :class="statusClass" class="mt-4 inline-flex rounded-full border px-2.5 py-1 text-xs font-medium">
      {{ statusLabel }}
    </div>
  </article>
</template>
