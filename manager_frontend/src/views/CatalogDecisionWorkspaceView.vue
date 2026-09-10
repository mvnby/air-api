<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import CatalogDecisionFilters from '../components/catalog-decision/CatalogDecisionFilters.vue';
import CatalogDecisionCollectionDialog from '../components/catalog-decision/CatalogDecisionCollectionDialog.vue';
import CatalogDecisionOrderDialog from '../components/catalog-decision/CatalogDecisionOrderDialog.vue';
import CatalogDecisionQuickOrderDialog from '../components/catalog-decision/CatalogDecisionQuickOrderDialog.vue';
import CatalogDecisionSelectionTray from '../components/catalog-decision/CatalogDecisionSelectionTray.vue';
import CatalogDecisionTable from '../components/catalog-decision/CatalogDecisionTable.vue';
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
const filters = ref<Filters>(defaultCatalogDecisionFilters());
const sort = ref<CatalogDecisionSort>('title');
const direction = ref<'asc' | 'desc'>('asc');
const page = ref(1); const pages = ref(1); const total = ref(0); const loading = ref(false); const error = ref('');
const selected = ref<Record<number, CatalogDecisionSelectionItem>>({});
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

const load = async () => {
  const generation = ++loadGeneration;
  loading.value = true; error.value = '';
  try {
    const response = await catalogDecisionApi.list(page.value, 40, filters.value, sort.value, direction.value);
    if (generation !== loadGeneration) return;
    items.value = response.items ?? []; page.value = response.meta.page; pages.value = response.meta.pages; total.value = response.meta.total;
  } catch (err) { if (generation === loadGeneration) error.value = getApiErrorMessage(err) || 'Не удалось загрузить рабочий каталог'; }
  finally { if (generation === loadGeneration) loading.value = false; }
};
const updateFilters = (next: Filters) => { filters.value = next; page.value = 1; };
const reset = () => { filters.value = defaultCatalogDecisionFilters(); page.value = 1; };
const changeSort = (next: CatalogDecisionSort) => { direction.value = sort.value === next && direction.value === 'asc' ? 'desc' : 'asc'; sort.value = next; page.value = 1; void load(); };
const go = (next: number) => { if (next >= 1 && next <= pages.value && !loading.value) { page.value = next; void load(); } };
const toggleSelection = (item: CatalogDecisionItem) => {
  if (target.saving.value) return;
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
  if (next.search !== previous.search) searchTimer = setTimeout(() => void load(), 220);
  else void load();
}, { deep: true });
watch(selectionStorageKey, (key) => {
  initializedSelectionKey.value = null;
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
  void catalogDecisionApi.filterOptions().then(options => {
    brands.value = options.brands ?? [];
    series.value = (options.series ?? []).map(item => ({ id: item.id, title: item.title, brandId: item.brand_id }));
  }).catch(() => { /* The list request shows the actionable error. */ });
});
onBeforeUnmount(() => { disposed = true; clearTimeout(searchTimer); loadGeneration += 1; });
</script>

<template>
  <section class="min-h-full bg-gray-50 p-4 pb-44 md:p-6 md:pb-44" data-testid="catalog-decision-workspace">
    <div class="mx-auto max-w-7xl space-y-4">
      <header class="flex flex-wrap items-end justify-between gap-2">
        <div><h1 class="text-2xl font-bold text-gray-900">Подбор оборудования</h1><p class="mt-1 text-sm text-gray-500">Мощность, форма блока и обогрев — под задачу клиента.</p></div>
        <p class="text-sm text-gray-500" aria-live="polite">Найдено: {{ total }}</p>
      </header>
      <div v-if="target.requested" class="rounded-xl border border-teal-200 bg-teal-50 p-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p class="font-semibold text-teal-950">{{ target.context.value ? `Подбор для заказа #${target.context.value.orderId}` : 'Подбор для заказа' }}</p>
            <p v-if="target.loading.value" class="mt-1 text-sm text-teal-800">Загружаем заказ…</p>
            <p v-else-if="target.order.value && target.proposal.value" class="mt-1 text-sm text-teal-800">{{ target.order.value.title || target.order.value.customer?.name || 'Без названия' }} · {{ target.proposal.value.name }}</p>
            <p v-if="target.canAttach.value" class="mt-1 text-xs text-teal-800">Выбранные модели дополнят этот вариант предложения.</p>
          </div>
          <a v-if="target.context.value" :href="target.context.value.returnTo" class="text-sm font-semibold text-teal-800 underline underline-offset-2" @click.prevent="!target.saving.value && navigateManager(target.context.value!.returnTo)">Вернуться в заказ</a>
        </div>
        <p v-if="target.error.value" role="alert" class="mt-2 text-sm text-red-700">{{ target.error.value }}</p>
      </div>
      <p v-if="success" class="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800"><span>{{ success.message }}</span><a class="font-semibold underline underline-offset-2" :href="success.href">{{ success.label }}</a></p>
      <CatalogDecisionFilters :model-value="filters" :brands="brands" :series="series" @update:model-value="updateFilters" @reset="reset" />
      <p v-if="error || selectionError" role="alert" class="rounded-xl bg-red-50 p-3 text-sm text-red-700">{{ error || selectionError }}</p>
      <div v-if="loading" class="py-12 text-center text-gray-500">Загрузка…</div>
      <CatalogDecisionTable v-else :items="items" :selected-ids="Object.keys(selected).map(Number)" :sort="sort" :direction="direction" :busy="target.saving.value" :existing-ids="targetProductIds" @sort="changeSort" @toggle="toggleSelection" />
      <div class="flex items-center justify-between text-sm"><button class="rounded-lg border border-gray-200 px-3 py-2 disabled:opacity-40" :disabled="page <= 1 || loading" @click="go(page - 1)">Назад</button><span>Страница {{ page }} из {{ pages }}</span><button class="rounded-lg border border-gray-200 px-3 py-2 disabled:opacity-40" :disabled="page >= pages || loading" @click="go(page + 1)">Далее</button></div>
      <CatalogDecisionSelectionTray :items="Object.values(selected)" :target-order-id="target.context.value?.orderId" :targeted="target.requested" :busy="target.saving.value" :can-attach="target.canAttach.value" @remove="removeSelection" @clear="selected = {}; selectionError = ''" @attach-target="attachToTarget" @create-collection="collectionDialogOpen = true" @attach-order="orderDialogOpen = true" @create-order="quickOrderDialogOpen = true" />
      <CatalogDecisionCollectionDialog :open="collectionDialogOpen" :items="Object.values(selected)" @close="collectionDialogOpen = false" @created="collectionCreated" />
      <CatalogDecisionOrderDialog :open="orderDialogOpen" :items="Object.values(selected)" @close="orderDialogOpen = false" @attached="orderAttached" />
      <CatalogDecisionQuickOrderDialog :open="quickOrderDialogOpen" :items="Object.values(selected)" @close="quickOrderDialogOpen = false" @created="orderCreated" />
    </div>
  </section>
</template>
