<script setup lang="ts">
import { computed, ref } from 'vue';
import { X } from 'lucide-vue-next';
import type { ManagerBrandSeriesResponse } from '../../client';

const props = defineProps<{
  modelValue: number[];
  series: ManagerBrandSeriesResponse[];
  loading: boolean;
  error: string;
  savedTitles: Record<number, string>;
}>();
const emit = defineEmits<{ 'update:modelValue': [ids: number[]] }>();
const query = ref('');
const filtered = computed(() => props.series.filter((item) => item.title.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase())));
const title = (id: number) => props.series.find((item) => item.id === id)?.title || props.savedTitles[id] || `Серия #${id}`;
const toggle = (id: number) => emit('update:modelValue', props.modelValue.includes(id)
  ? props.modelValue.filter((value) => value !== id) : [...props.modelValue, id]);
</script>

<template>
  <fieldset class="min-w-0 sm:col-span-2">
    <legend class="text-sm font-semibold text-slate-700 dark:text-slate-200">Серии с этими условиями</legend>
    <div v-if="modelValue.length" class="mt-2 flex flex-wrap gap-1.5" aria-label="Выбранные серии">
      <button v-for="id in modelValue" :key="id" type="button" class="inline-flex max-w-full items-center gap-1 rounded-md bg-teal-50 px-2 py-1 text-left text-xs text-teal-800 dark:bg-teal-950 dark:text-teal-200" :aria-label="`Убрать серию ${title(id)}`" @click="toggle(id)">
        <span class="break-words">{{ title(id) }}</span><X class="h-3.5 w-3.5 shrink-0" />
      </button>
    </div>
    <label class="relative mt-2 block">
      <span class="sr-only">Найти серию</span>
      <input v-model="query" type="search" class="field-input" placeholder="Найти серию" />
    </label>
    <p v-if="loading" class="mt-2 text-xs text-slate-500" role="status">Загружаем серии…</p>
    <p v-else-if="error" class="mt-2 text-xs text-red-700 dark:text-red-300" role="alert">{{ error }}</p>
    <div v-else class="mt-2 max-h-44 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-700">
      <label v-for="item in filtered" :key="item.id" class="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800">
        <input type="checkbox" class="h-4 w-4 shrink-0 accent-teal-600" :checked="modelValue.includes(item.id)" @change="toggle(item.id)" />
        <span class="min-w-0 break-words">{{ item.title }}</span>
        <span class="ml-auto shrink-0 text-xs text-slate-500">{{ item.products_count }} тов.</span>
      </label>
      <p v-if="!filtered.length" class="px-3 py-2 text-sm text-slate-500">{{ query ? 'Серии не найдены' : 'У этого бренда пока нет серий' }}</p>
    </div>
    <p class="mt-2 text-xs text-slate-500" aria-live="polite">Выбрано: {{ modelValue.length }}. Для остальных серий действует общее правило бренда, если оно задано.</p>
  </fieldset>
</template>
