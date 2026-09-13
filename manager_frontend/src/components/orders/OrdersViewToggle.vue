<script setup lang="ts">
import { LayoutGrid, List } from 'lucide-vue-next';
import type { DashboardView } from '../../api';

defineProps<{ modelValue: DashboardView }>();
const emit = defineEmits<{ 'update:modelValue': [value: DashboardView] }>();
</script>

<template>
  <div class="inline-flex rounded-xl border border-gray-200 bg-gray-100 p-0.5 dark:border-slate-600 dark:bg-slate-700">
    <button
      class="inline-flex items-center gap-1.5 rounded-[10px] px-2 py-1.5 text-xs font-semibold transition sm:px-3 sm:py-2"
      :class="modelValue === 'kanban' ? 'bg-[var(--mv-teal)] text-white' : 'text-gray-600 hover:text-gray-900 dark:text-slate-200 dark:hover:text-white'"
      title="Канбан"
      aria-label="Канбан"
      :aria-pressed="modelValue === 'kanban'"
      @click="emit('update:modelValue', 'kanban')"
    >
      <LayoutGrid class="h-4 w-4" />
      <span>Канбан</span>
    </button>
    <button
      class="inline-flex items-center gap-1.5 rounded-[10px] px-2 py-1.5 text-xs font-semibold transition sm:px-3 sm:py-2"
      :class="modelValue === 'list' ? 'bg-[var(--mv-teal)] text-white' : 'text-gray-600 hover:text-gray-900 dark:text-slate-200 dark:hover:text-white'"
      title="Таблица"
      aria-label="Таблица"
      :aria-pressed="modelValue === 'list'"
      @click="emit('update:modelValue', 'list')"
    >
      <List class="h-4 w-4" />
      <span>Таблица</span>
    </button>
  </div>
</template>
