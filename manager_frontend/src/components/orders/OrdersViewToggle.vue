<script setup lang="ts">
import type { DashboardView } from '../../api';

defineProps<{ modelValue: DashboardView }>();
const emit = defineEmits<{ 'update:modelValue': [value: DashboardView] }>();
</script>

<template>
  <div class="inline-flex rounded-[12px] bg-slate-800 p-1">
    <button
      class="rounded-[12px] px-3 py-2 text-sm font-medium transition"
      :class="modelValue === 'kanban' ? 'bg-white text-slate-900' : 'text-slate-300 hover:text-white'"
      @click="emit('update:modelValue', 'kanban')"
    >
      Канбан
    </button>
    <button
      class="rounded-[12px] px-3 py-2 text-sm font-medium transition"
      :class="modelValue === 'list' ? 'bg-white text-slate-900' : 'text-slate-300 hover:text-white'"
      @click="emit('update:modelValue', 'list')"
    >
      Список
    </button>
  </div>
</template>
