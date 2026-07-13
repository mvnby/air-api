<script setup lang="ts">
import { RefreshCw, Search, X } from 'lucide-vue-next';
import { ATTENTION_FILTER_OPTIONS } from './registry';
import type { EquipmentAttentionFilter } from './types';

defineProps<{
  modelValue: string;
  attention: EquipmentAttentionFilter;
  loading: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: string];
  'update:attention': [value: EquipmentAttentionFilter];
  refresh: [];
}>();

const updateSearch = (event: Event) => {
  emit('update:modelValue', (event.target as HTMLInputElement).value);
};
</script>

<template>
  <section class="border-y border-gray-200 py-3 dark:border-slate-700">
    <div class="flex items-center gap-2">
      <label class="relative min-w-0 flex-1 sm:max-w-xl">
        <span class="sr-only">Поиск оборудования</span>
        <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-slate-500" />
        <input
          :value="modelValue"
          type="search"
          class="h-10 w-full rounded-lg border border-gray-200 bg-white pl-9 pr-9 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
          placeholder="Оборудование, клиент, адрес, серийный номер"
          @input="updateSearch"
        >
        <button
          v-if="modelValue"
          type="button"
          class="absolute right-1.5 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 dark:text-slate-500 dark:hover:bg-slate-700 dark:hover:text-white"
          title="Очистить поиск"
          aria-label="Очистить поиск"
          @click="emit('update:modelValue', '')"
        >
          <X class="h-4 w-4" />
        </button>
      </label>

      <button
        type="button"
        class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-600 transition hover:border-teal-300 hover:text-teal-700 disabled:cursor-wait disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-teal-600 dark:hover:text-teal-300"
        :disabled="loading"
        title="Обновить список"
        aria-label="Обновить список"
        @click="emit('refresh')"
      >
        <RefreshCw class="h-4 w-4" :class="loading ? 'animate-spin' : ''" />
      </button>
    </div>

    <div class="mt-3 overflow-x-auto pb-1">
      <div class="inline-flex min-w-max gap-1 rounded-lg bg-gray-100 p-1 dark:bg-slate-800" role="tablist" aria-label="Статус оборудования">
        <button
          v-for="option in ATTENTION_FILTER_OPTIONS"
          :key="option.value"
          type="button"
          role="tab"
          class="h-8 rounded-md px-3 text-xs font-semibold transition sm:text-sm"
          :class="attention === option.value
            ? 'bg-white text-teal-700 shadow-sm dark:bg-slate-700 dark:text-teal-300'
            : 'text-gray-600 hover:bg-white/70 hover:text-gray-900 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white'"
          :aria-selected="attention === option.value"
          @click="emit('update:attention', option.value)"
        >
          {{ option.label }}
        </button>
      </div>
    </div>
  </section>
</template>
