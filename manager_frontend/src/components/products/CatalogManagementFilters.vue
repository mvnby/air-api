<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api } from '../../api';
import { ManagerFeaturesService, type ManagerFeatureResponse } from '../../client';
import CatalogDecisionFilters from '../catalog-decision/CatalogDecisionFilters.vue';
import { catalogDecisionApi } from '../../services/catalog-decision-api';
import type { CatalogManagementFilterState, CatalogManagementSort } from '../../services/catalog-management-api';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ modelValue: CatalogManagementFilterState; sort: CatalogManagementSort }>();
const emit = defineEmits<{ 'update:modelValue': [value: CatalogManagementFilterState]; 'update:sort': [value: CatalogManagementSort]; reset: [] }>();
const brands = ref<Array<{ id: number; title: string }>>([]);
const series = ref<Array<{ id: number; title: string; brandId?: number | null }>>([]);
const suppliers = ref<Array<{ id: number; name: string }>>([]);
const features = ref<ManagerFeatureResponse[]>([]);
const error = ref('');
const resetKey = ref(0);
const expanded = ref(typeof window !== 'undefined' && window.innerWidth >= 1024);
const activeCount = computed(() => Object.entries(props.modelValue).filter(([key, value]) => key !== 'search' && !(key === 'includeOrderable' && value === true) && value != null && (!Array.isArray(value) || value.length > 0)).length);
const update = (patch: Partial<CatalogManagementFilterState>) => emit('update:modelValue', { ...props.modelValue, ...patch });
const reset = () => { resetKey.value++; emit('reset'); };
const load = async () => {
  error.value = '';
  const results = await Promise.allSettled([
    catalogDecisionApi.filterOptions(), api.listSuppliers(),
    ManagerFeaturesService.listManagerFeatures(undefined, undefined, undefined, undefined, undefined, true),
  ]);
  const options = results[0];
  if (options.status === 'fulfilled') {
    brands.value = options.value.brands ?? [];
    series.value = (options.value.series ?? []).map(item => ({ ...item, brandId: item.brand_id }));
  } else error.value = getApiErrorMessage(options.reason);
  const supply = results[1];
  if (supply.status === 'fulfilled') suppliers.value = supply.value.items;
  else error.value = getApiErrorMessage(supply.reason);
  const featureLibrary = results[2];
  if (featureLibrary.status === 'fulfilled') features.value = featureLibrary.value.items;
  else error.value = getApiErrorMessage(featureLibrary.reason);
};
onMounted(load);
</script>

<template>
  <div class="mb-4 space-y-3">
    <input type="search" class="w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm dark:border-slate-700 dark:bg-slate-800" placeholder="Найти товар, бренд или серию" aria-label="Поиск по каталогу" :value="modelValue.search ?? ''" @input="update({ search: ($event.target as HTMLInputElement).value || undefined })" />
    <details :open="expanded" @toggle="expanded = ($event.target as HTMLDetailsElement).open" class="space-y-3">
      <summary class="cursor-pointer py-2 text-sm font-semibold text-gray-700 dark:text-slate-200">Фильтры<span v-if="activeCount"> · {{ activeCount }}</span><span class="ml-2 font-normal text-gray-500">Бренд, серия, поставщик, характеристики</span></summary>
    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-gray-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
      <label class="min-w-40 flex-1 text-xs font-semibold text-gray-600 dark:text-slate-300">Поставщик
        <select class="mt-1 block w-full rounded-lg border bg-transparent p-2 text-sm" aria-label="Поставщик" :value="modelValue.supplierId ?? ''" @change="update({ supplierId: Number(($event.target as HTMLSelectElement).value) || undefined })">
          <option value="">Все поставщики</option><option v-for="supplier in suppliers" :key="supplier.id" :value="supplier.id">{{ supplier.name }}</option>
        </select>
      </label>
      <label class="text-xs font-semibold text-gray-600 dark:text-slate-300">Публикация
        <select class="mt-1 block rounded-lg border bg-transparent p-2 text-sm" aria-label="Публикация" :value="modelValue.isPublished == null ? '' : String(modelValue.isPublished)" @change="update({ isPublished: ($event.target as HTMLSelectElement).value === '' ? undefined : ($event.target as HTMLSelectElement).value === 'true' })">
          <option value="">Все, включая черновики</option><option value="true">Опубликованы</option><option value="false">Не опубликованы</option>
        </select>
      </label>
      <label class="text-xs font-semibold text-gray-600 dark:text-slate-300">Заполненность
        <select class="mt-1 block rounded-lg border bg-transparent p-2 text-sm" aria-label="Заполненность" :value="modelValue.missing ?? ''" @change="update({ missing: (($event.target as HTMLSelectElement).value || undefined) as CatalogManagementFilterState['missing'] })">
          <option value="">Любая</option><option value="brand">Без бренда</option><option value="series">Без серии</option><option value="image">Без фото</option><option value="price">Без цены</option>
        </select>
      </label>
      <label class="min-w-44 text-xs font-semibold text-gray-600 dark:text-slate-300">Особенность
        <select class="mt-1 block w-full rounded-lg border bg-transparent p-2 text-sm" aria-label="Особенность" :value="modelValue.featureId ?? ''" @change="update({ featureId: Number(($event.target as HTMLSelectElement).value) || undefined, hasFeature: Number(($event.target as HTMLSelectElement).value) ? true : undefined })">
          <option value="">Любая</option><option v-for="feature in features" :key="feature.id" :value="feature.id">{{ feature.name }}</option>
        </select>
      </label>
      <div v-if="modelValue.featureId" class="text-xs font-semibold text-gray-600 dark:text-slate-300"><span class="mb-1 block">Наличие особенности</span><div class="inline-flex overflow-hidden rounded-lg border"><button type="button" class="px-3 py-2" :class="modelValue.hasFeature ? 'bg-brand-600 text-white' : ''" @click="update({ hasFeature: true })">Есть</button><button type="button" class="border-l px-3 py-2" :class="modelValue.hasFeature === false ? 'bg-brand-600 text-white' : ''" @click="update({ hasFeature: false })">Нет</button></div></div>
      <div class="text-xs font-semibold text-gray-600 dark:text-slate-300"><span class="mb-1 block">Яндекс</span><div class="inline-flex overflow-hidden rounded-lg border"><button type="button" class="px-3 py-2" :class="modelValue.inYandexFeed === true ? 'bg-brand-600 text-white' : ''" @click="update({ inYandexFeed: modelValue.inYandexFeed === true ? undefined : true })">В выгрузке</button><button type="button" class="border-l px-3 py-2" :class="modelValue.inYandexFeed === false ? 'bg-brand-600 text-white' : ''" @click="update({ inYandexFeed: modelValue.inYandexFeed === false ? undefined : false })">Вне выгрузки</button></div></div>
      <label class="text-xs font-semibold text-gray-600 dark:text-slate-300">Площадь, м²
        <span class="mt-1 flex items-center gap-1"><input type="number" min="0" class="w-20 rounded-lg border bg-transparent p-2 text-sm" placeholder="От" aria-label="Площадь от" :value="modelValue.areaMin ?? ''" @input="update({ areaMin: Number(($event.target as HTMLInputElement).value) || undefined })" /><span>—</span><input type="number" min="0" class="w-20 rounded-lg border bg-transparent p-2 text-sm" placeholder="До" aria-label="Площадь до" :value="modelValue.areaMax ?? ''" @input="update({ areaMax: Number(($event.target as HTMLInputElement).value) || undefined })" /></span>
      </label>
      <label class="text-xs font-semibold text-gray-600 dark:text-slate-300">Сортировка
        <select class="mt-1 block rounded-lg border bg-transparent p-2 text-sm" aria-label="Сортировка" :value="sort" @change="emit('update:sort', ($event.target as HTMLSelectElement).value as CatalogManagementSort)">
          <option value="recommended">Рекомендуемые</option><option value="title">По названию</option><option value="newest">Сначала новые</option><option value="price_asc">Сначала дешевле</option><option value="price_desc">Сначала дороже</option>
        </select>
      </label>
      <button type="button" class="rounded-lg border px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:text-slate-200 dark:hover:bg-slate-700" @click="reset">Сбросить фильтры</button>
    </div>
    <div v-if="error" role="alert" class="text-sm text-red-700">{{ error }} <button type="button" class="underline" @click="load">Повторить загрузку фильтров</button></div>
    <CatalogDecisionFilters :model-value="modelValue" :brands="brands" :series="series" :reset-key="resetKey" hide-search @update:model-value="update" @reset="reset" />
    <button type="button" class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white lg:hidden" @click="expanded = false">Показать товары</button>
    </details>
  </div>
</template>
