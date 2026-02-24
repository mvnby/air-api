<script setup lang="ts">
import type { Segment } from '../../api';

defineProps<{ modelValue: Segment }>();
const emit = defineEmits<{ 'update:modelValue': [value: Segment] }>();
</script>

<template>
  <div class="inline-flex rounded-[12px] bg-gray-100 p-1 border border-gray-200 shrink-0">
    <button
      class="rounded-[12px] px-3 py-1.5 md:px-4 md:py-2 text-sm font-semibold transition"
      :class="modelValue === 'b2c' ? 'bg-[#007f80] text-white shadow-sm' : 'text-gray-600 hover:text-gray-900'"
      @click="emit('update:modelValue', 'b2c')"
    >
      Частные (B2C)
    </button>
    <button
      class="rounded-[12px] px-3 py-1.5 md:px-4 md:py-2 text-sm font-semibold transition"
      :class="modelValue === 'b2b' ? 'bg-[#007f80] text-white shadow-sm' : 'text-gray-600 hover:text-gray-900'"
      @click="emit('update:modelValue', 'b2b')"
    >
      Юр. лица (B2B)
    </button>
  </div>
</template>
