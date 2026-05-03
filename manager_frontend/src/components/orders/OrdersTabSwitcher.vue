<script setup lang="ts">
import type { Segment } from '../../api';

defineProps<{ modelValue: Segment }>();
const emit = defineEmits<{ 'update:modelValue': [value: Segment] }>();
</script>

<template>
  <div class="inline-flex shrink-0 rounded-xl border border-gray-200 bg-gray-100 p-0.5">
    <button
      class="rounded-[10px] px-2 py-1.5 text-xs font-semibold transition sm:px-3 sm:text-sm"
      :class="modelValue === 'b2c' ? 'bg-[#007f80] text-white shadow-sm' : 'text-gray-600 hover:text-gray-900'"
      title="Частные клиенты"
      @click="emit('update:modelValue', 'b2c')"
    >
      B2C
    </button>
    <button
      class="rounded-[10px] px-2 py-1.5 text-xs font-semibold transition sm:px-3 sm:text-sm"
      :class="modelValue === 'b2b' ? 'bg-[#007f80] text-white shadow-sm' : 'text-gray-600 hover:text-gray-900'"
      title="Юридические лица"
      @click="emit('update:modelValue', 'b2b')"
    >
      B2B
    </button>
  </div>
</template>
