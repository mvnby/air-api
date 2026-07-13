<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { watchDebounced } from '@vueuse/core';
import {
  Boxes,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  LoaderCircle,
  RotateCcw,
} from 'lucide-vue-next';
import EquipmentMaintenanceOrderDialog from '../components/equipment/EquipmentMaintenanceOrderDialog.vue';
import EquipmentRegistryCards from '../components/equipment/EquipmentRegistryCards.vue';
import EquipmentRegistryFilters from '../components/equipment/EquipmentRegistryFilters.vue';
import EquipmentRegistryTable from '../components/equipment/EquipmentRegistryTable.vue';
import {
  createEquipmentMaintenanceOrder,
  listEquipmentRegistry,
} from '../components/equipment/api';
import type {
  EquipmentAttentionFilter,
  EquipmentRegistryItem,
} from '../components/equipment/types';
import { getApiErrorMessage } from '../utils/api-errors';

const PAGE_LIMIT = 25;

const items = ref<EquipmentRegistryItem[]>([]);
const search = ref('');
const attention = ref<EquipmentAttentionFilter>('all');
const page = ref(1);
const meta = ref({ total: 0, page: 1, limit: PAGE_LIMIT, pages: 1 });
const loading = ref(false);
const hasLoaded = ref(false);
const error = ref('');

const selectedEquipment = ref<EquipmentRegistryItem | null>(null);
const creatingOrder = ref(false);
const orderError = ref('');

let pendingListRequest: ReturnType<typeof listEquipmentRegistry> | null = null;
let pendingOrderRequest: ReturnType<typeof createEquipmentMaintenanceOrder> | null = null;

const totalPages = computed(() => Math.max(1, meta.value.pages || 1));
const hasActiveFilters = computed(() => Boolean(search.value.trim()) || attention.value !== 'all');
const emptyTitle = computed(() => (
  hasActiveFilters.value ? 'Ничего не найдено' : 'Оборудование пока не добавлено'
));
const equipmentCountLabel = computed(() => {
  const count = meta.value.total;
  const mod10 = count % 10;
  const mod100 = count % 100;
  const unit = mod10 === 1 && mod100 !== 11
    ? 'единица'
    : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)
      ? 'единицы'
      : 'единиц';
  return `${count} ${unit}`;
});

const isCanceledRequest = (requestError: unknown) => (
  requestError instanceof Error && requestError.name === 'CancelError'
);

const loadEquipment = async () => {
  pendingListRequest?.cancel();
  const currentRequest = listEquipmentRegistry({
    page: page.value,
    limit: PAGE_LIMIT,
    q: search.value,
    attention: attention.value,
  });
  pendingListRequest = currentRequest;
  loading.value = true;
  error.value = '';

  try {
    const response = await currentRequest;
    if (pendingListRequest !== currentRequest) return;

    items.value = response.items || [];
    meta.value = {
      ...response.meta,
      pages: Math.max(1, response.meta.pages || 1),
    };
    page.value = response.meta.page || 1;
  } catch (requestError) {
    if (isCanceledRequest(requestError) || pendingListRequest !== currentRequest) return;
    error.value = getApiErrorMessage(requestError);
  } finally {
    if (pendingListRequest === currentRequest) {
      pendingListRequest = null;
      loading.value = false;
      hasLoaded.value = true;
    }
  }
};

const changeAttention = (value: EquipmentAttentionFilter) => {
  if (attention.value === value) return;
  attention.value = value;
  page.value = 1;
  void loadEquipment();
};

const goToPage = (nextPage: number) => {
  const normalizedPage = Math.min(Math.max(1, nextPage), totalPages.value);
  if (normalizedPage === page.value) return;
  page.value = normalizedPage;
  void loadEquipment();
};

const resetFilters = () => {
  const searchChanged = search.value !== '';
  search.value = '';
  attention.value = 'all';
  page.value = 1;
  if (!searchChanged) void loadEquipment();
};

const openMaintenanceOrderDialog = (item: EquipmentRegistryItem) => {
  selectedEquipment.value = item;
  orderError.value = '';
};

const closeMaintenanceOrderDialog = () => {
  if (creatingOrder.value) return;
  selectedEquipment.value = null;
  orderError.value = '';
};

const openCreatedOrder = (orderId: number) => {
  const target = `/manager/orders/kanban?orderId=${encodeURIComponent(String(orderId))}`;
  window.history.pushState({}, '', target);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const confirmMaintenanceOrder = async () => {
  const equipment = selectedEquipment.value;
  if (!equipment || creatingOrder.value) return;

  creatingOrder.value = true;
  orderError.value = '';
  const currentRequest = createEquipmentMaintenanceOrder(equipment.id);
  pendingOrderRequest = currentRequest;

  try {
    const order = await currentRequest;
    if (pendingOrderRequest !== currentRequest) return;
    selectedEquipment.value = null;
    openCreatedOrder(order.id);
  } catch (requestError) {
    if (isCanceledRequest(requestError) || pendingOrderRequest !== currentRequest) return;
    orderError.value = getApiErrorMessage(requestError);
  } finally {
    if (pendingOrderRequest === currentRequest) {
      pendingOrderRequest = null;
      creatingOrder.value = false;
    }
  }
};

watchDebounced(search, () => {
  page.value = 1;
  void loadEquipment();
}, { debounce: 350 });

onMounted(() => {
  void loadEquipment();
});

onBeforeUnmount(() => {
  pendingListRequest?.cancel();
  pendingOrderRequest?.cancel();
});
</script>

<template>
  <main class="w-full px-4 py-5 sm:px-6 lg:px-8">
    <div class="mx-auto max-w-[1500px]">
      <header class="flex items-center justify-between gap-4 pb-4">
        <div class="flex min-w-0 items-center gap-3">
          <span class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-300">
            <Boxes class="h-5 w-5" />
          </span>
          <div class="min-w-0">
            <h1 class="truncate text-2xl font-semibold text-gray-950 dark:text-white">Реестр оборудования</h1>
            <p class="mt-0.5 text-sm font-medium text-gray-500 dark:text-slate-400">
              {{ hasLoaded ? equipmentCountLabel : 'Загрузка данных' }}
            </p>
          </div>
        </div>
      </header>

      <EquipmentRegistryFilters
        v-model="search"
        :attention="attention"
        :loading="loading"
        @update:attention="changeAttention"
        @refresh="loadEquipment"
      />

      <div
        v-if="error"
        class="mt-4 flex flex-col gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 sm:flex-row sm:items-center sm:justify-between dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-300"
      >
        <span class="flex min-w-0 items-start gap-2 font-medium">
          <CircleAlert class="mt-0.5 h-4 w-4 shrink-0" />
          <span class="break-words">{{ error }}</span>
        </span>
        <button
          type="button"
          class="inline-flex min-h-8 shrink-0 items-center justify-center rounded-md border border-red-200 bg-white px-3 text-xs font-semibold text-red-700 transition hover:bg-red-100 dark:border-red-500/40 dark:bg-transparent dark:text-red-300 dark:hover:bg-red-500/10"
          @click="loadEquipment"
        >
          Повторить
        </button>
      </div>

      <div class="flex items-center justify-between gap-3 py-3 text-sm">
        <p class="font-medium text-gray-500 dark:text-slate-400">
          Найдено: <span class="font-semibold text-gray-900 dark:text-slate-100">{{ meta.total }}</span>
        </p>
        <p v-if="totalPages > 1" class="text-xs font-medium text-gray-500 dark:text-slate-400">
          Страница {{ page }} из {{ totalPages }}
        </p>
      </div>

      <div
        v-if="loading && !hasLoaded"
        class="flex min-h-56 items-center justify-center gap-2 border-y border-gray-200 text-sm font-medium text-gray-500 dark:border-slate-700 dark:text-slate-400"
      >
        <LoaderCircle class="h-5 w-5 animate-spin text-teal-600 dark:text-teal-300" />
        Загрузка оборудования
      </div>

      <div
        v-else-if="hasLoaded && !error && !items.length"
        class="flex min-h-56 flex-col items-center justify-center border-y border-dashed border-gray-300 px-4 text-center dark:border-slate-700"
      >
        <Boxes class="h-9 w-9 text-gray-300 dark:text-slate-600" />
        <h2 class="mt-3 text-base font-semibold text-gray-900 dark:text-white">{{ emptyTitle }}</h2>
        <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">По текущим условиям нет записей.</p>
        <button
          v-if="hasActiveFilters"
          type="button"
          class="mt-4 inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-gray-200 bg-white px-3 text-sm font-semibold text-gray-700 transition hover:border-teal-300 hover:text-teal-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-teal-600 dark:hover:text-teal-300"
          @click="resetFilters"
        >
          <RotateCcw class="h-4 w-4" />
          Сбросить фильтры
        </button>
      </div>

      <div v-else :class="loading ? 'pointer-events-none opacity-60' : ''" class="transition-opacity">
        <EquipmentRegistryTable :items="items" @create-maintenance-order="openMaintenanceOrderDialog" />
        <EquipmentRegistryCards :items="items" @create-maintenance-order="openMaintenanceOrderDialog" />
      </div>

      <nav
        v-if="hasLoaded && totalPages > 1"
        class="mt-3 flex items-center justify-center gap-3 border-t border-gray-200 pt-3 dark:border-slate-700"
        aria-label="Страницы реестра оборудования"
      >
        <button
          type="button"
          class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-gray-200 bg-white text-gray-600 transition hover:border-teal-300 hover:text-teal-700 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-teal-600 dark:hover:text-teal-300"
          :disabled="page <= 1 || loading"
          title="Предыдущая страница"
          aria-label="Предыдущая страница"
          @click="goToPage(page - 1)"
        >
          <ChevronLeft class="h-4 w-4" />
        </button>
        <span class="min-w-20 text-center text-sm font-semibold text-gray-600 dark:text-slate-300">
          {{ page }} / {{ totalPages }}
        </span>
        <button
          type="button"
          class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-gray-200 bg-white text-gray-600 transition hover:border-teal-300 hover:text-teal-700 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-teal-600 dark:hover:text-teal-300"
          :disabled="page >= totalPages || loading"
          title="Следующая страница"
          aria-label="Следующая страница"
          @click="goToPage(page + 1)"
        >
          <ChevronRight class="h-4 w-4" />
        </button>
      </nav>
    </div>

    <EquipmentMaintenanceOrderDialog
      v-if="selectedEquipment"
      :equipment="selectedEquipment"
      :loading="creatingOrder"
      :error="orderError"
      @close="closeMaintenanceOrderDialog"
      @confirm="confirmMaintenanceOrder"
    />
  </main>
</template>
