<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { Archive, Plus, Search, Trash2, X } from 'lucide-vue-next';
import {
  ManagerFeaturesService,
  ManagerBrandsService,
  type FeatureCategoryResponse,
  type FeatureCreatePayload,
  type FeatureRulePayload,
  type ManagerFeatureResponse,
  type ManagerBrandResponse,
} from '../client';
import MediaField from '../components/MediaField.vue';
import { getApiErrorMessage } from '../utils/api-errors';

type RuleDraft = FeatureRulePayload & { valueText: string };
type FeatureDraft = Omit<FeatureCreatePayload, 'rules'> & { rules: RuleDraft[] };

const categories = ref<FeatureCategoryResponse[]>([]);
const items = ref<ManagerFeatureResponse[]>([]);
const brands = ref<ManagerBrandResponse[]>([]);
const loading = ref(true);
const saving = ref(false);
const error = ref('');
const search = ref('');
const categoryId = ref<number | ''>('');
const brandId = ref<number | ''>('');
const scope = ref<FeatureCreatePayload['scope_type'] | ''>('');
const showArchived = ref(false);
const editingId = ref<number | null>(null);
const editorOpen = ref(false);

const blankDraft = (): FeatureDraft => ({
  name: '',
  slug: null,
  short_description: null,
  full_description: null,
  category_id: categories.value[0]?.id || 0,
  scope_type: 'universal',
  brand_id: null,
  icon: null,
  image_url: null,
  video_url: null,
  footnote: null,
  source_url: null,
  aliases: [],
  seo_title: null,
  seo_description: null,
  source_notes: null,
  legal_notes: null,
  is_active: true,
  sort_order: 0,
  rules: [],
});

const draft = reactive<FeatureDraft>(blankDraft());
const scopeLabels: Record<string, string> = {
  universal: 'Общая', brand: 'Бренд', series: 'Серия', product: 'Товар', derived: 'По правилу',
};
const sourceCount = (item: ManagerFeatureResponse) =>
  Number(item.brands_count || 0) + Number(item.series_count || 0) + Number(item.products_count || 0);

const filteredItems = computed(() => items.value);
const iconValue = computed({
  get: () => draft.icon || '',
  set: (value: string) => { draft.icon = value || null; },
});
const imageValue = computed({
  get: () => draft.image_url || '',
  set: (value: string) => { draft.image_url = value || null; },
});

const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    const [categoryRows, brandRows, response] = await Promise.all([
      categories.value.length ? Promise.resolve(categories.value) : ManagerFeaturesService.listManagerFeatureCategories(),
      brands.value.length ? Promise.resolve({ items: brands.value }) : ManagerBrandsService.listManagerBrands(),
      ManagerFeaturesService.listManagerFeatures(
        search.value.trim() || undefined,
        categoryId.value || undefined,
        brandId.value || undefined,
        scope.value || undefined,
        !showArchived.value,
      ),
    ]);
    categories.value = categoryRows;
    brands.value = brandRows.items;
    items.value = response.items;
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    loading.value = false;
  }
};

const resetDraft = (feature?: ManagerFeatureResponse) => {
  const next = feature ? {
    name: feature.name,
    slug: feature.slug,
    short_description: feature.short_description || null,
    full_description: feature.full_description || null,
    category_id: feature.category.id,
    scope_type: feature.scope_type,
    brand_id: feature.brand_id || null,
    icon: feature.icon || null,
    image_url: feature.image_url || null,
    video_url: feature.video_url || null,
    footnote: feature.footnote || null,
    source_url: feature.source_url || null,
    aliases: feature.aliases || [],
    seo_title: feature.seo_title || null,
    seo_description: feature.seo_description || null,
    source_notes: feature.source_notes || null,
    legal_notes: feature.legal_notes || null,
    is_active: feature.is_active,
    sort_order: feature.sort_order,
    rules: (feature.rules || []).map((rule) => ({
      spec_key: rule.spec_key,
      operator: rule.operator,
      target_value: rule.target_value,
      is_active: rule.is_active,
      sort_order: rule.sort_order,
      valueText: rule.target_value == null ? '' : typeof rule.target_value === 'string'
        ? rule.target_value : JSON.stringify(rule.target_value),
    })),
  } satisfies FeatureDraft : blankDraft();
  Object.assign(draft, next);
};

const openCreate = () => {
  editingId.value = null;
  resetDraft();
  editorOpen.value = true;
};

const openEdit = (feature: ManagerFeatureResponse) => {
  editingId.value = feature.id;
  resetDraft(feature);
  editorOpen.value = true;
};

const addRule = () => draft.rules.push({
  spec_key: '', operator: 'eq', target_value: '', is_active: true,
  sort_order: draft.rules.length * 10, valueText: '',
});

const parseRuleValue = (rule: RuleDraft) => {
  if (rule.operator === 'exists') return rule.valueText.trim() !== 'false';
  const raw = rule.valueText.trim();
  if (rule.operator === 'in') {
    if (raw.startsWith('[')) return JSON.parse(raw);
    return raw.split(',').map((item) => item.trim()).filter(Boolean);
  }
  if (/^-?\d+(?:[.,]\d+)?$/.test(raw)) return Number(raw.replace(',', '.'));
  if (raw === 'true' || raw === 'false') return raw === 'true';
  return raw;
};

const save = async () => {
  if (!draft.name.trim() || !draft.category_id || saving.value) return;
  saving.value = true;
  error.value = '';
  try {
    const payload: FeatureCreatePayload = {
      ...draft,
      name: draft.name.trim(),
      slug: draft.slug?.trim() || null,
      aliases: (draft.aliases || []).map((item) => item.trim()).filter(Boolean),
      brand_id: draft.scope_type === 'brand' ? draft.brand_id : null,
      rules: draft.rules.map(({ valueText: _valueText, ...rule }, index) => ({
        ...rule,
        target_value: parseRuleValue(draft.rules[index]!),
        sort_order: index * 10,
      })),
    };
    if (editingId.value) await ManagerFeaturesService.updateManagerFeature(editingId.value, payload);
    else await ManagerFeaturesService.createManagerFeature(payload);
    editorOpen.value = false;
    await load();
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    saving.value = false;
  }
};

const archive = async (feature: ManagerFeatureResponse) => {
  if (!window.confirm(`Архивировать фичу «${feature.name}»?`)) return;
  try {
    await ManagerFeaturesService.archiveManagerFeature(feature.id);
    await load();
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  }
};

onMounted(load);
</script>

<template>
  <div class="min-h-full bg-gray-50 px-4 py-6 dark:bg-slate-950 sm:px-6">
    <div class="mx-auto max-w-[1500px]">
      <header class="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 class="text-2xl font-bold text-gray-950 dark:text-white">Библиотека фич</h1>
          <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">Единые преимущества для брендов, серий и товаров</p>
        </div>
        <button type="button" class="inline-flex h-10 items-center gap-2 rounded-md bg-teal-600 px-4 text-sm font-semibold text-white hover:bg-teal-700" @click="openCreate">
          <Plus class="h-4 w-4" />Новая фича
        </button>
      </header>

      <div class="mb-4 grid gap-2 border-y border-gray-200 bg-white py-3 dark:border-slate-800 dark:bg-slate-950 lg:grid-cols-[minmax(220px,1fr)_190px_190px_160px_auto]">
        <label class="relative"><Search class="absolute left-3 top-2.5 h-4 w-4 text-gray-400" /><input v-model="search" class="h-9 w-full rounded-md border border-gray-200 bg-transparent pl-9 pr-3 text-sm dark:border-slate-700" placeholder="Название или slug" @keyup.enter="load" /></label>
        <select v-model="categoryId" class="h-9 rounded-md border border-gray-200 bg-transparent px-3 text-sm dark:border-slate-700" @change="load"><option value="">Все категории</option><option v-for="category in categories" :key="category.id" :value="category.id">{{ category.name }}</option></select>
        <select v-model="brandId" class="h-9 rounded-md border border-gray-200 bg-transparent px-3 text-sm dark:border-slate-700" @change="load"><option value="">Все бренды</option><option v-for="brand in brands" :key="brand.id" :value="brand.id">{{ brand.title }}</option></select>
        <select v-model="scope" class="h-9 rounded-md border border-gray-200 bg-transparent px-3 text-sm dark:border-slate-700" @change="load"><option value="">Все области</option><option v-for="(label, value) in scopeLabels" :key="value" :value="value">{{ label }}</option></select>
        <button type="button" class="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-gray-200 px-3 text-sm font-semibold dark:border-slate-700" :class="showArchived ? 'bg-gray-900 text-white dark:bg-white dark:text-slate-950' : ''" @click="showArchived = !showArchived; load()"><Archive class="h-4 w-4" />Архив</button>
      </div>

      <p v-if="error" class="mb-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
      <div v-if="loading" class="py-20 text-center text-gray-500">Загрузка…</div>
      <div v-else class="overflow-hidden border-y border-gray-200 bg-white dark:border-slate-800 dark:bg-slate-950">
        <div v-for="feature in filteredItems" :key="feature.id" role="button" tabindex="0" class="grid w-full cursor-pointer gap-2 border-b border-gray-100 px-4 py-3 text-left last:border-0 hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-600 dark:border-slate-800 dark:hover:bg-slate-900 md:grid-cols-[minmax(240px,1fr)_180px_150px_150px_auto] md:items-center" @click="openEdit(feature)" @keydown.enter="openEdit(feature)" @keydown.space.prevent="openEdit(feature)">
          <div class="min-w-0"><p class="truncate font-semibold text-gray-950 dark:text-white">{{ feature.name }}</p><p class="truncate text-xs text-gray-500">{{ feature.slug }}<span v-if="feature.short_description"> · {{ feature.short_description }}</span></p></div>
          <span class="text-sm text-gray-600 dark:text-slate-300">{{ feature.category.name }}</span>
          <span class="text-sm text-gray-600 dark:text-slate-300">{{ scopeLabels[feature.scope_type] }}</span>
          <span class="text-xs text-gray-500">{{ sourceCount(feature) }} связей · {{ feature.rules?.length || 0 }} правил</span>
          <button v-if="feature.is_active" type="button" class="flex h-8 w-8 items-center justify-center rounded-md text-gray-400 hover:bg-red-50 hover:text-red-600" title="Архивировать" @click.stop="archive(feature)"><Archive class="h-4 w-4" /></button>
        </div>
        <p v-if="!filteredItems.length" class="py-16 text-center text-sm text-gray-500">Фичи не найдены</p>
      </div>
    </div>

    <div v-if="editorOpen" class="fixed inset-0 z-50 flex justify-end bg-black/45" @click.self="editorOpen = false">
      <form class="h-full w-full max-w-2xl overflow-y-auto bg-white p-5 shadow-2xl dark:bg-slate-950" @submit.prevent="save">
        <div class="mb-5 flex items-center justify-between"><h2 class="text-xl font-bold dark:text-white">{{ editingId ? 'Редактирование фичи' : 'Новая фича' }}</h2><button type="button" class="flex h-9 w-9 items-center justify-center rounded-md hover:bg-gray-100 dark:hover:bg-slate-800" @click="editorOpen = false"><X class="h-5 w-5" /></button></div>
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="sm:col-span-2"><span class="field-label">Название</span><input v-model="draft.name" required class="field-input" /></label>
          <label><span class="field-label">Slug</span><input v-model="draft.slug" class="field-input" placeholder="создаётся автоматически" /></label>
          <label><span class="field-label">Категория</span><select v-model="draft.category_id" required class="field-input"><option v-for="category in categories" :key="category.id" :value="category.id">{{ category.name }}</option></select></label>
          <label><span class="field-label">Область</span><select v-model="draft.scope_type" class="field-input"><option v-for="(label, value) in scopeLabels" :key="value" :value="value">{{ label }}</option></select></label>
          <label v-if="draft.scope_type === 'brand'"><span class="field-label">Бренд</span><select v-model="draft.brand_id" required class="field-input"><option :value="null" disabled>Выберите бренд</option><option v-for="brand in brands" :key="brand.id" :value="brand.id">{{ brand.title }}</option></select></label>
          <label><span class="field-label">Порядок</span><input v-model.number="draft.sort_order" type="number" class="field-input" /></label>
          <label class="sm:col-span-2"><span class="field-label">Краткое описание</span><input v-model="draft.short_description" class="field-input" /></label>
          <label class="sm:col-span-2"><span class="field-label">Полное описание</span><textarea v-model="draft.full_description" rows="4" class="field-input h-auto py-2" /></label>
          <MediaField v-model="iconValue" label="Иконка" kind="feature" :tags="['feature', 'icon']" />
          <MediaField v-model="imageValue" label="Иллюстрация" kind="feature" :tags="['feature', 'illustration']" />
          <label><span class="field-label">Источник</span><input v-model="draft.source_url" class="field-input" placeholder="https://…" /></label>
          <label><span class="field-label">Сноска</span><input v-model="draft.footnote" class="field-input" /></label>
        </div>

        <section class="mt-7 border-t border-gray-200 pt-5 dark:border-slate-800">
          <div class="mb-3 flex items-center justify-between"><div><h3 class="font-bold dark:text-white">Derived rules</h3><p class="text-xs text-gray-500">Все активные правила должны выполняться одновременно</p></div><button type="button" class="inline-flex h-8 items-center gap-1 rounded-md border border-gray-200 px-2 text-xs font-semibold dark:border-slate-700" @click="addRule"><Plus class="h-3.5 w-3.5" />Правило</button></div>
          <div v-for="(rule, index) in draft.rules" :key="index" class="mb-2 grid gap-2 sm:grid-cols-[1fr_120px_1fr_36px]">
            <input v-model="rule.spec_key" class="field-input" placeholder="spec key" />
            <select v-model="rule.operator" class="field-input"><option v-for="operator in ['eq','neq','gt','gte','lt','lte','in','contains','exists']" :key="operator">{{ operator }}</option></select>
            <input v-model="rule.valueText" class="field-input" :disabled="rule.operator === 'exists'" :placeholder="rule.operator === 'in' ? 'wifi, quiet' : 'значение'" />
            <button type="button" class="flex h-10 items-center justify-center rounded-md text-gray-400 hover:bg-red-50 hover:text-red-600" title="Удалить правило" @click="draft.rules.splice(index, 1)"><Trash2 class="h-4 w-4" /></button>
          </div>
        </section>

        <div class="sticky bottom-0 mt-8 flex justify-end gap-2 border-t border-gray-200 bg-white py-4 dark:border-slate-800 dark:bg-slate-950"><button type="button" class="h-10 rounded-md px-4 text-sm font-semibold text-gray-600" @click="editorOpen = false">Отмена</button><button type="submit" class="h-10 rounded-md bg-teal-600 px-5 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50" :disabled="saving">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button></div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.field-label { display: block; margin-bottom: 0.35rem; font-size: 0.75rem; font-weight: 700; color: rgb(75 85 99); }
.field-input { width: 100%; min-height: 2.5rem; border: 1px solid rgb(209 213 219); border-radius: 0.375rem; background: transparent; padding: 0 0.75rem; font-size: 0.875rem; }
:global(.dark) .field-label { color: rgb(148 163 184); }
:global(.dark) .field-input { border-color: rgb(51 65 85); color: white; }
</style>
