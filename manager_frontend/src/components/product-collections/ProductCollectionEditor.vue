<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import {
  Archive, ArrowDown, ArrowUp, Copy, Plus, RefreshCw, Save, Search, Trash2,
} from 'lucide-vue-next';
import type {
  ManagerProductCollectionItemResponse,
  ManagerProductCollectionPlacementPayload,
  ManagerProductCollectionProductOptionResponse,
  ManagerProductCollectionResponse,
  ProductCollectionPreviewResponse,
  ProductCollectionRuleOptionsResponse,
} from '../../client';
import ProductCollectionPlacementsEditor from './ProductCollectionPlacementsEditor.vue';
import ProductCollectionPreview from './ProductCollectionPreview.vue';
import ProductCollectionRulesEditor from './ProductCollectionRulesEditor.vue';
import { kindLabel, type CollectionForm } from './product-collection-workspace';

const props = defineProps<{
  active: ManagerProductCollectionResponse | null;
  form: CollectionForm;
  items: ManagerProductCollectionItemResponse[];
  placements: ManagerProductCollectionPlacementPayload[];
  collections: ManagerProductCollectionResponse[];
  ruleOptions: ProductCollectionRuleOptionsResponse;
  preview: ProductCollectionPreviewResponse | null;
  previewSaved: boolean;
  initialTab?: 'products' | 'details' | 'placements';
  canManagePlatform: boolean;
  saving?: boolean;
  searching?: boolean;
  previewing?: boolean;
  searchResults: ManagerProductCollectionProductOptionResponse[];
}>();

const emit = defineEmits<{
  save: [];
  duplicate: [];
  archive: [];
  preview: [surfaceKey: string, slotKey: string];
  search: [query: string];
  'update:items': [items: ManagerProductCollectionItemResponse[]];
  'update:placements': [placements: ManagerProductCollectionPlacementPayload[]];
}>();

const tab = ref<'products' | 'details' | 'placements'>(props.initialTab || 'products');
const productPanel = ref<'composition' | 'preview'>('composition');
const searchQuery = ref('');
const replacementIndex = ref<number | null>(null);
const selectedProductIds = computed(() => new Set(props.items.map(item => item.product_id)));
const fallbacks = computed(() => props.collections.filter(
  row => row.id !== props.active?.id && row.status !== 'archived',
));
const replacementItem = computed(() => (
  replacementIndex.value === null ? null : props.items[replacementIndex.value] || null
));

const updateItems = (items: ManagerProductCollectionItemResponse[]) => {
  emit('update:items', items.map((item, position) => ({ ...item, position })));
};
const moveItem = (index: number, delta: number) => {
  const rows = [...props.items];
  const target = index + delta;
  if (!rows[target]) return;
  [rows[index], rows[target]] = [rows[target]!, rows[index]!];
  updateItems(rows);
};
const removeItem = (productId: number) => {
  if (replacementItem.value?.product_id === productId) replacementIndex.value = null;
  updateItems(props.items.filter(item => item.product_id !== productId));
};
const productFields = (product: ManagerProductCollectionProductOptionResponse) => ({
  product_id: product.id,
  product_title: product.title,
  product_slug: product.slug || '',
  product_kind: product.product_kind,
  is_published: product.is_published,
  price: product.price,
  main_image: product.main_image,
});
const chooseProduct = (product: ManagerProductCollectionProductOptionResponse) => {
  if (selectedProductIds.value.has(product.id)) return;
  if (replacementIndex.value !== null) {
    const rows = [...props.items];
    const original = rows[replacementIndex.value];
    if (!original) return;
    rows[replacementIndex.value] = { ...original, ...productFields(product) };
    replacementIndex.value = null;
    updateItems(rows);
    return;
  }
  updateItems([
    ...props.items,
    {
      id: -Date.now(),
      position: props.items.length,
      is_pinned: true,
      editorial_note: null,
      ...productFields(product),
    },
  ]);
};
const beginReplace = (index: number) => {
  replacementIndex.value = index;
  searchQuery.value = '';
};
const submitSearch = () => emit('search', searchQuery.value);
const loadPreview = (surfaceKey: string, slotKey: string) => emit('preview', surfaceKey, slotKey);
const openPreview = () => {
  productPanel.value = 'preview';
  const placement = props.active?.placements?.[0];
  if (props.previewSaved && placement) loadPreview(placement.surface_key, placement.slot_key);
};

watch(() => props.active?.id, () => {
  replacementIndex.value = null;
  productPanel.value = 'composition';
});
</script>

<template>
  <section class="min-w-0" data-testid="product-collection-editor">
    <header class="sticky top-0 z-10 -mx-4 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95 sm:static sm:mx-0 sm:rounded-xl sm:border sm:px-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-xs font-bold uppercase tracking-wider text-blue-600">{{ active ? 'Подборка' : 'Новая подборка' }}</p>
          <h1 class="break-words text-xl font-bold text-slate-950 dark:text-white">{{ form.internal_name || 'Без названия' }}</h1>
          <p class="break-all text-xs text-slate-500">{{ active ? `/${form.slug}` : 'Сохранится как черновик до публикации' }}</p>
        </div>
        <div class="flex flex-wrap items-center justify-end gap-1">
          <button v-if="active" class="tool-button" type="button" title="Дублировать" :disabled="saving" @click="emit('duplicate')"><Copy class="h-4 w-4" /></button>
          <button v-if="active && active.status !== 'archived'" class="tool-button" type="button" title="Архивировать" :disabled="saving" @click="emit('archive')"><Archive class="h-4 w-4" /></button>
          <button class="save-button" type="button" :disabled="saving" @click="emit('save')"><Save class="h-4 w-4" />{{ saving ? 'Сохранение…' : form.status === 'published' ? 'Применить' : 'Сохранить' }}</button>
        </div>
      </div>
      <nav class="mt-3 grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800" aria-label="Разделы подборки">
        <button
          v-for="entry in [['products', 'Товары'], ['details', 'Описание'], ['placements', 'Размещения']] as const"
          :key="entry[0]"
          class="tab-button"
          :class="tab === entry[0] ? 'tab-button--active' : ''"
          type="button"
          @click="tab = entry[0]"
        >
          {{ entry[1] }}<span v-if="entry[0] === 'products'" class="ml-1 text-xs">{{ items.length }}</span><span v-if="entry[0] === 'placements'" class="ml-1 text-xs">{{ placements.length }}</span>
        </button>
      </nav>
    </header>

    <fieldset class="contents" :disabled="saving">
    <div v-show="tab === 'products'" class="space-y-4 py-5">
      <div class="grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800" aria-label="Товары или предпросмотр">
        <button class="panel-button" :class="productPanel === 'composition' ? 'panel-button--active' : ''" type="button" @click="productPanel = 'composition'">Состав</button>
        <button class="panel-button" :class="productPanel === 'preview' ? 'panel-button--active' : ''" type="button" @click="openPreview">Предпросмотр</button>
      </div>

      <template v-if="productPanel === 'composition'">
        <ProductCollectionRulesEditor :form="form" :rule-options="ruleOptions" :can-manage-platform="canManagePlatform" />

        <section v-if="form.mode !== 'automatic'" class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <div>
            <h2 class="font-bold">Товары в подборке</h2>
            <p class="mt-1 text-xs text-slate-500">Порядок сверху вниз станет порядком карточек. В гибридном режиме закреплённые идут первыми.</p>
          </div>

          <div v-if="replacementItem" class="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-950" data-testid="replacement-notice">
            <span class="min-w-0">Заменяем: <strong class="break-words">{{ replacementItem.product_title }}</strong>. Позиция, закрепление и заметка сохранятся.</span>
            <button class="text-xs font-bold text-blue-700" type="button" @click="replacementIndex = null">Отменить</button>
          </div>

          <form class="mt-4 grid min-w-0 gap-2 sm:grid-cols-[minmax(0,1fr)_auto]" @submit.prevent="submitSearch">
            <input v-model="searchQuery" class="field-input mt-0 min-w-0" :placeholder="replacementItem ? 'Найдите товар для замены' : 'Модель, бренд или серия'" />
            <button class="secondary-button" type="submit"><Search class="h-4 w-4" />{{ searching ? 'Поиск…' : replacementItem ? 'Найти замену' : 'Найти' }}</button>
          </form>

          <div v-if="searchResults.length" class="mt-3 divide-y rounded-lg border border-slate-200 dark:border-slate-700">
            <button
              v-for="product in searchResults"
              :key="product.id"
              class="flex w-full items-center justify-between gap-3 p-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800"
              type="button"
              data-testid="search-product"
              @click="chooseProduct(product)"
            >
              <span class="min-w-0"><strong class="block break-words text-sm">{{ product.title }}</strong><span class="text-xs text-slate-500">{{ kindLabel(product.product_kind) }} · {{ product.price }} BYN</span></span>
              <RefreshCw v-if="replacementItem" class="h-4 w-4 shrink-0" /><Plus v-else class="h-4 w-4 shrink-0" />
            </button>
          </div>

          <div class="mt-3 divide-y rounded-lg border border-slate-200 dark:border-slate-700">
            <div v-for="(item, index) in items" :key="item.product_id" class="flex min-w-0 gap-3 p-3">
              <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-slate-100 text-xs font-bold text-slate-500 dark:bg-slate-800">{{ index + 1 }}</span>
              <div class="min-w-0 flex-1">
                <strong class="block break-words text-sm">{{ item.product_title }}</strong>
                <p class="mt-1 break-words text-xs text-slate-500">{{ kindLabel(item.product_kind) }} · {{ item.price }} BYN · <span :class="item.is_published ? 'text-emerald-700' : 'text-red-700'">{{ item.is_published ? 'Опубликован' : 'Скрыт' }}</span></p>
                <label class="mt-2 block text-xs">Редакторская заметка<input v-model="item.editorial_note" class="field-input" placeholder="Необязательно" @input="updateItems(items)" /></label>
                <label v-if="form.mode === 'hybrid'" class="mt-2 inline-flex items-center gap-2 text-xs"><input v-model="item.is_pinned" type="checkbox" @change="updateItems(items)" /> Закреплён</label>
                <button class="mt-2 inline-flex items-center gap-1 text-xs font-bold text-blue-700" type="button" @click="beginReplace(index)"><RefreshCw class="h-3.5 w-3.5" /> Заменить товар</button>
              </div>
              <div class="flex shrink-0 flex-col gap-1">
                <button class="tool-button" :disabled="index === 0" type="button" title="Выше" @click="moveItem(index, -1)"><ArrowUp class="h-4 w-4" /></button>
                <button class="tool-button" :disabled="index === items.length - 1" type="button" title="Ниже" @click="moveItem(index, 1)"><ArrowDown class="h-4 w-4" /></button>
                <button class="tool-button text-red-600" type="button" title="Убрать" @click="removeItem(item.product_id)"><Trash2 class="h-4 w-4" /></button>
              </div>
            </div>
            <p v-if="!items.length" class="p-7 text-center text-sm text-slate-500">Добавьте товары через поиск.</p>
          </div>
        </section>
        <p v-else class="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">Состав формируется только правилами, заданными выше.</p>
      </template>

      <ProductCollectionPreview
        v-else-if="active"
        :active="active"
        :preview="preview"
        :preview-saved="previewSaved"
        :loading="previewing"
        @load="loadPreview"
      />
      <p v-else class="rounded-xl border border-dashed border-slate-300 p-7 text-center text-sm text-slate-500">Сначала сохраните новую подборку, затем откройте предпросмотр.</p>
    </div>

    <div v-show="tab === 'details'" class="space-y-5 py-5">
      <section class="editor-card">
        <h2 class="section-title">Описание и публикация</h2>
        <div class="grid gap-4 md:grid-cols-2">
          <label>Служебное название<input v-model="form.internal_name" class="field-input" required /></label>
          <label>Публичный заголовок<input v-model="form.public_title" class="field-input" required /></label>
          <label class="md:col-span-2">Описание на сайте<textarea v-model="form.public_description" class="field-input min-h-24" /></label>
          <label>Плашка<input v-model="form.public_badge" class="field-input" placeholder="Например: Выбор мастера" /></label>
          <label>Статус<select v-model="form.status" class="field-input"><option value="draft">Черновик</option><option value="published">Опубликована</option><option value="archived">Архив</option></select></label>
          <label>Начало публикации<input v-model="form.starts_at" class="field-input" type="datetime-local" /></label>
          <label>Окончание публикации<input v-model="form.ends_at" class="field-input" type="datetime-local" /></label>
          <label>Минимум товаров<input v-model.number="form.min_items" class="field-input" min="1" max="24" type="number" /></label>
          <label>Максимум товаров<input v-model.number="form.max_items" class="field-input" min="1" max="24" type="number" /></label>
          <label class="md:col-span-2">Резервная подборка<select v-model="form.fallback_collection_id" class="field-input"><option :value="null">Без резерва</option><option v-for="row in fallbacks" :key="row.id" :value="row.id">{{ row.internal_name }}</option></select></label>
        </div>
      </section>
    </div>

    <div v-show="tab === 'placements'" class="py-5">
      <ProductCollectionPlacementsEditor :model-value="placements" :disabled="saving" @update:model-value="emit('update:placements', $event)" />
    </div>
    </fieldset>
  </section>
</template>

<style scoped>
.field-input { display:block; width:100%; min-height:38px; margin-top:5px; border:1px solid rgb(203 213 225); border-radius:8px; background:transparent; padding:7px 10px; font-size:14px; }
.editor-card { border:1px solid rgb(226 232 240); border-radius:12px; background:white; padding:16px; }
.section-title { margin-bottom:16px; font-size:16px; font-weight:700; }
.tool-button { display:inline-flex; height:36px; width:36px; align-items:center; justify-content:center; border-radius:8px; }
.tool-button:hover { background:rgb(241 245 249); }
.tool-button:disabled { opacity:.35; }
.save-button,.secondary-button { display:inline-flex; min-height:38px; align-items:center; justify-content:center; gap:6px; border-radius:8px; padding:0 12px; font-size:13px; font-weight:700; }
.save-button { background:rgb(37 99 235); color:white; }
.save-button:disabled { opacity:.55; }
.secondary-button { border:1px solid rgb(203 213 225); }
.tab-button,.panel-button { min-width:0; min-height:34px; border-radius:6px; padding:0 4px; font-size:13px; font-weight:700; color:rgb(71 85 105); overflow-wrap:anywhere; }
.tab-button--active,.panel-button--active { background:white; color:rgb(30 64 175); box-shadow:0 1px 2px rgb(15 23 42 / .12); }
label { font-size:12px; font-weight:650; color:rgb(71 85 105); }
:global(.dark) .editor-card { background:rgb(15 23 42); border-color:rgb(51 65 85); }
:global(.dark) .field-input { border-color:rgb(71 85 105); }
:global(.dark) .tab-button--active,:global(.dark) .panel-button--active { background:rgb(30 41 59); color:rgb(191 219 254); }
</style>
