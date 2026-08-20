<script setup lang="ts">
import { onMounted, ref } from 'vue';
import CatalogDecisionFilters from '../components/catalog-decision/CatalogDecisionFilters.vue';
import CatalogDecisionTable from '../components/catalog-decision/CatalogDecisionTable.vue';
import { catalogDecisionApi, type CatalogDecisionFilters as Filters, type CatalogDecisionItem, type CatalogDecisionSort } from '../services/catalog-decision-api';
import { getApiErrorMessage } from '../utils/api-errors';

const items = ref<CatalogDecisionItem[]>([]); const filters = ref<Filters>({ isPublished: true }); const sort = ref<CatalogDecisionSort>('title'); const direction = ref<'asc' | 'desc'>('asc'); const page = ref(1); const pages = ref(1); const total = ref(0); const loading = ref(false); const error = ref('');
const load = async () => { loading.value = true; error.value = ''; try { const response = await catalogDecisionApi.list(page.value, 40, filters.value, sort.value, direction.value); items.value = response.items ?? []; page.value = response.meta.page; pages.value = response.meta.pages; total.value = response.meta.total; } catch (err) { error.value = getApiErrorMessage(err) || 'Не удалось загрузить рабочий каталог'; } finally { loading.value = false; } };
const apply = (next: Filters) => { filters.value = next; page.value = 1; void load(); };
const reset = () => { filters.value = { isPublished: true }; page.value = 1; void load(); };
const changeSort = (next: CatalogDecisionSort) => { direction.value = sort.value === next && direction.value === 'asc' ? 'desc' : 'asc'; sort.value = next; page.value = 1; void load(); };
const go = (next: number) => { if (next >= 1 && next <= pages.value && !loading.value) { page.value = next; void load(); } };
onMounted(() => void load());
</script>

<template><section class="min-h-full bg-gray-50 p-4 md:p-6" data-testid="catalog-decision-workspace"><div class="mx-auto max-w-7xl space-y-4"><header><h1 class="text-2xl font-bold text-gray-900">Подбор оборудования</h1><p class="mt-1 text-sm text-gray-500">Рабочий каталог для предложения клиенту. Карточки master-каталога здесь не редактируются.</p></header><CatalogDecisionFilters @apply="apply" @reset="reset" /><p v-if="error" class="rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p><p class="text-sm text-gray-500">Найдено: {{ total }}</p><div v-if="loading" class="py-12 text-center text-gray-500">Загрузка…</div><CatalogDecisionTable v-else :items="items" :sort="sort" :direction="direction" @sort="changeSort" /><div class="flex items-center justify-between text-sm"><button class="rounded border px-3 py-2 disabled:opacity-40" :disabled="page <= 1 || loading" @click="go(page - 1)">Назад</button><span>Страница {{ page }} из {{ pages }}</span><button class="rounded border px-3 py-2 disabled:opacity-40" :disabled="page >= pages || loading" @click="go(page + 1)">Далее</button></div></div></section></template>
