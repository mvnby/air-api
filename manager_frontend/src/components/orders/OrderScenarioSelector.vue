<script setup lang="ts">
export type OrderScenarioOption = {
  label: string;
  hint?: string | null;
  workflow_type: string;
  service_type?: string | null;
};

defineProps<{
  options: OrderScenarioOption[];
  modelValue: OrderScenarioOption | null;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: OrderScenarioOption): void;
}>();

const selected = (option: OrderScenarioOption, current: OrderScenarioOption | null) =>
  current?.workflow_type === option.workflow_type && current?.service_type === option.service_type;
</script>

<template>
  <div class="grid grid-cols-1 gap-2 sm:grid-cols-2" role="group" aria-label="Сценарий заказа">
    <button
      v-for="option in options"
      :key="`${option.workflow_type}:${option.service_type || ''}`"
      type="button"
      :disabled="disabled"
      :aria-pressed="selected(option, modelValue)"
      class="rounded-xl border px-4 py-3 text-left transition-colors disabled:opacity-50"
      :class="selected(option, modelValue)
        ? 'border-brand-500 bg-brand-500/10 text-brand-300'
        : 'border-slate-600 bg-slate-800 text-slate-200 hover:border-brand-400'"
      @click="emit('update:modelValue', option)"
    >
      <span class="block text-sm font-semibold">{{ option.label }}</span>
      <span v-if="option.hint" class="block text-xs opacity-70">{{ option.hint }}</span>
    </button>
  </div>
</template>
