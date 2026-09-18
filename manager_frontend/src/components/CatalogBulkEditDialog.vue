<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Check, Eye, Plus, RefreshCw, Save, Trash2, X } from 'lucide-vue-next';
import { api, type ManagerBrand } from '../api';
import { ManagerFeaturesService, type ManagerFeatureResponse } from '../client';
import { useCatalogUsage } from '../composables/useCatalogUsage';
import { useSpecRegistry } from '../composables/useSpecRegistry';
import {
  catalogBulkApi,
  type CatalogBulkApplyResult,
  type CatalogBulkChange,
  type CatalogBulkKind,
  type CatalogBulkPreview,
} from '../services/catalog-bulk-api';
import { getApiErrorMessage } from '../utils/api-errors';
import ProductSeriesSelector from './products/ProductSeriesSelector.vue';
import SpecKeyCombobox from './SpecKeyCombobox.vue';
import SpecValueInput from './SpecValueInput.vue';

const props = defineProps<{ open: boolean; productIds: number[] }>();
const emit = defineEmits<{ close: []; applied: [result: CatalogBulkApplyResult] }>();

type SpecRow = { key: string; value: string };
type FeatureMode = 'add' | 'hide' | 'inherit';
type SpecMode = 'set' | 'fill_empty' | 'remove';
type Category = 'cat-household' | 'cat-multi' | 'cat-industrial' | null;

const tab = ref<CatalogBulkKind>('relations');
const brands = ref<ManagerBrand[]>([]);
const brandId = ref<number | null>(null);
const seriesId = ref<number | null>(null);
const specs = ref<SpecRow[]>([{ key: '', value: '' }]);
const specMode = ref<SpecMode>('set');
const featureMode = ref<FeatureMode>('add');
const featureIds = ref<number[]>([]);
const features = ref<ManagerFeatureResponse[]>([]);
const featureQuery = ref('');
const publication = ref<boolean>(true);
const category = ref<Category>(null);
const loading = ref(false);
const applying = ref(false);
const error = ref('');
const preview = ref<CatalogBulkPreview | null>(null);
const { knownSpecKeys, loadSpecRegistry, serializeSpecValue } = useSpecRegistry();
const catalogUsage = useCatalogUsage();

const tabs: Array<{ value: CatalogBulkKind; label: string }> = [
  { value: 'relations', label: 'Бренд и серия' }, { value: 'specs', label: 'Характеристики' },
  { value: 'features', label: 'Особенности' }, { value: 'publication', label: 'Публикация' },
  { value: 'category', label: 'Категория' },
];
const categoryOptions: Array<{ value: Category; label: string }> = [
  { value: null, label: 'Авто' }, { value: 'cat-household', label: 'Бытовые' },
  { value: 'cat-multi', label: 'Мульти-сплит' }, { value: 'cat-industrial', label: 'Промышленные' },
];
const brandsSorted = computed(() => [...brands.value].sort((left, right) => (
  Number(left.sort_order || 0) - Number(right.sort_order || 0)
  || left.title.localeCompare(right.title, 'ru')
)));
const visibleFeatures = computed(() => {
  const query = featureQuery.value.trim().toLocaleLowerCase('ru');
  return features.value.filter(feature => !query || `${feature.name} ${feature.slug}`.toLocaleLowerCase('ru').includes(query));
});
const selectedFeatureIds = computed(() => new Set(featureIds.value));
const selectedCount = computed(() => new Set(props.productIds).size);
const changeFingerprint = computed(() => JSON.stringify({
  ids: [...props.productIds].sort((left, right) => left - right), tab: tab.value, brandId: brandId.value,
  seriesId: seriesId.value, specs: specs.value, specMode: specMode.value, featureMode: featureMode.value,
  featureIds: [...featureIds.value].sort((left, right) => left - right), publication: publication.value, category: category.value,
}));

const clearPreview = () => { preview.value = null; error.value = ''; };
const close = () => { if (!loading.value && !applying.value) emit('close'); };
const reset = () => {
  tab.value = 'relations';
  brandId.value = null;
  seriesId.value = null;
  specs.value = [{ key: '', value: '' }];
  specMode.value = 'set';
  featureMode.value = 'add';
  featureIds.value = [];
  featureQuery.value = '';
  publication.value = true;
  category.value = null;
  clearPreview();
};
const loadCatalogInputs = async () => {
  try {
    const [brandResponse, featureResponse] = await Promise.all([
      api.listManagerBrands(),
      ManagerFeaturesService.listManagerFeatures(undefined, undefined, undefined, undefined, undefined, true),
    ]);
    brands.value = brandResponse.items || [];
    features.value = featureResponse.items || [];
  } catch (cause) {
    error.value = `Не удалось загрузить справочники: ${getApiErrorMessage(cause)}`;
  }
};
const selectTab = (next: CatalogBulkKind) => { tab.value = next; clearPreview(); };
const addSpec = () => { if (specs.value.length < 30) specs.value.push({ key: '', value: '' }); };
const removeSpec = (index: number) => {
  if (specs.value.length === 1) specs.value = [{ key: '', value: '' }];
  else specs.value.splice(index, 1);
};
const toggleFeature = (id: number) => {
  featureIds.value = selectedFeatureIds.value.has(id)
    ? featureIds.value.filter(value => value !== id)
    : [...featureIds.value, id];
};
const buildChange = (): CatalogBulkChange | null => {
  if (tab.value === 'relations') return { kind: 'relations', brand_id: brandId.value, series_id: seriesId.value };
  if (tab.value === 'publication') return { kind: 'publication', is_published: publication.value };
  if (tab.value === 'category') return { kind: 'category', category: category.value };
  if (tab.value === 'features') {
    if (!featureIds.value.length) { error.value = 'Выберите хотя бы одну особенность'; return null; }
    return { kind: 'features', feature_ids: featureIds.value, feature_mode: featureMode.value };
  }
  const values: Record<string, string> = {};
  for (const row of specs.value) {
    const key = row.key.trim();
    if (key) values[key] = serializeSpecValue(key, row.value);
  }
  if (!Object.keys(values).length) { error.value = 'Укажите хотя бы одну характеристику'; return null; }
  return { kind: 'specs', specs: values, spec_mode: specMode.value };
};
const previewChanges = async () => {
  const change = buildChange();
  if (!change || !selectedCount.value) {
    if (!selectedCount.value) error.value = 'Выберите товары для изменения';
    return;
  }
  const fingerprint = changeFingerprint.value;
  const productIds = [...new Set(props.productIds)];
  loading.value = true;
  error.value = '';
  try {
    const result = await catalogBulkApi.preview(productIds, change);
    if (fingerprint !== changeFingerprint.value) return;
    preview.value = result;
  }
  catch (cause) {
    if (fingerprint === changeFingerprint.value) error.value = getApiErrorMessage(cause) || 'Не удалось рассчитать изменения';
  }
  finally { loading.value = false; }
};
const applyChanges = async () => {
  if (!preview.value?.token || applying.value) return;
  const startedAt = performance.now();
  applying.value = true;
  error.value = '';
  try {
    const result = await catalogBulkApi.apply(preview.value.token);
    catalogUsage.track('bulk_edit', 'success', performance.now() - startedAt);
    emit('applied', result);
    emit('close');
  } catch (cause) {
    catalogUsage.track('bulk_edit', 'failed', performance.now() - startedAt);
    const status = Number((cause as { status?: number })?.status || 0);
    error.value = status === 409
      ? 'Товары изменились после предпросмотра. Рассчитайте изменения заново.'
      : getApiErrorMessage(cause) || 'Не удалось применить изменения';
    if (status === 409) preview.value = null;
  } finally { applying.value = false; }
};
const featureLabel = (value: unknown) => features.value.find(feature => feature.id === Number(value))?.name || `#${value}`;
const categoryLabel = (value: unknown) => categoryOptions.find(option => option.value === value)?.label || 'Авто';
const fieldLabel: Record<string, string> = {
  brand: 'Бренд', series: 'Серия', is_published: 'Публикация', category: 'Категория',
  features: 'Особенности', assignments: 'Ручные настройки', tags: 'Теги', is_inverter: 'Инвертор', power_cooling: 'Мощность охлаждения, кВт',
};
const displayValue = (key: string, value: unknown): string => {
  if ((key === 'brand' || key === 'series') && value && typeof value === 'object') return String((value as { title?: string }).title || '—');
  if (key === 'is_inverter') return value ? 'Да' : 'Нет';
  if (key === 'assignments' && Array.isArray(value)) return value.map(item => `${featureLabel(item.feature_id)}: ${item.is_enabled ? 'добавлена' : 'скрыта'}`).join(', ') || 'Наследуются';
  if (key === 'is_published') return value ? 'Опубликован' : 'Скрыт';
  if (key === 'category') return categoryLabel(value);
  if (key === 'features' && Array.isArray(value)) return value.map(featureLabel).join(', ') || '—';
  if (Array.isArray(value)) return value.length ? value.map(item => typeof item === 'object' ? JSON.stringify(item) : String(item)).join(', ') : '—';
  if (value && typeof value === 'object') return Object.entries(value as Record<string, unknown>).map(([itemKey, itemValue]) => `${itemKey}: ${itemValue}`).join(', ');
  return value === null || value === undefined || value === '' ? '—' : String(value);
};
const stateRows = (state: Record<string, unknown>) => Object.entries(state).map(([key, value]) => ({ key, label: fieldLabel[key] || key, value: displayValue(key, value) }));

watch(() => props.open, open => {
  if (!open) return;
  reset();
  void Promise.all([loadSpecRegistry(), loadCatalogInputs()]);
}, { immediate: true });
watch(changeFingerprint, clearPreview);
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-[70] overflow-y-auto bg-black/50 p-4" role="dialog" aria-modal="true" aria-label="Массовое изменение товаров" @click.self="close">
    <section class="mx-auto my-6 w-full max-w-4xl rounded-xl bg-white shadow-xl dark:bg-slate-900" @click.stop>
      <header class="flex items-start justify-between gap-4 border-b border-slate-200 p-4 dark:border-slate-700">
        <div><h2 class="text-lg font-semibold text-slate-900 dark:text-white">Массовое изменение</h2><p class="text-sm text-slate-500">Выбрано товаров: {{ selectedCount }}. Сначала проверьте результат.</p></div>
        <button type="button" class="btn-mini-outline h-9 w-9 justify-center p-0" aria-label="Закрыть" @click="close"><X :size="17" /></button>
      </header>
      <fieldset :disabled="applying" class="contents">
      <div class="border-b border-slate-200 px-4 dark:border-slate-700"><div class="flex overflow-x-auto" role="tablist" aria-label="Тип изменения"><button v-for="item in tabs" :key="item.value" type="button" class="shrink-0 border-b-2 px-3 py-3 text-sm font-medium" :class="tab === item.value ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500'" :aria-selected="tab === item.value" @click="selectTab(item.value)">{{ item.label }}</button></div></div>
      <div class="p-4 sm:p-6">
        <p v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
        <section v-if="tab === 'relations'" class="grid gap-4 sm:grid-cols-2"><label class="field-label">Бренд<select v-model="brandId" class="field-input mt-1"><option :value="null">Без бренда</option><option v-for="brand in brandsSorted" :key="brand.id" :value="brand.id">{{ brand.title }}</option></select></label><ProductSeriesSelector :brand-id="brandId" :model-value="seriesId" @update:model-value="seriesId = $event" /></section>
        <section v-else-if="tab === 'specs'" class="space-y-3"><div class="flex flex-wrap gap-2"><button v-for="mode in [{ value: 'set', label: 'Задать' }, { value: 'fill_empty', label: 'Заполнить пустые' }, { value: 'remove', label: 'Удалить' }]" :key="mode.value" type="button" class="rounded-md px-3 py-2 text-sm" :class="specMode === mode.value ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200'" @click="specMode = mode.value as SpecMode">{{ mode.label }}</button></div><div v-for="(row, index) in specs" :key="index" class="grid gap-2 sm:grid-cols-[1fr_1fr_auto]"><SpecKeyCombobox v-model="row.key" :known-keys="knownSpecKeys" /><SpecValueInput v-model="row.value" :spec-key="row.key" :disabled="specMode === 'remove'" :placeholder="specMode === 'remove' ? 'Не требуется' : 'Значение'" /><button type="button" class="btn-mini-outline justify-center" aria-label="Удалить строку" @click="removeSpec(index)"><Trash2 :size="16" /></button></div><button type="button" class="inline-flex items-center gap-1 text-sm font-medium text-brand-700" :disabled="specs.length >= 30" @click="addSpec"><Plus :size="16" />Добавить характеристику</button></section>
        <section v-else-if="tab === 'features'" class="space-y-3"><div class="flex flex-wrap gap-2"><button v-for="mode in [{ value: 'add', label: 'Добавить' }, { value: 'hide', label: 'Скрыть' }, { value: 'inherit', label: 'Наследовать' }]" :key="mode.value" type="button" class="rounded-md px-3 py-2 text-sm" :class="featureMode === mode.value ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200'" @click="featureMode = mode.value as FeatureMode">{{ mode.label }}</button></div><input v-model="featureQuery" class="field-input" type="search" placeholder="Найти особенность" /><div class="max-h-56 divide-y overflow-auto rounded-lg border border-slate-200 dark:border-slate-700"><button v-for="feature in visibleFeatures" :key="feature.id" type="button" class="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800" @click="toggleFeature(feature.id)"><span class="flex h-5 w-5 items-center justify-center rounded border" :class="selectedFeatureIds.has(feature.id) ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300'"> <Check v-if="selectedFeatureIds.has(feature.id)" :size="14" /> </span><span><span class="block text-sm font-medium">{{ feature.name }}</span><span class="block text-xs text-slate-500">{{ feature.category.name }} · {{ feature.slug }}</span></span></button></div></section>
        <section v-else-if="tab === 'publication'" class="flex gap-3"><button type="button" class="rounded-lg px-4 py-3 text-sm font-medium" :class="publication ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200'" @click="publication = true">Опубликовать</button><button type="button" class="rounded-lg px-4 py-3 text-sm font-medium" :class="!publication ? 'bg-slate-700 text-white' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200'" @click="publication = false">Скрыть</button></section>
        <section v-else class="flex flex-wrap gap-2"><button v-for="option in categoryOptions" :key="option.label" type="button" class="rounded-lg px-4 py-3 text-sm font-medium" :class="category === option.value ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200'" @click="category = option.value">{{ option.label }}</button></section>
        <section v-if="preview" class="mt-6 rounded-xl border border-slate-200 p-4 dark:border-slate-700"><div class="flex flex-wrap items-center justify-between gap-3"><div><h3 class="font-semibold">Предпросмотр</h3><p class="text-sm text-slate-500">Изменятся: {{ preview.changed_count }} из {{ preview.items.length }}. Действует {{ Math.ceil(preview.expires_in_seconds / 60) }} мин.</p></div><button type="button" class="btn-mini-outline inline-flex items-center gap-1" :disabled="loading" @click="previewChanges"><RefreshCw :size="15" />Пересчитать</button></div><div class="mt-3 max-h-64 overflow-auto rounded-lg border border-slate-100 dark:border-slate-800"><article v-for="item in preview.items.filter(item => item.changed)" :key="item.product_id" class="border-b border-slate-100 p-3 text-sm last:border-0 dark:border-slate-800"><p class="font-medium">{{ item.title }}</p><div class="mt-2 grid gap-2 sm:grid-cols-2"><div><p class="text-xs font-semibold text-slate-500">Было</p><p v-for="row in stateRows(item.before)" :key="row.key" class="text-slate-700 dark:text-slate-200">{{ row.label }}: {{ row.value }}</p></div><div><p class="text-xs font-semibold text-slate-500">Станет</p><p v-for="row in stateRows(item.after)" :key="row.key" class="text-slate-700 dark:text-slate-200">{{ row.label }}: {{ row.value }}</p></div></div></article></div></section>
      </div>
      </fieldset>
      <footer class="flex justify-end gap-3 border-t border-slate-200 p-4 dark:border-slate-700"><button type="button" class="btn-mini-outline" :disabled="loading || applying" @click="close">Отмена</button><button v-if="preview" type="button" class="btn-mini" :disabled="applying || !preview.changed_count" @click="applyChanges"><Save :size="16" />{{ applying ? 'Применяем…' : 'Применить' }}</button><button v-else type="button" class="btn-mini" :disabled="loading || !selectedCount" data-testid="bulk-preview" @click="previewChanges"><Eye :size="16" />{{ loading ? 'Считаем…' : 'Предпросмотр' }}</button></footer>
    </section>
  </div>
</template>
