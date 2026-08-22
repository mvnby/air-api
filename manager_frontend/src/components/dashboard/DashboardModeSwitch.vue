<script setup lang="ts">
import type { DashboardMode } from '../../services/dashboard-overview';

defineProps<{ modelValue: DashboardMode }>();
const emit = defineEmits<{ 'update:modelValue': [mode: DashboardMode] }>();
</script>

<template>
  <div class="grid w-full grid-cols-2 rounded-lg border border-slate-200 bg-slate-100 p-1 dark:border-slate-700 dark:bg-slate-800 sm:w-[248px]" role="group" aria-label="Режим дашборда">
    <button
      v-for="option in [{ value: 'manager', label: 'Менеджер' }, { value: 'owner', label: 'Собственник' }] as const"
      :key="option.value"
      type="button"
      class="rounded-md px-3 py-2 text-sm font-semibold transition-colors"
      :class="modelValue === option.value ? 'bg-white text-teal-700 shadow-sm dark:bg-slate-700 dark:text-teal-300' : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'"
      :aria-pressed="modelValue === option.value"
      @click="emit('update:modelValue', option.value)"
    >{{ option.label }}</button>
  </div>
</template>
