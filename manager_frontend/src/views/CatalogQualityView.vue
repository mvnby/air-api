<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { watchDebounced } from '@vueuse/core';
import {
  Grid2X2,
  List,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
} from 'lucide-vue-next';
import { api, type CatalogQualityReportParams, type ManagerCatalogQualityReportResponse } from '../api';
import CatalogQualityCards from '../components/catalog-quality/CatalogQualityCards.vue';
import CatalogQualityFilters from '../components/catalog-quality/CatalogQualityFilters.vue';
import CatalogQualitySummary from '../components/catalog-quality/CatalogQualitySummary.vue';
import CatalogQualityTable from '../components/catalog-quality/CatalogQualityTable.vue';
import {
  applyCatalogQualityView,
  catalogQualityBuiltinViews,
  createDefaultCatalogQualityState,
  parseCatalogQualityState,
  readCatalogQualitySavedViews,
  serializeCatalogQualityState,
  writeCatalogQualitySavedViews,
  type CatalogQualityFilterState,
  type CatalogQualitySavedView,
} from '../components/catalog-quality/catalog-quality-state';
import { getApiErrorMessage } from '../utils/api-errors';

type QualityProduct = ManagerCatalogQualityReportResponse['items'][number];

const SCROLL_STORAGE_KEY = 'manager:catalog-quality:return-scroll:v1';
const report = ref<ManagerCatalogQualityReportResponse | null>(null);
const state = ref<CatalogQualityFilterState>(parseCatalogQualityState(window.location.search));
const loading = ref(false);
const error = ref('');
const requestId = ref(0);
const customViews = ref<CatalogQualitySavedView[]>(readCatalogQualitySavedViews(window.localStorage));

const savedViews = computed(() => [...catalogQualityBuiltinViews, ...customViews.value]);
const meta = computed(() => report.value?.meta);
const totalPages = computed(() => meta.value?.pages ?? 1);
const currentRelativeUrl = () => `${window.location.pathname}${window.location.search}`;
const generatedAt = computed(() => report.value?.generated_at
  ? new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(report.value.generated_at))
  : '');
const productCountLabel = (value?: number | null) => {
  const count = Number(value || 0);
  const lastTwo = count % 100;
  const last = count % 10;
  const noun = last === 1 && lastTwo !== 11
    ? 'товар'
    : last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14) ? 'товара' : 'товаров';
  return `${new Intl.NumberFormat('ru-RU').format(count)} ${noun}`;
};

const toNumber = (value: string) => value ? Number(value) : null;
const requestParams = (): CatalogQualityReportParams => ({
  page: state.value.page,
  limit: state.value.limit,
  q: state.value.q.trim() || null,
  category: state.value.category === 'all' ? null : state.value.category,
  severity: state.value.severity === 'all' ? null : state.value.severity,
  issueCode: state.value.issueCode || null,
  onlyProblems: state.value.onlyProblems,
  equipmentType: state.value.equipmentType || null,
  equipmentSubtype: state.value.equipmentSubtype || null,
  brandId: toNumber(state.value.brandId),
  seriesId: toNumber(state.value.seriesId),
  seriesState: state.value.seriesState || null,
  supplierId: toNumber(state.value.supplierId),
  supplierState: state.value.supplierState || null,
  publication: state.value.publication || null,
  availability: state.value.availability || null,
  priority: state.value.priority || null,
  scoreMin: toNumber(state.value.scoreMin),
  scoreMax: toNumber(state.value.scoreMax),
  onlyFixable: state.value.onlyFixable,
  sortBy: state.value.sortBy,
  groupBy: state.value.groupBy,
});

const syncUrl = () => {
  const nextUrl = `${window.location.pathname}${serializeCatalogQualityState(state.value)}`;
  window.history.replaceState(null, '', nextUrl);
};

const loadReport = async () => {
  const activeRequest = ++requestId.value;
  loading.value = true;
  error.value = '';
  try {
    const response = await api.getCatalogQualityReport(requestParams());
    if (activeRequest !== requestId.value) return;
    report.value = response;
    if (state.value.page > response.meta.pages && response.meta.pages > 0) {
      state.value = { ...state.value, page: response.meta.pages };
    }
  } catch (caught) {
    if (activeRequest === requestId.value) error.value = getApiErrorMessage(caught);
  } finally {
    if (activeRequest === requestId.value) loading.value = false;
  }
};

watchDebounced(
  state,
  async () => {
    syncUrl();
    await loadReport();
  },
  { deep: true, debounce: 280, maxWait: 700 },
);

const updateState = (next: CatalogQualityFilterState) => {
  state.value = next;
};

const resetFilters = () => {
  const defaults = createDefaultCatalogQualityState();
  state.value = { ...defaults, view: state.value.view, limit: state.value.limit };
};

const selectIssue = (code: string) => {
  state.value = { ...state.value, issueCode: state.value.issueCode === code ? '' : code, page: 1 };
};

const applySavedView = (view: CatalogQualitySavedView) => {
  state.value = applyCatalogQualityView(state.value, view.filters);
};

const saveCurrentView = (name: string) => {
  const filters = { ...state.value, page: 1, q: '' };
  const next = [...customViews.value, { id: `custom-${Date.now()}`, name, filters }];
  customViews.value = next;
  writeCatalogQualitySavedViews(window.localStorage, next);
};

const deleteSavedView = (id: string) => {
  const next = customViews.value.filter((view) => view.id !== id);
  customViews.value = next;
  writeCatalogQualitySavedViews(window.localStorage, next);
};

const openProduct = (product: QualityProduct) => {
  window.sessionStorage.setItem(SCROLL_STORAGE_KEY, JSON.stringify({
    url: currentRelativeUrl(),
    scrollY: window.scrollY,
  }));
  const params = new URLSearchParams({
    editProductId: String(product.product_id),
    returnTo: currentRelativeUrl(),
  });
  if (product.title) params.set('editProductQuery', product.title);
  window.location.href = `/manager/products?${params.toString()}`;
};

const goToPage = (page: number) => {
  state.value = { ...state.value, page: Math.min(Math.max(1, page), totalPages.value) };
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

const handlePopState = () => {
  state.value = parseCatalogQualityState(window.location.search);
};

const restoreScroll = async () => {
  try {
    const raw = window.sessionStorage.getItem(SCROLL_STORAGE_KEY);
    const saved = raw ? JSON.parse(raw) : null;
    if (!saved || saved.url !== currentRelativeUrl()) return;
    window.sessionStorage.removeItem(SCROLL_STORAGE_KEY);
    await nextTick();
    window.requestAnimationFrame(() => window.scrollTo({ top: Number(saved.scrollY) || 0 }));
  } catch {
    window.sessionStorage.removeItem(SCROLL_STORAGE_KEY);
  }
};

onMounted(async () => {
  window.addEventListener('popstate', handlePopState);
  await loadReport();
  await restoreScroll();
});
onBeforeUnmount(() => window.removeEventListener('popstate', handlePopState));
</script>

<template>
  <main class="min-h-screen bg-gray-50 pb-8 pt-12 text-gray-950 md:pt-4">
    <div class="mx-auto max-w-[1600px] overflow-hidden border-y border-gray-200 bg-white shadow-sm md:rounded-xl md:border">
      <header class="flex flex-col gap-3 border-b border-gray-200 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <div class="min-w-0">
          <div class="flex items-center gap-2"><ShieldCheck class="h-6 w-6 text-teal-700" /><h1 class="text-xl font-bold">Качество каталога</h1></div>
          <p class="mt-1 text-sm text-gray-500">Рабочая очередь карточек: контент, нормализация и готовность предложений.</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <span v-if="generatedAt" class="text-xs text-gray-400">Проверено {{ generatedAt }}</span>
          <button class="grid h-9 w-9 place-items-center rounded-lg border border-gray-200 text-gray-600 hover:border-teal-300 hover:text-teal-700 disabled:opacity-50" :disabled="loading" title="Обновить отчет" @click="loadReport"><RefreshCw class="h-4 w-4" :class="loading ? 'animate-spin' : ''" /></button>
          <button class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-gray-200 px-2.5 text-sm font-semibold text-gray-600 hover:bg-gray-50" title="Сбросить фильтры" @click="resetFilters"><RotateCcw class="h-4 w-4" />Сбросить</button>
        </div>
      </header>

      <CatalogQualityFilters
        :model-value="state"
        :options="report?.filter_options"
        :saved-views="savedViews"
        :loading="loading"
        @update:model-value="updateState"
        @apply-view="applySavedView"
        @save-view="saveCurrentView"
        @delete-view="deleteSavedView"
      />

      <CatalogQualitySummary v-if="report" :report="report" :selected-issue-code="state.issueCode" @select-issue="selectIssue" />

      <div v-if="error" class="border-b border-red-200 bg-red-50 px-5 py-3 text-sm font-semibold text-red-700">Не удалось загрузить отчет: {{ error }}</div>

      <section class="flex flex-col gap-3 border-b border-gray-200 bg-gray-50 px-4 py-3 lg:flex-row lg:items-center lg:justify-between sm:px-5">
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <strong>{{ productCountLabel(meta?.total) }}</strong>
          <span class="text-gray-400">·</span>
          <span class="text-gray-500">страница {{ meta?.page || 1 }} из {{ totalPages }}</span>
          <span v-if="loading" class="font-semibold text-teal-700">обновляем...</span>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <label class="flex items-center gap-2 text-xs font-semibold text-gray-500">Сортировка
            <select v-model="state.sortBy" class="h-9 rounded-lg border border-gray-200 bg-white px-2 text-sm text-gray-800">
              <option value="priority">По рабочему приоритету</option><option value="score_asc">Худший score</option><option value="critical">Критичные сначала</option><option value="stock">С наличием сначала</option><option value="newest">Новые сначала</option><option value="brand">По бренду</option><option value="series">По серии</option><option value="title">По названию</option>
            </select>
          </label>
          <label class="flex items-center gap-2 text-xs font-semibold text-gray-500">Группа
            <select v-model="state.groupBy" class="h-9 rounded-lg border border-gray-200 bg-white px-2 text-sm text-gray-800">
              <option value="none">Без группировки</option><option value="brand">Бренд</option><option value="series">Серия</option><option value="supplier">Поставщик</option><option value="equipment_type">Тип оборудования</option>
            </select>
          </label>
          <div class="inline-flex h-9 overflow-hidden rounded-lg border border-gray-200 bg-white">
            <button class="grid w-9 place-items-center" :class="state.view === 'cards' ? 'bg-teal-600 text-white' : 'text-gray-500'" title="Карточки" @click="state.view = 'cards'"><Grid2X2 class="h-4 w-4" /></button>
            <button class="grid w-9 place-items-center" :class="state.view === 'table' ? 'bg-teal-600 text-white' : 'text-gray-500'" title="Таблица" @click="state.view = 'table'"><List class="h-4 w-4" /></button>
          </div>
        </div>
      </section>

      <div v-if="loading && !report" class="grid gap-3 p-5 sm:grid-cols-2"><div v-for="index in 6" :key="index" class="h-36 animate-pulse rounded-lg bg-gray-100" /></div>
      <div v-else-if="report && !report.items.length" class="px-5 py-14 text-center"><ShieldCheck class="mx-auto h-10 w-10 text-emerald-600" /><h2 class="mt-3 text-lg font-bold">По этой выборке все чисто</h2><p class="mt-1 text-sm text-gray-500">Измените фильтры или включите карточки без проблем.</p></div>
      <template v-else-if="report">
        <CatalogQualityCards v-if="state.view === 'cards'" :items="report.items" :groups="report.groups" :grouped="state.groupBy !== 'none'" @open="openProduct" @select-issue="selectIssue" />
        <CatalogQualityTable v-else :items="report.items" @open="openProduct" @select-issue="selectIssue" />
      </template>

      <footer v-if="report" class="flex flex-col gap-3 border-t border-gray-200 bg-gray-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <label class="flex items-center gap-2 text-sm text-gray-500">На странице
          <select v-model.number="state.limit" class="h-9 rounded-lg border border-gray-200 bg-white px-2 font-semibold text-gray-800"><option :value="25">25</option><option :value="50">50</option><option :value="100">100</option></select>
        </label>
        <div class="flex items-center gap-2">
          <button class="h-9 rounded-lg border border-gray-200 bg-white px-3 text-sm font-semibold disabled:opacity-40" :disabled="state.page <= 1 || loading" @click="goToPage(state.page - 1)">Назад</button>
          <span class="min-w-20 text-center text-sm font-semibold text-gray-600">{{ state.page }} / {{ totalPages }}</span>
          <button class="h-9 rounded-lg border border-gray-200 bg-white px-3 text-sm font-semibold disabled:opacity-40" :disabled="state.page >= totalPages || loading" @click="goToPage(state.page + 1)">Дальше</button>
        </div>
      </footer>
    </div>
  </main>
</template>
