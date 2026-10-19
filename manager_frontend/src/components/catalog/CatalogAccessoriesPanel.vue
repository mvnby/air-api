<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Plus, RotateCcw, Search, Trash2 } from 'lucide-vue-next';
import { OpenAPI } from '../../client/core/OpenAPI';
import { request } from '../../client/core/request';
import type { ManagerCatalogProductListResponse } from '../../client/models/ManagerCatalogProductListResponse';
import type { ManagerCatalogProductItemResponse } from '../../client/models/ManagerCatalogProductItemResponse';
import { getApiErrorMessage } from '../../utils/api-errors';

type AccessoryItem = {
  accessory_product_id: number; title: string; slug: string; accessory_type: string | null;
  is_published: boolean; inherited: boolean; override: boolean | null; is_enabled: boolean;
};
type Workspace = { target_type: 'series' | 'product'; target_id: number; series_id: number | null; items: AccessoryItem[] };
const props = defineProps<{ targetType: 'series' | 'product'; targetId: number }>();
const workspace = ref<Workspace | null>(null);
const loading = ref(false);
const saving = ref(false);
const searching = ref(false);
const query = ref('');
const results = ref<ManagerCatalogProductItemResponse[]>([]);
const error = ref('');
const searched = ref(false);
let loadVersion = 0;
let searchVersion = 0;
const path = computed(() => `/api/manager/catalog-accessories/${props.targetType === 'series' ? 'series' : 'products'}/${props.targetId}`);
const selected = computed(() => new Set((workspace.value?.items ?? []).map(item => item.accessory_product_id)));
const availableResults = computed(() => results.value.filter(item => !selected.value.has(item.id) && !(props.targetType === 'product' && item.id === props.targetId)));

async function load() {
  const version = ++loadVersion;
  ++searchVersion;
  workspace.value = null;
  results.value = [];
  query.value = '';
  searched.value = false;
  searching.value = false;
  error.value = '';
  if (props.targetId < 1) {
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    const value = await request<Workspace>(OpenAPI, { method: 'GET', url: path.value });
    if (version === loadVersion) workspace.value = value;
  } catch (cause) {
    if (version === loadVersion) error.value = getApiErrorMessage(cause);
  } finally {
    if (version === loadVersion) loading.value = false;
  }
}

async function search() {
  if (!query.value.trim() || saving.value) return;
  const version = ++searchVersion;
  searching.value = true;
  error.value = '';
  try {
    const response = await request<ManagerCatalogProductListResponse>(OpenAPI, {
      method: 'GET', url: '/api/manager/products/list', query: { search: query.value.trim(), limit: 100, product_kind: 'accessory' },
    });
    if (version !== searchVersion) return;
    results.value = response.items.filter(item => item.product_kind === 'accessory');
    searched.value = true;
  } catch (cause) {
    if (version === searchVersion) error.value = getApiErrorMessage(cause);
  } finally {
    if (version === searchVersion) searching.value = false;
  }
}

async function save(items: AccessoryItem[]) {
  if (!workspace.value || saving.value) return;
  const version = loadVersion;
  saving.value = true;
  error.value = '';
  const body = props.targetType === 'series'
    ? { accessory_product_ids: items.map(item => item.accessory_product_id) }
    : { overrides: items.filter(item => item.override !== null).map(item => ({ accessory_product_id: item.accessory_product_id, is_enabled: item.override })) };
  try {
    const value = await request<Workspace>(OpenAPI, { method: 'PUT', url: path.value, body, mediaType: 'application/json' });
    if (version === loadVersion) workspace.value = value;
  } catch (cause) {
    if (version === loadVersion) error.value = getApiErrorMessage(cause);
  } finally {
    saving.value = false;
  }
}

function add(product: ManagerCatalogProductItemResponse) {
  const type = product.specs?.accessory_type;
  void save([...(workspace.value?.items ?? []), {
    accessory_product_id: product.id, title: product.title, slug: product.slug ?? '',
    accessory_type: typeof type === 'string' ? type : null,
    is_published: product.is_published, inherited: false,
    override: props.targetType === 'product' ? true : null, is_enabled: true,
  }]);
}

function remove(item: AccessoryItem) {
  void save((workspace.value?.items ?? []).filter(value => value.accessory_product_id !== item.accessory_product_id));
}

function toggle(item: AccessoryItem) {
  void save((workspace.value?.items ?? []).map(value => value.accessory_product_id === item.accessory_product_id
    ? { ...value, override: !item.is_enabled, is_enabled: !item.is_enabled } : value));
}

function reset(item: AccessoryItem) {
  if (!item.inherited) { remove(item); return; }
  void save((workspace.value?.items ?? []).map(value => value.accessory_product_id === item.accessory_product_id
    ? { ...value, override: null, is_enabled: true } : value));
}

watch(() => [props.targetType, props.targetId], load, { immediate: true });
</script>

<template>
  <section class="space-y-3 rounded-xl border border-gray-200 p-4 dark:border-slate-700" aria-label="Совместимые аксессуары">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h3 class="text-sm font-semibold text-gray-900 dark:text-slate-100">Совместимые аксессуары</h3>
        <p class="mt-1 text-xs text-gray-500">{{ targetType === 'series' ? 'Подходят всем моделям серии. Исключения можно задать в карточке товара.' : 'Аксессуары серии наследуются автоматически. Для этой модели можно добавить или исключить отдельные позиции.' }}</p>
      </div>
      <span v-if="saving" class="text-xs text-gray-500" role="status">Сохранение…</span>
    </div>
    <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
    <p v-if="loading" class="text-sm text-gray-500" role="status">Загрузка аксессуаров…</p>
    <template v-else-if="workspace">
      <ul class="divide-y divide-gray-100 dark:divide-slate-700">
        <li v-for="item in workspace.items" :key="item.accessory_product_id" class="flex items-center gap-3 py-2">
          <button v-if="targetType === 'product'" type="button" role="switch" :aria-checked="item.is_enabled" :aria-label="`Совместим: ${item.title}`" :disabled="saving" class="relative h-6 w-10 shrink-0 rounded-full disabled:opacity-50" :class="item.is_enabled ? 'bg-brand-600' : 'bg-gray-300 dark:bg-slate-600'" @click="toggle(item)">
            <span class="absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform" :class="item.is_enabled ? 'left-0.5 translate-x-4' : 'left-0.5'" />
          </button>
          <div class="min-w-0 flex-1" :class="!item.is_enabled ? 'opacity-60' : ''">
            <span class="block text-sm font-medium">{{ item.title }}</span>
            <span class="text-xs text-gray-500">{{ item.inherited ? 'Из серии' : targetType === 'series' ? 'Для всей серии' : 'Для этой модели' }}{{ item.override !== null ? item.is_enabled ? ' · включён для модели' : ' · исключён для модели' : '' }}{{ !item.is_published ? ' · не опубликован' : '' }}</span>
          </div>
          <button v-if="targetType === 'product' && item.inherited && item.override !== null" type="button" :disabled="saving" class="rounded p-2 text-gray-500 hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-slate-800" title="Вернуть правило серии" aria-label="Вернуть правило серии" @click="reset(item)"><RotateCcw class="h-4 w-4" /></button>
          <button v-if="!item.inherited" type="button" :disabled="saving" class="rounded p-2 text-gray-500 hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-slate-800" :aria-label="`Убрать ${item.title}`" @click="remove(item)"><Trash2 class="h-4 w-4" /></button>
        </li>
      </ul>
      <p v-if="!workspace.items.length" class="text-sm text-gray-500">Аксессуары пока не указаны.</p>
      <form class="flex gap-2" @submit.prevent="search">
        <input v-model="query" type="search" aria-label="Найти аксессуар в каталоге" placeholder="Название или модель аксессуара" class="min-w-0 flex-1 rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm dark:border-slate-700" />
        <button type="submit" :disabled="searching || saving || !query.trim()" class="rounded-lg border border-gray-200 px-3 py-2 text-gray-600 disabled:opacity-40 dark:border-slate-700 dark:text-slate-300" aria-label="Найти аксессуар"><Search class="h-4 w-4" /></button>
      </form>
      <p v-if="searching" class="text-xs text-gray-500" role="status">Поиск…</p>
      <ul v-else-if="availableResults.length" class="max-h-48 divide-y divide-gray-100 overflow-auto rounded-lg border border-gray-200 dark:divide-slate-700 dark:border-slate-700">
        <li v-for="product in availableResults" :key="product.id" class="flex items-center justify-between gap-2 px-3 py-2">
          <span class="text-sm">{{ product.title }}<span v-if="!product.is_published" class="block text-xs text-gray-500">Не опубликован</span></span>
          <button type="button" :disabled="saving || workspace.items.length >= 100" class="rounded p-2 text-brand-600 hover:bg-brand-50 disabled:opacity-40" :aria-label="`Добавить ${product.title}`" @click="add(product)"><Plus class="h-4 w-4" /></button>
        </li>
      </ul>
      <p v-else-if="searched" class="text-xs text-gray-500">Подходящие аксессуары не найдены. У товара должен быть выбран тип «Аксессуар».</p>
      <p class="text-xs text-gray-400">Аксессуары продаются отдельно. Цена и наличие берутся из их карточек.</p>
    </template>
  </section>
</template>
