<script setup lang="ts">
import type { ServiceDescriptionMode } from './service-description-mode';

defineProps<{
  modelValue: ServiceDescriptionMode;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: ServiceDescriptionMode];
}>();

const options: Array<{ value: ServiceDescriptionMode; label: string }> = [
  { value: 'short', label: 'Кратко' },
  { value: 'full', label: 'Подробно' },
];
</script>

<template>
  <div
    class="inline-flex h-8 shrink-0 items-center rounded-lg border border-gray-200 bg-gray-50 p-0.5"
    role="group"
    aria-label="Формат описания услуги"
  >
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="h-7 rounded-md px-2.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50"
      :class="modelValue === option.value
        ? 'bg-white text-teal-700 shadow-sm'
        : 'text-gray-500 hover:text-gray-800'"
      :disabled="disabled"
      :aria-pressed="modelValue === option.value"
      @click="emit('update:modelValue', option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>
