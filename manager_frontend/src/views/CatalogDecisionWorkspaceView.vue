<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import BynSymbol from '../components/catalog-decision/BynSymbol.vue';
import CatalogDecisionFilters from '../components/catalog-decision/CatalogDecisionFilters.vue';
import CatalogDecisionCollectionDialog from '../components/catalog-decision/CatalogDecisionCollectionDialog.vue';
import CatalogDecisionOrderDialog from '../components/catalog-decision/CatalogDecisionOrderDialog.vue';
import CatalogDecisionQuickOrderDialog from '../components/catalog-decision/CatalogDecisionQuickOrderDialog.vue';
import CatalogDecisionSelectionTray from '../components/catalog-decision/CatalogDecisionSelectionTray.vue';
import CatalogDecisionTable from '../components/catalog-decision/CatalogDecisionTable.vue';
import CatalogDecisionCompareDialog from '../components/catalog-decision/CatalogDecisionCompareDialog.vue';
import CatalogDecisionProductDetailsDialog from '../components/catalog-decision/CatalogDecisionProductDetailsDialog.vue';
import { catalogDecisionChips, readCatalogDecisionQuery, writeCatalogDecisionQuery } from '../services/catalog-decision-query';
import { catalogDecisionApi, defaultCatalogDecisionFilters, type CatalogDecisionFilters as Filters, type CatalogDecisionItem, type CatalogDecisionSort } from '../services/catalog-decision-api';
import {
  catalogDecisionSelectionStorageKey,
  loadCatalogDecisionSelection,
  saveCatalogDecisionSelection,
  type CatalogDecisionSelectionItem,
} from '../services/catalog-decision-selection';
import { managerSession } from '../services/manager-session';
import { useCatalogDecisionTarget } from '../composables/useCatalogDecisionTarget';
import { navigateManager } from '../services/catalog-decision-context';
import { getApiErrorMessage } from '../utils/api-errors';

const target = useCatalogDecisionTarget();
const selectionError = ref('');
const targetProductIds = computed(() => (target.proposal.value?.product_lines ?? []).flatMap(line => typeof line.product_id === 'number' ? [line.product_id] : []));
const initializedSelectionKey = ref<string | null>(null);
let loadGeneration = 0;
let disposed = false;
const items = ref<CatalogDecisionItem[]>([]);
const brands = ref<Array<{ id: number; title: string }>>([]);
const series = ref<Array<{ id: number; title: string; brandId?: number | null }>>([]);
const initialQuery = readCatalogDecisionQuery(window.location.search);
const filters = ref<Filters>(initialQuery.filters);
const sort = ref<CatalogDecisionSort>(initialQuery.sort);
const direction = ref<'asc' | 'desc'>(initialQuery.direction);
const page = ref(initialQuery.page); const pages = ref(1); const total = ref(0); const loading = ref(false); const error = ref('');
const selected = ref<Record<number, CatalogDecisionSelectionItem>>({});
const filterResetKey = ref(0);
const filterOptionsError = ref('');
const compareOpen = ref(false);
const compareItems = ref<CatalogDecisionItem[]>([]);
const compareLoading = ref(false);
const compareError = ref('');
const detailItem = ref<CatalogDecisionItem | null>(null);
let compareGeneration = 0;
const chips = computed(() => catalogDecisionChips(filters.value, brands.value, series.value));
const collectionDialogOpen = ref(false);
const orderDialogOpen = ref(false);
const quickOrderDialogOpen = ref(false);
const success = ref<{ message: string; href: string; label: string } | null>(null);
let searchTimer: ReturnType<typeof setTimeout> | undefined;
const selectionStorageKey = computed(() => {
  const auth = managerSession.auth.value;
  if (!auth || (target.requested && !target.context.value)) return null;
  const base = catalogDecisionSelectionStorageKey(auth);
  const context = target.context.value;
  return context ? `${base}:order-${context.orderId}:proposal-${context.proposalId}` : base;
});

const syncQuery = () => {
  const query = writeCatalogDecisionQuery(window.location.search, { filters: filters.value, sort: sort.value, direction: direction.value, page: page.value });
  // Do not dispatch popstate: the Manager shell remounts on navigation.
  window.history.replaceState(window.history.state, '', `${window.location.pathname}${query}${window.location.hash}`);
};
const load = async () => {
  clearTimeout(searchTimer);
  syncQuery();
  const generation = ++loadGeneration;
  loading.value = true; error.value = '';
  try {
    const response = await catalogDecisionApi.list(page.value, 40, filters.value, sort.value, direction.value);
    if (generation !== loadGeneration) return;
    items.value = response.items ?? []; page.value = response.meta.page; pages.value = Math.max(1, response.meta.pages); total.value = response.meta.total;
    syncQuery();
  } catch (err) { if (generation === loadGeneration) error.value = getApiErrorMessage(err) || 'Не удалось загрузить рабочий каталог'; }
  finally { if (generation === loadGeneration) loading.value = false; }
};
const updateFilters = (next: Filters) => { filters.value = next; page.value = 1; };
const reset = () => { filterResetKey.value += 1; filters.value = defaultCatalogDecisionFilters(); page.value = 1; };
const changeSort = (next: CatalogDecisionSort) => { direction.value = sort.value === next && direction.value === 'asc' ? 'desc' : 'asc'; sort.value = next; page.value = 1; void load(); };
const go = (next: number) => { if (next >= 1 && next <= pages.value && !loading.value) { page.value = next; void load(); } };
const toggleSelection = (item: CatalogDecisionItem) => {
  if (target.saving.value || loading.value || error.value) return;
  selectionError.value = '';
  const next = { ...selected.value };
  if (next[item.id]) delete next[item.id];
  else {
    if (Object.keys(next).length >= 24) { selectionError.value = 'В один подбор можно добавить до 24 моделей.'; return; }
    next[item.id] = { id: item.id, title: item.title };
  }
  selected.value = next;
};
const removeSelection = (id: number) => { const next = { ...selected.value }; delete next[id]; selected.value = next; };
const openCompare = async () => {
  const ids = Object.values(selected.value).map(item => item.id);
  if (ids.length < 2 || ids.length > 4) return;
  const generation = ++compareGeneration;
  compareOpen.value = true; compareLoading.value = true; compareError.value = ''; compareItems.value = [];
  try {
    const response = await catalogDecisionApi.list(1, 24, { isPublished: true, includeOrderable: true, productIds: ids }, 'title', 'asc');
    if (disposed || generation !== compareGeneration) return;
    compareItems.value = ids.flatMap(id => (response.items ?? []).filter(item => item.id === id));
    if (compareItems.value.length !== ids.length) compareError.value = 'Часть выбранных моделей больше недоступна. Закройте сравнение и проверьте подбор.';
  } catch (err) { if (!disposed && generation === compareGeneration) compareError.value = getApiErrorMessage(err) || 'Не удалось загрузить сравнение. Закройте его и попробуйте ещё раз.'; }
  finally { if (!disposed && generation === compareGeneration) compareLoading.value = false; }
};
const closeCompare = () => { compareOpen.value = false; compareGeneration += 1; };
const loadFilterOptions = async () => {
  filterOptionsError.value = '';
  try {
    const options = await catalogDecisionApi.filterOptions();
    if (disposed) return;
    brands.value = options.brands ?? [];
    series.value = (options.series ?? []).map(item => ({ id: item.id, title: item.title, brandId: item.brand_id }));
  } catch { if (!disposed) filterOptionsError.value = 'Не удалось загрузить бренды и серии.'; }
};
const collectionCreated = (collectionId: number) => {
  collectionDialogOpen.value = false;
  success.value = { message: 'Подборка создана. Выбранные модели остались в корзине.', href: `/manager/product-collections?collectionId=${collectionId}`, label: 'Открыть подборки' };
};
const orderAttached = (orderId: number) => {
  orderDialogOpen.value = false;
  success.value = { message: `Модели прикреплены к заказу #${orderId}. Корзина не очищена.`, href: `/manager/orders/kanban?orderId=${orderId}`, label: 'Открыть заказ' };
};
const orderCreated = (orderId: number) => {
  quickOrderDialogOpen.value = false;
  success.value = { message: `Быстрый заказ #${orderId} создан. Клиента можно привязать позже.`, href: `/manager/orders/kanban?orderId=${orderId}`, label: 'Открыть заказ' };
};
const attachToTarget = async () => {
  if (await target.attach(Object.values(selected.value).map(item => item.id)) && !disposed) {
    selected.value = {};
    if (target.context.value) navigateManager(target.context.value.returnTo);
  }
};
watch(filters, (next, previous) => {
  clearTimeout(searchTimer);
  // Invalidate the old response as soon as criteria change, even during debounce.
  loadGeneration += 1;
  loading.value = true;
  if (next.search !== previous.search) searchTimer = setTimeout(() => void load(), 220);
  else void load();
}, { deep: true });
watch(selectionStorageKey, (key) => {
  initializedSelectionKey.value = null;
  closeCompare(); detailItem.value = null;
  selected.value = key ? Object.fromEntries(loadCatalogDecisionSelection(key).map(item => [item.id, item])) : {};
  initializedSelectionKey.value = key;
}, { immediate: true, flush: 'sync' });
watch(selected, (next) => {
  const key = selectionStorageKey.value;
  if (key && initializedSelectionKey.value === key) saveCatalogDecisionSelection(Object.values(next), key);
}, { deep: true, flush: 'sync' });
onMounted(() => {
  void load();
  void target.load();
  void loadFilterOptions();
});
onBeforeUnmount(() => { disposed = true; compareGeneration += 1; clearTimeout(searchTimer); loadGeneration += 1; });
</script>

<template>
  <section class="min-h-full bg-gray-50 p-3 pb-80 sm:pb-56 md:p-5 md:pb-52" data-testid="catalog-decision-workspace">
    <div class="mx-auto max-w-screen-2xl space-y-3">
      <header class="flex flex-wrap items-end justify-between gap-2">
        <div><h1 class="text-2xl font-bold text-gray-900">Подбор оборудования</h1><p class="mt-1 text-sm text-gray-500">Мощность, форма блока и обогрев — под задачу клиента.</p></div>
        <p class="text-sm text-gray-500" aria-live="polite">Найдено: {{ total }}</p>
      </header>
      <div v-if="target.requested" class="rounded-xl border border-brand-200 bg-brand-50 p-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p class="font-semibold text-brand-950">{{ target.context.value ? `Подбор для заказа #${target.context.value.orderId}` : 'Подбор для заказа' }}</p>
            <p v-if="target.loading.value" class="mt-1 text-sm text-brand-800">Загружаем заказ…</p>
            <p v-else-if="target.order.value && target.proposal.value" class="mt-1 text-sm text-brand-800">{{ target.order.value.title || target.order.value.customer?.name || 'Без названия' }} · {{ target.proposal.value.name }}</p>
            <p v-if="target.canAttach.value" class="mt-1 text-xs text-brand-800">Выбранные модели дополнят этот вариант предложения.</p>
          </div>
          <a v-if="target.context.value" :href="target.context.value.returnTo" class="text-sm font-semibold text-brand-800 underline underline-offset-2" @click.prevent="!target.saving.value && navigateManager(target.context.value!.returnTo)">Вернуться в заказ</a>
        </div>
        <p v-if="target.error.value" role="alert" class="mt-2 text-sm text-red-700">{{ target.error.value }}</p>
      </div>
      <p v-if="success" class="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800"><span>{{ success.message }}</span><a class="font-semibold underline underline-offset-2" :href="success.href">{{ success.label }}</a></p>
      <CatalogDecisionFilters :reset-key="filterResetKey" :model-value="filters" :brands="brands" :series="series" @update:model-value="updateFilters" @reset="reset" />
      <p v-if="filterOptionsError" role="alert" class="flex items-center gap-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{{ filterOptionsError }}<button type="button" class="font-semibold underline" @click="loadFilterOptions">Повторить</button></p>
      <div class="flex flex-wrap items-center gap-1.5" aria-label="Выбранные фильтры">
        <button v-for="chip in chips" :key="chip.key" type="button" class="inline-flex items-center gap-1 rounded-lg bg-brand-50 px-2 py-1 text-xs text-brand-900 hover:bg-brand-100" :aria-label="`Снять фильтр: ${chip.label}`" @click="updateFilters(chip.remove())">{{ chip.label.endsWith(' BYN') ? chip.label.slice(0, -4) : chip.label }}<template v-if="chip.label.endsWith(' BYN')"><span class="sr-only"> BYN</span><BynSymbol /></template><span aria-hidden="true">×</span></button>
        <button type="button" class="ml-1 text-xs text-gray-600 underline underline-offset-2" @click="reset">Сбросить всё</button>
      </div>
      <p v-if="error || selectionError" role="alert" class="rounded-xl bg-red-50 p-3 text-sm text-red-700">{{ error || selectionError }} <button v-if="error" type="button" class="ml-2 font-semibold underline" @click="load">Повторить</button></p>
      <div class="relative min-h-48" :aria-busy="loading">
        <p class="min-h-5 text-xs text-gray-500" role="status">{{ loading ? 'Обновляем каталог…' : error ? 'Результаты не обновлены. Повторите загрузку.' : '' }}</p>
        <div :class="loading || error ? 'pointer-events-none opacity-50' : ''" :inert="loading || Boolean(error)">
          <CatalogDecisionTable :items="items" :selected-ids="Object.keys(selected).map(Number)" :sort="sort" :direction="direction" :busy="target.saving.value || loading || Boolean(error)" :existing-ids="targetProductIds" @sort="changeSort" @toggle="toggleSelection" @details="detailItem = $event" />
        </div>
        <div v-if="!loading && !error && !items.length" class="mt-2 flex flex-wrap justify-center gap-3 text-sm">
          <button v-if="!filters.includeOrderable" class="rounded-lg border border-gray-200 bg-white px-3 py-2 text-brand-700" @click="updateFilters({ ...filters, includeOrderable: true })">Показать также заказные</button>
          <button class="rounded-lg border border-gray-200 bg-white px-3 py-2 text-brand-700" @click="reset">Сбросить фильтры</button>
        </div>
      </div>
      <div class="flex items-center justify-between text-sm"><button class="rounded-lg border border-gray-200 px-3 py-2 disabled:opacity-40" :disabled="page <= 1 || loading" @click="go(page - 1)">Назад</button><span>Страница {{ page }} из {{ pages }}</span><button class="rounded-lg border border-gray-200 px-3 py-2 disabled:opacity-40" :disabled="page >= pages || loading" @click="go(page + 1)">Далее</button></div>
      <CatalogDecisionSelectionTray :items="Object.values(selected)" :target-order-id="target.context.value?.orderId" :targeted="target.requested" :busy="target.saving.value" :can-attach="target.canAttach.value" @compare="openCompare" @remove="removeSelection" @clear="selected = {}; selectionError = ''" @attach-target="attachToTarget" @create-collection="collectionDialogOpen = true" @attach-order="orderDialogOpen = true" @create-order="quickOrderDialogOpen = true" />
      <CatalogDecisionCompareDialog :open="compareOpen" :items="compareItems" :loading="compareLoading" :error="compareError" @close="closeCompare" />
      <CatalogDecisionProductDetailsDialog :open="Boolean(detailItem)" :item="detailItem" @close="detailItem = null" />
      <CatalogDecisionCollectionDialog :open="collectionDialogOpen" :items="Object.values(selected)" @close="collectionDialogOpen = false" @created="collectionCreated" />
      <CatalogDecisionOrderDialog :open="orderDialogOpen" :items="Object.values(selected)" @close="orderDialogOpen = false" @attached="orderAttached" />
      <CatalogDecisionQuickOrderDialog :open="quickOrderDialogOpen" :items="Object.values(selected)" @close="quickOrderDialogOpen = false" @created="orderCreated" />
    </div>
  </section>
</template>
