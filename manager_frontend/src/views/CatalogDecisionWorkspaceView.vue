<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import CatalogDecisionFilters from '../components/catalog-decision/CatalogDecisionFilters.vue';
import CatalogDecisionSelectionTray from '../components/catalog-decision/CatalogDecisionSelectionTray.vue';
import CatalogDecisionTable from '../components/catalog-decision/CatalogDecisionTable.vue';
import { catalogDecisionApi, type CatalogDecisionFilters as Filters, type CatalogDecisionItem, type CatalogDecisionSort } from '../services/catalog-decision-api';
import { getApiErrorMessage } from '../utils/api-errors';

const items = ref<CatalogDecisionItem[]>([]);
const brands = ref<Array<{ id: number; title: string }>>([]);
const series = ref<Array<{ id: number; title: string; brandId?: number | null }>>([]);
const filters = ref<Filters>({ isPublished: true });
const sort = ref<CatalogDecisionSort>('title');
const direction = ref<'asc' | 'desc'>('asc');
const page = ref(1); const pages = ref(1); const total = ref(0); const loading = ref(false); const error = ref('');
const selected = ref<Record<number, CatalogDecisionItem>>({});
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
const reset = () => { filters.value = { isPublished: true }; page.value = 1; };
const changeSort = (next: CatalogDecisionSort) => { direction.value = sort.value === next && direction.value === 'asc' ? 'desc' : 'asc'; sort.value = next; page.value = 1; void load(); };
const go = (next: number) => { if (next >= 1 && next <= pages.value && !loading.value) { page.value = next; void load(); } };
const toggleSelection = (item: CatalogDecisionItem) => { const next = { ...selected.value }; if (next[item.id]) delete next[item.id]; else next[item.id] = item; selected.value = next; };
const removeSelection = (id: number) => { const next = { ...selected.value }; delete next[id]; selected.value = next; };
watch(filters, (next, previous) => { if (next.search !== previous.search) { clearTimeout(searchTimer); searchTimer = setTimeout(() => void load(), 220); } else void load(); }, { deep: true });
onMounted(async () => { try { const options = await catalogDecisionApi.filterOptions(); brands.value = options.brands ?? []; series.value = (options.series ?? []).map(item => ({ id: item.id, title: item.title, brandId: item.brand_id })); } catch { /* The list request shows the actionable error. */ } void load(); });
</script>

<template>
  <section class="min-h-full bg-gray-50 p-4 md:p-6" data-testid="catalog-decision-workspace"><div class="mx-auto max-w-7xl space-y-4"><header class="flex flex-wrap items-end justify-between gap-2"><div><h1 class="text-2xl font-bold text-gray-900">Подбор оборудования</h1><p class="mt-1 text-sm text-gray-500">Быстрый рабочий каталог: выберите модели для предложения, не меняя master-каталог.</p></div><p class="text-sm text-gray-500">Найдено: {{ total }}</p></header><CatalogDecisionFilters :model-value="filters" :brands="brands" :series="series" @update:model-value="updateFilters" @reset="reset" /><p v-if="error" class="rounded-xl bg-red-50 p-3 text-sm text-red-700">{{ error }}</p><div v-if="loading" class="py-12 text-center text-gray-500">Загрузка…</div><CatalogDecisionTable v-else :items="items" :selected-ids="Object.keys(selected).map(Number)" :sort="sort" :direction="direction" @sort="changeSort" @toggle="toggleSelection" /><div class="flex items-center justify-between text-sm"><button class="rounded-lg border border-gray-200 px-3 py-2 disabled:opacity-40" :disabled="page <= 1 || loading" @click="go(page - 1)">Назад</button><span>Страница {{ page }} из {{ pages }}</span><button class="rounded-lg border border-gray-200 px-3 py-2 disabled:opacity-40" :disabled="page >= pages || loading" @click="go(page + 1)">Далее</button></div><CatalogDecisionSelectionTray :items="Object.values(selected)" @remove="removeSelection" @clear="selected = {}" /></div></section>
</template>
