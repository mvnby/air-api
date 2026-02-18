<script setup lang="ts">
import type { DashboardView } from '../../api';

defineProps<{ modelValue: DashboardView }>();
const emit = defineEmits<{ 'update:modelValue': [value: DashboardView] }>();
</script>

<template>
  <div class="inline-flex rounded-[12px] bg-gray-100 p-1 border border-gray-200">
    <button
      class="rounded-[12px] px-3 py-2 text-sm font-medium transition"
      :class="modelValue === 'kanban' ? 'bg-[var(--mv-teal)] text-white' : 'text-gray-600 hover:text-gray-900'"
      @click="emit('update:modelValue', 'kanban')"
    >
      Канбан
    </button>
    <button
      class="rounded-[12px] px-3 py-2 text-sm font-medium transition"
      :class="modelValue === 'list' ? 'bg-[var(--mv-teal)] text-white' : 'text-gray-600 hover:text-gray-900'"
      @click="emit('update:modelValue', 'list')"
    >
      Список
    </button>
  </div>
</template>
