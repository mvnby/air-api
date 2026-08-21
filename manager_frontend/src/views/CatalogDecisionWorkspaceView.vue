<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import CatalogDecisionFilters from '../components/catalog-decision/CatalogDecisionFilters.vue';
import CatalogDecisionCollectionDialog from '../components/catalog-decision/CatalogDecisionCollectionDialog.vue';
import CatalogDecisionOrderDialog from '../components/catalog-decision/CatalogDecisionOrderDialog.vue';
import CatalogDecisionQuickOrderDialog from '../components/catalog-decision/CatalogDecisionQuickOrderDialog.vue';
import CatalogDecisionSelectionTray from '../components/catalog-decision/CatalogDecisionSelectionTray.vue';
import CatalogDecisionTable from '../components/catalog-decision/CatalogDecisionTable.vue';
import { catalogDecisionApi, defaultCatalogDecisionFilters, type CatalogDecisionFilters as Filters, type CatalogDecisionItem, type CatalogDecisionSort } from '../services/catalog-decision-api';
import {
  loadCatalogDecisionSelection,
  saveCatalogDecisionSelection,
  type CatalogDecisionSelectionItem,
} from '../services/catalog-decision-selection';
import { getApiErrorMessage } from '../utils/api-errors';

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

const load = async () => {
  loading.value = true; error.value = '';
  try {
    const response = await catalogDecisionApi.list(page.value, 40, filters.value, sort.value, direction.value);
    items.value = response.items ?? []; page.value = response.meta.page; pages.value = response.meta.pages; total.value = response.meta.total;
  } catch (err) { error.value = getApiErrorMessage(err) || 'Не удалось загрузить рабочий каталог'; }
  finally { loading.value = false; }
};
const updateFilters = (next: Filters) => { filters.value = next; page.value = 1; };
const reset = () => { filters.value = defaultCatalogDecisionFilters(); page.value = 1; };
const changeSort = (next: CatalogDecisionSort) => { direction.value = sort.value === next && direction.value === 'asc' ? 'desc' : 'asc'; sort.value = next; page.value = 1; void load(); };
const go = (next: number) => { if (next >= 1 && next <= pages.value && !loading.value) { page.value = next; void load(); } };
const toggleSelection = (item: CatalogDecisionItem) => { const next = { ...selected.value }; if (next[item.id]) delete next[item.id]; else next[item.id] = { id: item.id, title: item.title }; selected.value = next; };
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
watch(filters, (next, previous) => { if (next.search !== previous.search) { clearTimeout(searchTimer); searchTimer = setTimeout(() => void load(), 220); } else void load(); }, { deep: true });
watch(selected, (next) => saveCatalogDecisionSelection(Object.values(next)), { deep: true });
onMounted(async () => { selected.value = Object.fromEntries(loadCatalogDecisionSelection().map(item => [item.id, item])); try { const options = await catalogDecisionApi.filterOptions(); brands.value = options.brands ?? []; series.value = (options.series ?? []).map(item => ({ id: item.id, title: item.title, brandId: item.brand_id })); } catch { /* The list request shows the actionable error. */ } void load(); });
</script>

<template>
  <section class="min-h-full bg-gray-50 p-4 pb-40 md:p-6 md:pb-40" data-testid="catalog-decision-workspace"><div class="mx-auto max-w-7xl space-y-4"><header class="flex flex-wrap items-end justify-between gap-2"><div><h1 class="text-2xl font-bold text-gray-900">Подбор оборудования</h1><p class="mt-1 text-sm text-gray-500">Быстрый рабочий каталог: выберите модели для предложения, не меняя master-каталог.</p></div><p class="text-sm text-gray-500">Найдено: {{ total }}</p></header><p v-if="success" class="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800"><span>{{ success.message }}</span><a class="font-semibold underline underline-offset-2" :href="success.href">{{ success.label }}</a></p><CatalogDecisionFilters :model-value="filters" :brands="brands" :series="series" @update:model-value="updateFilters" @reset="reset" /><p v-if="error" class="rounded-xl bg-red-50 p-3 text-sm text-red-700">{{ error }}</p><div v-if="loading" class="py-12 text-center text-gray-500">Загрузка…</div><CatalogDecisionTable v-else :items="items" :selected-ids="Object.keys(selected).map(Number)" :sort="sort" :direction="direction" @sort="changeSort" @toggle="toggleSelection" /><div class="flex items-center justify-between text-sm"><button class="rounded-lg border border-gray-200 px-3 py-2 disabled:opacity-40" :disabled="page <= 1 || loading" @click="go(page - 1)">Назад</button><span>Страница {{ page }} из {{ pages }}</span><button class="rounded-lg border border-gray-200 px-3 py-2 disabled:opacity-40" :disabled="page >= pages || loading" @click="go(page + 1)">Далее</button></div><CatalogDecisionSelectionTray :items="Object.values(selected)" @remove="removeSelection" @clear="selected = {}" @create-collection="collectionDialogOpen = true" @attach-order="orderDialogOpen = true" @create-order="quickOrderDialogOpen = true" /><CatalogDecisionCollectionDialog :open="collectionDialogOpen" :items="Object.values(selected)" @close="collectionDialogOpen = false" @created="collectionCreated" /><CatalogDecisionOrderDialog :open="orderDialogOpen" :items="Object.values(selected)" @close="orderDialogOpen = false" @attached="orderAttached" /><CatalogDecisionQuickOrderDialog :open="quickOrderDialogOpen" :items="Object.values(selected)" @close="quickOrderDialogOpen = false" @created="orderCreated" /></div></section>
</template>
