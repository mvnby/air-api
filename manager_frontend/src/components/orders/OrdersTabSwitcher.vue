<script setup lang="ts">
import type { Segment } from '../../api';

defineProps<{ modelValue: Segment }>();
const emit = defineEmits<{ 'update:modelValue': [value: Segment] }>();
</script>

<template>
  <div class="inline-flex rounded-[12px] bg-slate-800 p-1">
    <button
      class="rounded-[12px] px-4 py-2 text-sm font-semibold transition"
      :class="modelValue === 'b2c' ? 'bg-[#007f80] text-white' : 'text-slate-300 hover:text-white'"
      @click="emit('update:modelValue', 'b2c')"
    >
      Частные клиенты (B2C)
    </button>
    <button
      class="rounded-[12px] px-4 py-2 text-sm font-semibold transition"
      :class="modelValue === 'b2b' ? 'bg-[#007f80] text-white' : 'text-slate-300 hover:text-white'"
      @click="emit('update:modelValue', 'b2b')"
    >
      Организации (B2B)
    </button>
  </div>
</template>
