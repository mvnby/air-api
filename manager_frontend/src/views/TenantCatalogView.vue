<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { Loader2, Search } from 'lucide-vue-next';

import {
  ManagerTenantCatalogService,
  type ManagerTenantCatalogProductResponse,
} from '../client';
import { getApiErrorMessage } from '../utils/api-errors';

const items = ref<ManagerTenantCatalogProductResponse[]>([]);
const loading = ref(false);
const error = ref('');
const search = ref('');
const allowedFilter = ref<'all' | 'allowed' | 'not_allowed'>('all');
const total = ref(0);
const page = ref(1);
const pages = ref(1);
const pageLimit = 100;

const allowedQuery = computed(() => {
  if (allowedFilter.value === 'allowed') return true;
  if (allowedFilter.value === 'not_allowed') return false;
  return undefined;
});

const loadProducts = async () => {
  loading.value = true;
  error.value = '';
  try {
    const response = await ManagerTenantCatalogService.listManagerTenantCatalogProducts(
      page.value,
      pageLimit,
      search.value.trim() || undefined,
      allowedQuery.value,
    );
    items.value = response.items ?? [];
    total.value = response.meta.total;
    page.value = response.meta.page;
    pages.value = Math.max(1, response.meta.pages);
  } catch (err) {
    error.value = getApiErrorMessage(err) || 'Не удалось загрузить каталог';
  } finally {
    loading.value = false;
  }
};

const submitFilters = () => {
  page.value = 1;
  void loadProducts();
};

const goToPage = (nextPage: number) => {
  if (loading.value || nextPage < 1 || nextPage > pages.value) return;
  page.value = nextPage;
  void loadProducts();
};

onMounted(() => {
  void loadProducts();
});
</script>

<template>
  <section class="min-h-full bg-gray-50 p-4 md:p-6" data-testid="tenant-catalog-view">
    <div class="mx-auto max-w-6xl space-y-5">
      <header>
        <h1 class="text-2xl font-bold text-gray-900">Каталог товаров</h1>
        <p class="mt-1 text-sm text-gray-500">
          Общий каталог доступен только для просмотра. Доступность и цены задаёт оператор.
        </p>
      </header>

      <form class="flex flex-col gap-3 rounded-xl border border-gray-200 bg-white p-4 sm:flex-row" @submit.prevent="submitFilters">
        <label class="relative flex-1">
          <Search class="absolute left-3 top-2.5 h-5 w-5 text-gray-400" />
          <input
            v-model="search"
            class="w-full rounded-lg border border-gray-200 py-2 pl-10 pr-3 text-sm outline-none focus:border-teal-500"
            placeholder="Модель или бренд"
            aria-label="Поиск по каталогу"
          />
        </label>
        <select
          v-model="allowedFilter"
          class="rounded-lg border border-gray-200 px-3 py-2 text-sm"
          aria-label="Фильтр доступности"
          @change="submitFilters"
        >
          <option value="all">Все товары</option>
          <option value="allowed">Разрешены для витрины</option>
          <option value="not_allowed">Не разрешены</option>
        </select>
        <button class="rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700" type="submit">
          Найти
        </button>
      </form>

      <p v-if="error" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      <div v-if="loading" class="flex items-center justify-center py-16 text-gray-500">
        <Loader2 class="mr-2 h-5 w-5 animate-spin" /> Загрузка каталога…
      </div>
      <div v-else class="overflow-hidden rounded-xl border border-gray-200 bg-white">
        <div class="border-b border-gray-100 px-4 py-3 text-sm text-gray-500">Найдено: {{ total }}</div>
        <ul class="divide-y divide-gray-100">
          <li v-for="item in items" :key="item.id" class="flex items-center gap-4 p-4">
            <img v-if="item.main_image" :src="item.main_image" :alt="item.title" class="h-16 w-16 rounded-lg object-contain" />
            <div v-else class="h-16 w-16 rounded-lg bg-gray-100" />
            <div class="min-w-0 flex-1">
              <div class="font-semibold text-gray-900">{{ item.title }}</div>
              <div class="mt-1 text-sm text-gray-500">
                {{ [item.brand_title, item.series_title].filter(Boolean).join(' · ') || 'Без бренда и серии' }}
              </div>
            </div>
            <div class="text-right">
              <div v-if="item.effective_price !== null && item.effective_price !== undefined" class="font-semibold text-gray-900">
                {{ item.effective_price.toLocaleString('ru-BY') }} BYN
              </div>
              <span
                class="mt-1 inline-flex rounded-full px-2 py-1 text-xs font-semibold"
                :class="item.allowed ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-500'"
              >
                {{ item.allowed ? 'Разрешён' : 'Не разрешён' }}
              </span>
            </div>
          </li>
        </ul>
        <div v-if="items.length === 0" class="p-10 text-center text-sm text-gray-500">Товары не найдены</div>
        <div class="flex items-center justify-between border-t border-gray-100 px-4 py-3 text-sm text-gray-600">
          <button
            type="button"
            class="rounded-lg border border-gray-200 px-3 py-1.5 font-semibold disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="loading || page <= 1"
            @click="goToPage(page - 1)"
          >
            Назад
          </button>
          <span>Страница {{ page }} из {{ pages }}</span>
          <button
            type="button"
            class="rounded-lg border border-gray-200 px-3 py-1.5 font-semibold disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="loading || page >= pages"
            @click="goToPage(page + 1)"
          >
            Далее
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
