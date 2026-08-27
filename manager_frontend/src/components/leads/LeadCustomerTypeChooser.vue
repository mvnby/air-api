<script setup lang="ts">
export type LeadCustomerType = 'individual' | 'individual_entrepreneur' | 'company';

defineProps<{
  modelValue: LeadCustomerType | '';
  showError: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: LeadCustomerType];
}>();

const options: Array<{ value: LeadCustomerType; label: string; hint: string; icon: string }> = [
  { value: 'individual', label: 'Физлицо', hint: 'частный клиент', icon: 'person' },
  { value: 'individual_entrepreneur', label: 'ИП', hint: 'работает от своего имени', icon: 'storefront' },
  { value: 'company', label: 'Юрлицо', hint: 'организация', icon: 'business' },
];
</script>

<template>
  <div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all"
      :class="modelValue === option.value
        ? 'border-teal-500 bg-teal-50 text-teal-800 shadow-sm dark:border-teal-400 dark:bg-teal-500/10 dark:text-teal-200'
        : showError
          ? 'border-red-300 bg-red-50 text-slate-700 dark:border-red-500/50 dark:bg-red-500/10 dark:text-slate-200'
          : 'border-slate-200 bg-white text-slate-700 hover:border-teal-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200'"
      @click="emit('update:modelValue', option.value)"
    >
      <span class="material-icons-round text-[20px]">{{ option.icon }}</span>
      <span class="min-w-0">
        <span class="block text-sm font-bold">{{ option.label }}</span>
        <span class="block text-xs opacity-70">{{ option.hint }}</span>
      </span>
    </button>
  </div>
</template>
