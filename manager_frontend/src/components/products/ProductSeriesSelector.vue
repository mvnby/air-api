<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { api, type ManagerBrandSeries } from '../../api';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{
  brandId: number | null;
  modelValue: number | null;
  legacySeriesTitle?: string;
}>();

const emit = defineEmits<{
  (event: 'update:modelValue', value: number | null): void;
  (event: 'select', value: ManagerBrandSeries | null): void;
}>();

const items = ref<ManagerBrandSeries[]>([]);
const loading = ref(false);
const error = ref('');
const query = ref('');
let requestVersion = 0;

const filteredItems = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase('ru');
  if (!needle) return items.value;
  return items.value.filter((item) => (
    item.id === props.modelValue
    || item.title.toLocaleLowerCase('ru').includes(needle)
  ));
});

const select = (raw: string) => {
  if (raw === '__none__') {
    emit('update:modelValue', null);
    emit('select', null);
    return;
  }
  const id = Number(raw || 0);
  const selected = items.value.find((item) => item.id === id) || null;
  emit('update:modelValue', selected?.id ?? null);
  emit('select', selected);
};

const load = async (brandId: number | null) => {
  const version = ++requestVersion;
  query.value = '';
  error.value = '';
  items.value = [];
  if (!brandId) {
    if (props.modelValue != null) select('');
    return;
  }

  loading.value = true;
  try {
    const response = await api.listManagerBrandSeries(brandId);
    if (version !== requestVersion) return;
    items.value = [...(response.items || [])].sort((left, right) => (
      Number(left.sort_order || 0) - Number(right.sort_order || 0)
      || left.title.localeCompare(right.title, 'ru')
    ));
    const selected = items.value.find((item) => item.id === props.modelValue) || null;
    if (props.modelValue != null && !selected) {
      error.value = 'Текущая серия не входит в список серий выбранного бренда. Выберите корректную серию или «Без серии».';
    } else if (selected) emit('select', selected);
  } catch (cause) {
    if (version !== requestVersion) return;
    error.value = `Не удалось загрузить серии: ${getApiErrorMessage(cause)}`;
  } finally {
    if (version === requestVersion) loading.value = false;
  }
};

watch(() => props.brandId, load, { immediate: true });
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between gap-3">
      <label class="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-slate-500" for="product-series-select">Серия</label>
      <span v-if="loading" class="text-xs text-gray-500">Загрузка серий…</span>
    </div>
    <template v-if="brandId">
      <input
        v-if="items.length > 7"
        v-model="query"
        type="search"
        class="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
        placeholder="Найти серию"
      />
      <select
        id="product-series-select"
        class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
        :value="modelValue ?? ''"
        :disabled="loading"
        @change="select(($event.target as HTMLSelectElement).value)"
      >
        <option v-if="modelValue == null && legacySeriesTitle" value="" disabled>Не привязана: {{ legacySeriesTitle }}</option>
        <option :value="modelValue == null && legacySeriesTitle ? '__none__' : ''">Без серии</option>
        <option v-for="series in filteredItems" :key="series.id" :value="series.id">
          {{ series.title }}{{ series.is_published ? '' : ' · черновик' }} · {{ series.products_count ?? 0 }} тов.
        </option>
      </select>
      <p v-if="modelValue == null && legacySeriesTitle" class="text-xs text-amber-700 dark:text-amber-300">Серия есть только в старых характеристиках. Выберите существующую серию или явно укажите «Без серии».</p>
      <p v-if="!loading && !error && !filteredItems.length" class="text-xs text-gray-500 dark:text-slate-400">У этого бренда пока нет серий.</p>
    </template>
    <p v-else class="text-xs text-gray-500 dark:text-slate-400">Сначала выберите бренд.</p>
    <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200">{{ error }}</p>
  </div>
</template>
