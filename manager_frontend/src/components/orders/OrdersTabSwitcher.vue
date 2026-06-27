<script setup lang="ts">
import { Building2, Layers3, UserRound } from 'lucide-vue-next';
import type { Segment } from '../../api';

defineProps<{ modelValue: Segment }>();
const emit = defineEmits<{ 'update:modelValue': [value: Segment] }>();

const tabs: Array<{ value: Segment; label: string; title: string; icon: typeof Layers3 }> = [
  { value: 'all', label: 'Все', title: 'Все заказы', icon: Layers3 },
  { value: 'b2c', label: 'B2C', title: 'Частные клиенты', icon: UserRound },
  { value: 'b2b', label: 'B2B', title: 'Юридические лица', icon: Building2 },
];
</script>

<template>
  <div class="inline-flex shrink-0 rounded-xl border border-gray-200 bg-gray-100 p-0.5">
    <button
      v-for="tab in tabs"
      :key="tab.value"
      class="inline-flex items-center gap-1 rounded-[10px] px-1.5 py-1.5 text-xs font-semibold transition sm:gap-1.5 sm:px-3 sm:text-sm"
      :class="modelValue === tab.value ? 'bg-[#007f80] text-white shadow-sm' : 'text-gray-600 hover:text-gray-900'"
      :title="tab.title"
      @click="emit('update:modelValue', tab.value)"
    >
      <component :is="tab.icon" class="h-3.5 w-3.5" />
      <span>{{ tab.label }}</span>
    </button>
  </div>
</template>
