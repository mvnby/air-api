<script setup lang="ts">
import { LayoutGrid, List } from 'lucide-vue-next';
import type { DashboardView } from '../../api';

defineProps<{ modelValue: DashboardView }>();
const emit = defineEmits<{ 'update:modelValue': [value: DashboardView] }>();
</script>

<template>
  <div class="inline-flex rounded-xl border border-gray-200 bg-gray-100 p-0.5">
    <button
      class="rounded-[10px] p-1.5 transition sm:p-2"
      :class="modelValue === 'kanban' ? 'bg-[var(--mv-teal)] text-white' : 'text-gray-600 hover:text-gray-900'"
      title="Канбан"
      aria-label="Канбан"
      @click="emit('update:modelValue', 'kanban')"
    >
      <LayoutGrid class="h-4 w-4" />
    </button>
    <button
      class="rounded-[10px] p-1.5 transition sm:p-2"
      :class="modelValue === 'list' ? 'bg-[var(--mv-teal)] text-white' : 'text-gray-600 hover:text-gray-900'"
      title="Список"
      aria-label="Список"
      @click="emit('update:modelValue', 'list')"
    >
      <List class="h-4 w-4" />
    </button>
  </div>
</template>
