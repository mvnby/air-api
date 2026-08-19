<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  Archive,
  ArrowDown,
  ArrowUp,
  Copy,
  Eye,
  GripVertical,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
} from 'lucide-vue-next';
import {
  ManagerProductCollectionsService,
  type ManagerProductCollectionCreate,
  type ManagerProductCollectionItemResponse,
  type ManagerProductCollectionPlacementResponse,
  type ManagerProductCollectionProductOptionResponse,
  type ManagerProductCollectionResponse,
  type ProductCollectionPreviewResponse,
  type ProductCollectionRuleConfig,
  type ProductCollectionRuleOptionsResponse,
} from '../client';
import { getApiErrorMessage } from '../utils/api-errors';
import { confirmDialog } from '../services/ui-feedback';

type CollectionForm = {
  slug: string;
  internal_name: string;
  public_title: string;
  public_description: string;
  public_badge: string;
  status: 'draft' | 'published' | 'archived';
  mode: 'manual' | 'automatic' | 'hybrid';
  sort_mode: 'recommended' | 'price_asc' | 'price_desc' | 'area_asc' | 'area_desc' | 'newest';
  rule_config: ProductCollectionRuleConfig;
  min_items: number;
  max_items: number;
  fallback_collection_id: number | null;
  starts_at: string;
  ends_at: string;
};

const collections = ref<ManagerProductCollectionResponse[]>([]);
const active = ref<ManagerProductCollectionResponse | null>(null);
const items = ref<ManagerProductCollectionItemResponse[]>([]);
const placements = ref<ManagerProductCollectionPlacementResponse[]>([]);
const preview = ref<ProductCollectionPreviewResponse | null>(null);
const ruleOptions = ref<ProductCollectionRuleOptionsResponse>({});
const searchQuery = ref('');
const searchResults = ref<ManagerProductCollectionProductOptionResponse[]>([]);
const loading = ref(false);
const saving = ref(false);
const searching = ref(false);
const message = ref('');
const error = ref('');

const emptyRuleConfig = (): ProductCollectionRuleConfig => ({
  product_kinds: ['complete_split_system'],
  min_price: null,
  max_price: null,
  min_area_m2: null,
  max_area_m2: null,
  max_noise_min_db: null,
  max_heating_min_c: null,
  is_inverter: null,
  wifi_states: [],
  brand_ids: [],
  series_ids: [],
  colors: [],
  feature_ids: [],
  public_stock_states: [],
});

const emptyForm = (): CollectionForm => ({
  slug: '',
  internal_name: '',
  public_title: '',
  public_description: '',
  public_badge: '',
  status: 'draft',
  mode: 'manual',
  sort_mode: 'recommended',
  rule_config: emptyRuleConfig(),
  min_items: 1,
  max_items: 6,
  fallback_collection_id: null,
  starts_at: '',
  ends_at: '',
});
const form = ref<CollectionForm>(emptyForm());

const dateTimeLocal = (value?: string | null) => value ? String(value).slice(0, 16) : '';
const apiDate = (value: string) => value ? new Date(value).toISOString() : null;
const eligibleFallbacks = computed(() => collections.value.filter(row => row.id !== active.value?.id && row.status !== 'archived'));
const selectedProductIds = computed(() => new Set(items.value.map(item => item.product_id)));
const isNew = computed(() => !active.value?.id);
const availableSeries = computed(() => {
  const brandIds = new Set(form.value.rule_config.brand_ids || []);
  if (!brandIds.size) return ruleOptions.value.series || [];
  return (ruleOptions.value.series || []).filter(row => row.parent_id && brandIds.has(row.parent_id));
});

const statusLabel = (status?: string) => ({
  draft: 'Черновик',
  published: 'Опубликована',
  archived: 'Архив',
}[status || 'draft'] || status || 'Черновик');

const kindLabel = (kind?: string | null) => ({
  unknown: 'Тип не задан',
  complete_split_system: 'Готовая сплит-система',
  indoor_unit: 'Внутренний блок',
  outdoor_unit: 'Наружный блок',
  panel: 'Панель',
  accessory: 'Аксессуар',
  consumable: 'Расходник',
  other: 'Другое',
}[kind || 'unknown'] || kind || 'Тип не задан');

const sourceLabel = (source?: string) => ({
  manual: 'Закреплён',
  automatic: 'Подобран правилом',
  fallback: 'Из резерва',
}[source || 'manual'] || source || '');

const setColors = (event: Event) => {
  form.value.rule_config.colors = (event.target as HTMLInputElement).value
    .split(',')
    .map(value => value.trim())
    .filter(Boolean);
};

const applyCollection = (collection: ManagerProductCollectionResponse | null) => {
  active.value = collection;
  preview.value = null;
  message.value = '';
  error.value = '';
  searchResults.value = [];
  searchQuery.value = '';
  if (!collection) {
    form.value = emptyForm();
    items.value = [];
    placements.value = [{
      id: -1,
      surface_key: 'home',
      slot_key: 'featured_products',
      position: 0,
      is_enabled: true,
      starts_at: null,
      ends_at: null,
    }];
    return;
  }
  form.value = {
    slug: collection.slug,
    internal_name: collection.internal_name,
    public_title: collection.public_title,
    public_description: collection.public_description || '',
    public_badge: collection.public_badge || '',
    status: collection.status || 'draft',
    mode: collection.mode || 'manual',
    sort_mode: collection.sort_mode || 'recommended',
    rule_config: {
      ...emptyRuleConfig(),
      ...(collection.rule_config || {}),
    },
    min_items: collection.min_items || 1,
    max_items: collection.max_items || 6,
    fallback_collection_id: collection.fallback_collection_id || null,
    starts_at: dateTimeLocal(collection.starts_at),
    ends_at: dateTimeLocal(collection.ends_at),
  };
  items.value = [...(collection.items || [])].sort((a, b) => a.position - b.position);
  placements.value = [...(collection.placements || [])].sort((a, b) => a.position - b.position);
};

const loadCollections = async (keepId?: number) => {
  loading.value = true;
  error.value = '';
  try {
    const response = await ManagerProductCollectionsService.listManagerProductCollections();
    collections.value = response.items || [];
    if (keepId) {
      const selected = collections.value.find(row => row.id === keepId) || null;
      applyCollection(selected);
    }
  } catch (caught) {
    error.value = getApiErrorMessage(caught);
  } finally {
    loading.value = false;
  }
};

const loadRuleOptions = async () => {
  try {
    ruleOptions.value =
      await ManagerProductCollectionsService.getManagerProductCollectionRuleOptions();
  } catch (caught) {
    error.value = getApiErrorMessage(caught);
  }
};

const searchProducts = async () => {
  const query = searchQuery.value.trim();
  if (!query) return;
  searching.value = true;
  error.value = '';
  try {
    const response =
      await ManagerProductCollectionsService.searchManagerProductCollectionProducts(query, 30);
    searchResults.value = (response.items || []).filter(
      row => !selectedProductIds.value.has(row.id),
    );
  } catch (caught) {
    error.value = getApiErrorMessage(caught);
  } finally {
    searching.value = false;
  }
};

const addProduct = (product: ManagerProductCollectionProductOptionResponse) => {
  if (selectedProductIds.value.has(product.id)) return;
  items.value.push({
    id: -Date.now(),
    product_id: product.id,
    position: items.value.length,
    is_pinned: true,
    editorial_note: null,
    product_title: product.title,
    product_slug: product.slug || '',
    product_kind: (product.product_kind || 'unknown') as ManagerProductCollectionItemResponse['product_kind'],
    is_published: product.is_published,
    price: product.price,
    main_image: product.main_image,
  });
  searchResults.value = searchResults.value.filter(row => row.id !== product.id);
};

const moveItem = (index: number, delta: number) => {
  const target = index + delta;
  if (target < 0 || target >= items.value.length) return;
  const rows = [...items.value];
  const current = rows[index];
  const next = rows[target];
  if (!current || !next) return;
  rows[index] = next;
  rows[target] = current;
  items.value = rows.map((row, position) => ({ ...row, position }));
};

const removeItem = (productId: number) => {
  items.value = items.value
    .filter(item => item.product_id !== productId)
    .map((item, position) => ({ ...item, position }));
};

const addPlacement = () => {
  placements.value.push({
    id: -Date.now(),
    surface_key: 'home',
    slot_key: 'featured_products',
    position: placements.value.length,
    is_enabled: true,
    starts_at: null,
    ends_at: null,
  });
};

const save = async () => {
  saving.value = true;
  error.value = '';
  message.value = '';
  try {
    const payload: ManagerProductCollectionCreate = {
      slug: form.value.slug || null,
      internal_name: form.value.internal_name.trim(),
      public_title: form.value.public_title.trim(),
      public_description: form.value.public_description.trim() || null,
      public_badge: form.value.public_badge.trim() || null,
      status: form.value.status,
      mode: form.value.mode,
      sort_mode: form.value.sort_mode,
      rule_config: form.value.rule_config,
      min_items: Number(form.value.min_items),
      max_items: Number(form.value.max_items),
      fallback_collection_id: form.value.fallback_collection_id || null,
      starts_at: apiDate(form.value.starts_at),
      ends_at: apiDate(form.value.ends_at),
    };
    let saved = active.value?.id
      ? await ManagerProductCollectionsService.updateManagerProductCollection(active.value.id, payload)
      : await ManagerProductCollectionsService.createManagerProductCollection(payload);
    saved = await ManagerProductCollectionsService.replaceManagerProductCollectionItems(saved.id, {
      items: items.value.map(item => ({
        product_id: item.product_id,
        is_pinned: item.is_pinned,
        editorial_note: item.editorial_note || null,
      })),
    });
    saved = await ManagerProductCollectionsService.replaceManagerProductCollectionPlacements(saved.id, {
      placements: placements.value.map((placement, index) => ({
        surface_key: placement.surface_key,
        slot_key: placement.slot_key,
        position: index,
        is_enabled: placement.is_enabled,
        starts_at: apiDate(dateTimeLocal(placement.starts_at)),
        ends_at: apiDate(dateTimeLocal(placement.ends_at)),
      })),
    });
    await loadCollections(saved.id);
    message.value = 'Подборка сохранена.';
    await loadPreview();
  } catch (caught) {
    error.value = getApiErrorMessage(caught);
  } finally {
    saving.value = false;
  }
};

const loadPreview = async () => {
  if (!active.value?.id) return;
  error.value = '';
  try {
    const placement = placements.value[0];
    preview.value = await ManagerProductCollectionsService.previewManagerProductCollection(
      active.value.id,
      placement?.surface_key || 'home',
      placement?.slot_key || 'featured_products',
    );
  } catch (caught) {
    error.value = getApiErrorMessage(caught);
  }
};

const duplicateCollection = async () => {
  if (!active.value?.id) return;
  const copy = await ManagerProductCollectionsService.duplicateManagerProductCollection(active.value.id);
  await loadCollections(copy.id);
  message.value = 'Создан черновик-копия без активных размещений.';
};

const archiveCollection = async () => {
  if (!active.value?.id || !await confirmDialog({
    title: 'Архивировать подборку?',
    description: 'Она исчезнет из публичных размещений, но данные сохранятся.',
    confirmText: 'Архивировать',
    variant: 'danger',
  })) return;
  const archived = await ManagerProductCollectionsService.archiveManagerProductCollection(active.value.id);
  await loadCollections(archived.id);
};

onMounted(async () => {
  await Promise.all([
    loadCollections(),
    loadRuleOptions(),
  ]);
});
</script>

<template>
  <div class="mx-auto max-w-[1500px] space-y-5 px-4 pb-4 pt-16 sm:p-6">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Товарные подборки</h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">Состав и порядок витрин без изменений frontend-кода.</p>
      </div>
      <button class="inline-flex h-9 items-center gap-2 rounded-md bg-teal-600 px-3 text-sm font-semibold text-white hover:bg-teal-700" type="button" @click="applyCollection(null)">
        <Plus class="h-4 w-4" /> Новая подборка
      </button>
    </header>

    <p v-if="error" class="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{{ error }}</p>
    <p v-if="message" class="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">{{ message }}</p>

    <div class="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
      <section class="min-w-0 border-r-0 xl:border-r xl:border-gray-200 xl:pr-6 dark:xl:border-slate-800">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-sm font-bold uppercase tracking-wider text-gray-500 dark:text-slate-400">Подборки</h2>
          <button class="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-gray-100 dark:hover:bg-slate-800" type="button" title="Обновить" @click="loadCollections(active?.id)">
            <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': loading }" />
          </button>
        </div>
        <div class="divide-y divide-gray-200 border-y border-gray-200 dark:divide-slate-800 dark:border-slate-800">
          <button
            v-for="collection in collections"
            :key="collection.id"
            type="button"
            class="block w-full px-2 py-3 text-left hover:bg-gray-50 dark:hover:bg-slate-900"
            :class="active?.id === collection.id ? 'bg-teal-50 dark:bg-teal-950/20' : ''"
            @click="applyCollection(collection)"
          >
            <span class="flex items-start justify-between gap-3">
              <span class="min-w-0">
                <strong class="block truncate text-sm text-gray-900 dark:text-white">{{ collection.internal_name }}</strong>
                <span class="mt-1 block text-xs text-gray-500 dark:text-slate-400">{{ collection.items?.length || 0 }} товаров · {{ collection.placements?.length || 0 }} размещений</span>
              </span>
              <span class="shrink-0 rounded px-2 py-0.5 text-[11px] font-semibold" :class="collection.status === 'published' ? 'bg-emerald-100 text-emerald-800' : collection.status === 'archived' ? 'bg-gray-200 text-gray-700' : 'bg-amber-100 text-amber-800'">{{ statusLabel(collection.status) }}</span>
            </span>
          </button>
          <p v-if="!loading && !collections.length" class="px-2 py-8 text-center text-sm text-gray-500">Подборок пока нет.</p>
        </div>
      </section>

      <section v-if="active || isNew" class="min-w-0 space-y-7">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 pb-4 dark:border-slate-800">
          <div>
            <h2 class="text-lg font-bold text-gray-900 dark:text-white">{{ isNew ? 'Новая подборка' : form.internal_name }}</h2>
            <p class="text-xs text-gray-500">{{ isNew ? 'Сначала задайте смысл и состав.' : `/${form.slug}` }}</p>
          </div>
          <div class="flex items-center gap-2">
            <button v-if="active" class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-gray-200 dark:border-slate-700" type="button" title="Дублировать" @click="duplicateCollection"><Copy class="h-4 w-4" /></button>
            <button v-if="active && active.status !== 'archived'" class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-gray-200 text-gray-600 dark:border-slate-700" type="button" title="Архивировать" @click="archiveCollection"><Archive class="h-4 w-4" /></button>
            <button class="inline-flex h-9 items-center gap-2 rounded-md bg-teal-600 px-3 text-sm font-semibold text-white disabled:opacity-50" type="button" :disabled="saving" @click="save"><Save class="h-4 w-4" /> {{ saving ? 'Сохранение...' : 'Сохранить' }}</button>
          </div>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Служебное название</span><input v-model="form.internal_name" class="field-input" required /></label>
          <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Публичный заголовок</span><input v-model="form.public_title" class="field-input" required /></label>
          <label class="space-y-1 md:col-span-2"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Описание на сайте</span><textarea v-model="form.public_description" class="field-input min-h-20" /></label>
          <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Плашка</span><input v-model="form.public_badge" class="field-input" placeholder="Например: Выбор мастера" /></label>
          <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Статус</span><select v-model="form.status" class="field-input"><option value="draft">Черновик</option><option value="published">Опубликована</option><option value="archived">Архив</option></select></label>
          <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Формирование</span><select v-model="form.mode" class="field-input"><option value="manual">Вручную</option><option value="automatic">Автоматически</option><option value="hybrid">Закреплённые + правила</option></select></label>
          <label v-if="form.mode !== 'manual'" class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Сортировка автоподбора</span><select v-model="form.sort_mode" class="field-input"><option value="recommended">Рекомендованная</option><option value="price_asc">Сначала дешевле</option><option value="price_desc">Сначала дороже</option><option value="area_asc">Сначала меньшая площадь</option><option value="area_desc">Сначала большая площадь</option><option value="newest">Сначала новые</option></select></label>
          <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Минимум товаров</span><input v-model.number="form.min_items" class="field-input" min="1" max="24" type="number" /></label>
          <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Максимум товаров</span><input v-model.number="form.max_items" class="field-input" min="1" max="24" type="number" /></label>
          <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Начало публикации</span><input v-model="form.starts_at" class="field-input" type="datetime-local" /></label>
          <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Окончание публикации</span><input v-model="form.ends_at" class="field-input" type="datetime-local" /></label>
          <label class="space-y-1 md:col-span-2"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Резервная подборка</span><select v-model="form.fallback_collection_id" class="field-input"><option :value="null">Без резерва</option><option v-for="row in eligibleFallbacks" :key="row.id" :value="row.id">{{ row.internal_name }}</option></select></label>
        </div>

        <div v-if="form.mode !== 'manual'" class="space-y-4 border-t border-gray-200 pt-6 dark:border-slate-800">
          <div><h3 class="font-bold text-gray-900 dark:text-white">Условия автоподбора</h3><p class="text-xs text-gray-500">Все заполненные условия применяются одновременно.</p></div>
          <fieldset class="space-y-2">
            <legend class="text-xs font-semibold text-gray-600 dark:text-slate-300">Тип товара</legend>
            <div class="flex flex-wrap gap-x-4 gap-y-2">
              <label v-for="kind in [
                ['complete_split_system', 'Готовая сплит-система'],
                ['indoor_unit', 'Внутренний блок'],
                ['outdoor_unit', 'Наружный блок'],
                ['panel', 'Панель'],
                ['accessory', 'Аксессуар'],
                ['consumable', 'Расходник'],
                ['other', 'Другое'],
              ]" :key="kind[0]" class="flex items-center gap-2 text-xs">
                <input v-model="form.rule_config.product_kinds" type="checkbox" :value="kind[0]" /> {{ kind[1] }}
              </label>
            </div>
          </fieldset>
          <div class="grid gap-4 md:grid-cols-4">
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Цена от</span><input v-model.number="form.rule_config.min_price" class="field-input" min="0" type="number" /></label>
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Цена до</span><input v-model.number="form.rule_config.max_price" class="field-input" min="0" type="number" /></label>
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Площадь от, м²</span><input v-model.number="form.rule_config.min_area_m2" class="field-input" min="0" type="number" /></label>
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Площадь до, м²</span><input v-model.number="form.rule_config.max_area_m2" class="field-input" min="0" type="number" /></label>
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Шум не выше, дБ</span><input v-model.number="form.rule_config.max_noise_min_db" class="field-input" min="0" step="0.1" type="number" /></label>
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Обогрев до, °C</span><input v-model.number="form.rule_config.max_heating_min_c" class="field-input" max="30" min="-60" step="1" type="number" /></label>
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Инвертор</span><select v-model="form.rule_config.is_inverter" class="field-input"><option :value="null">Не важно</option><option :value="true">Да</option><option :value="false">Нет</option></select></label>
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Цвета</span><input :value="(form.rule_config.colors || []).join(', ')" class="field-input" placeholder="чёрный, серебристый" @input="setColors" /></label>
          </div>
          <div class="grid gap-4 md:grid-cols-3">
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Бренды</span><select v-model="form.rule_config.brand_ids" class="field-input min-h-32" multiple><option v-for="row in ruleOptions.brands || []" :key="row.id" :value="row.id">{{ row.label }}</option></select></label>
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Серии</span><select v-model="form.rule_config.series_ids" class="field-input min-h-32" multiple><option v-for="row in availableSeries" :key="row.id" :value="row.id">{{ row.label }}</option></select></label>
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Feature</span><select v-model="form.rule_config.feature_ids" class="field-input min-h-32" multiple><option v-for="row in ruleOptions.features || []" :key="row.id" :value="row.id">{{ row.label }}</option></select></label>
          </div>
          <div class="grid gap-4 md:grid-cols-2">
            <fieldset class="space-y-2"><legend class="text-xs font-semibold text-gray-600 dark:text-slate-300">Wi‑Fi</legend><div class="flex flex-wrap gap-4"><label class="flex items-center gap-2 text-xs"><input v-model="form.rule_config.wifi_states" type="checkbox" value="builtin" /> Встроенный</label><label class="flex items-center gap-2 text-xs"><input v-model="form.rule_config.wifi_states" type="checkbox" value="ready" /> Опциональный</label><label class="flex items-center gap-2 text-xs"><input v-model="form.rule_config.wifi_states" type="checkbox" value="none" /> Нет</label></div></fieldset>
            <fieldset class="space-y-2"><legend class="text-xs font-semibold text-gray-600 dark:text-slate-300">Доступность</legend><div class="flex flex-wrap gap-4"><label class="flex items-center gap-2 text-xs"><input v-model="form.rule_config.public_stock_states" type="checkbox" value="local_stock" /> Локально</label><label class="flex items-center gap-2 text-xs"><input v-model="form.rule_config.public_stock_states" type="checkbox" value="supplier_stock" /> У поставщика</label><label class="flex items-center gap-2 text-xs"><input v-model="form.rule_config.public_stock_states" type="checkbox" value="available_to_order" /> Под заказ</label><label class="flex items-center gap-2 text-xs"><input v-model="form.rule_config.public_stock_states" type="checkbox" value="out_of_stock" /> Нет в наличии</label></div></fieldset>
          </div>
        </div>

        <div v-if="form.mode !== 'automatic'" class="space-y-3 border-t border-gray-200 pt-6 dark:border-slate-800">
          <div class="flex flex-wrap items-end justify-between gap-3">
            <div><h3 class="font-bold text-gray-900 dark:text-white">Товары</h3><p class="text-xs text-gray-500">Порядок сверху вниз станет порядком карточек.</p></div>
            <form class="flex min-w-[280px] flex-1 gap-2 sm:max-w-lg" @submit.prevent="searchProducts">
              <div class="relative flex-1"><Search class="absolute left-3 top-2.5 h-4 w-4 text-gray-400" /><input v-model="searchQuery" class="field-input pl-9" placeholder="Модель, бренд или серия" /></div>
              <button class="inline-flex h-9 items-center rounded-md border border-gray-200 px-3 text-sm font-semibold dark:border-slate-700" type="submit">{{ searching ? 'Поиск...' : 'Найти' }}</button>
            </form>
          </div>
          <div v-if="searchResults.length" class="divide-y divide-gray-200 border-y border-gray-200 dark:divide-slate-800 dark:border-slate-800">
            <button v-for="product in searchResults" :key="product.id" class="flex w-full items-center justify-between gap-3 px-2 py-2 text-left hover:bg-gray-50 dark:hover:bg-slate-900" type="button" @click="addProduct(product)">
              <span class="min-w-0"><strong class="block truncate text-sm">{{ product.title }}</strong><span class="text-xs text-gray-500">{{ kindLabel(product.product_kind) }} · {{ product.price }} BYN</span></span><Plus class="h-4 w-4 shrink-0" />
            </button>
          </div>
          <div class="divide-y divide-gray-200 border-y border-gray-200 dark:divide-slate-800 dark:border-slate-800">
            <div v-for="(item, index) in items" :key="item.product_id" class="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 py-3">
              <GripVertical class="h-4 w-4 text-gray-400" />
              <div class="min-w-0">
                <strong class="block truncate text-sm">{{ item.product_title }}</strong>
                <div class="mt-1 flex flex-wrap gap-2 text-[11px]"><span>{{ kindLabel(item.product_kind) }}</span><span>{{ item.price }} BYN</span><span :class="item.is_published ? 'text-emerald-700' : 'text-red-700'">{{ item.is_published ? 'Опубликован' : 'Скрыт' }}</span></div>
              </div>
              <div class="flex items-center gap-1">
                <label v-if="form.mode === 'hybrid'" class="mr-2 flex items-center gap-1 text-xs"><input v-model="item.is_pinned" type="checkbox" /> Закреплён</label>
                <button class="icon-button" type="button" title="Выше" :disabled="index === 0" @click="moveItem(index, -1)"><ArrowUp class="h-4 w-4" /></button>
                <button class="icon-button" type="button" title="Ниже" :disabled="index === items.length - 1" @click="moveItem(index, 1)"><ArrowDown class="h-4 w-4" /></button>
                <button class="icon-button text-red-600" type="button" title="Убрать" @click="removeItem(item.product_id)"><Trash2 class="h-4 w-4" /></button>
              </div>
            </div>
            <p v-if="!items.length" class="py-8 text-center text-sm text-gray-500">Добавьте товары через поиск.</p>
          </div>
        </div>

        <div class="space-y-3 border-t border-gray-200 pt-6 dark:border-slate-800">
          <div class="flex items-center justify-between"><div><h3 class="font-bold">Размещения</h3><p class="text-xs text-gray-500">Для главной используйте home / featured_products.</p></div><button class="inline-flex h-8 items-center gap-1 rounded-md border border-gray-200 px-2 text-xs font-semibold dark:border-slate-700" type="button" @click="addPlacement"><Plus class="h-3.5 w-3.5" /> Размещение</button></div>
          <div v-for="(placement, index) in placements" :key="placement.id" class="grid gap-3 border-y border-gray-200 py-3 md:grid-cols-2 dark:border-slate-800">
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Поверхность</span><input v-model="placement.surface_key" class="field-input" placeholder="home" /></label>
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Слот</span><input v-model="placement.slot_key" class="field-input" placeholder="featured_products" /></label>
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Начало размещения</span><input :value="dateTimeLocal(placement.starts_at)" class="field-input" type="datetime-local" @input="placement.starts_at = ($event.target as HTMLInputElement).value || null" /></label>
            <label class="space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Окончание размещения</span><input :value="dateTimeLocal(placement.ends_at)" class="field-input" type="datetime-local" @input="placement.ends_at = ($event.target as HTMLInputElement).value || null" /></label>
            <div class="flex items-center gap-3 md:col-span-2">
              <label class="w-24 space-y-1"><span class="text-xs font-semibold text-gray-600 dark:text-slate-300">Позиция</span><input v-model.number="placement.position" class="field-input" min="0" type="number" /></label>
              <label class="mt-5 flex items-center gap-2 text-xs"><input v-model="placement.is_enabled" type="checkbox" /> Включено</label>
              <button class="icon-button ml-auto mt-5 text-red-600" type="button" title="Удалить размещение" @click="placements.splice(index, 1)"><X class="h-4 w-4" /></button>
            </div>
          </div>
        </div>

        <div v-if="active" class="space-y-3 border-t border-gray-200 pt-6 dark:border-slate-800">
          <div class="flex items-center justify-between"><div><h3 class="font-bold">Preview</h3><p class="text-xs text-gray-500">Точный результат общего resolver для выбранного placement.</p></div><button class="inline-flex h-9 items-center gap-2 rounded-md border border-gray-200 px-3 text-sm font-semibold dark:border-slate-700" type="button" @click="loadPreview"><Eye class="h-4 w-4" /> Проверить</button></div>
          <p v-if="preview?.below_min_items" class="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">Итог меньше min_items. Без рабочего fallback подборка не выйдет в публичный API.</p>
          <div v-if="(preview?.items || []).length" class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div v-for="item in (preview?.items || [])" :key="item.product.id" class="border border-gray-200 p-3 dark:border-slate-800">
              <img v-if="item.product.card_image || item.product.main_image" :src="item.product.card_image || item.product.main_image || ''" class="mb-2 aspect-[4/3] w-full object-contain" alt="" />
              <strong class="block text-sm">{{ item.product.title }}</strong>
              <span class="text-xs text-gray-500">{{ sourceLabel(item.selection_source) }} · {{ item.product.price }} BYN</span>
            </div>
          </div>
          <div v-if="(preview?.excluded_items || []).length" class="divide-y divide-red-100 border-y border-red-200 dark:divide-red-950 dark:border-red-900">
            <div v-for="item in (preview?.excluded_items || [])" :key="`${item.product_id}-${item.position}`" class="py-3">
              <strong class="text-sm text-red-800 dark:text-red-300">{{ item.product_title }}</strong>
              <p class="text-xs text-red-700 dark:text-red-400">{{ item.reasons.join(' ') }}</p>
            </div>
          </div>
        </div>
      </section>
      <section v-else class="flex min-h-72 items-center justify-center text-sm text-gray-500">Выберите подборку или создайте новую.</section>
    </div>
  </div>
</template>

<style scoped>
.field-input {
  width: 100%;
  min-height: 36px;
  border: 1px solid rgb(229 231 235);
  border-radius: 6px;
  background: transparent;
  padding: 7px 10px;
  font-size: 14px;
}
.icon-button {
  display: inline-flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
}
.icon-button:hover { background: rgb(243 244 246); }
.icon-button:disabled { opacity: 0.3; }
:global(.dark) .field-input { border-color: rgb(51 65 85); }
:global(.dark) .icon-button:hover { background: rgb(30 41 59); }
</style>
