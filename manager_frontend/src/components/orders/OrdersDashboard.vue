<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { Download, SlidersHorizontal, Upload } from 'lucide-vue-next';
import type { DashboardView, Segment } from '../../api';
import { api } from '../../api';
import {
  ManagerOrdersService,
  type ManagerOrderDetailResponse,
  type ManagerOrderImportPreviewResponse,
  type ManagerOrderListItemResponse,
  type ManagerOrderTransferPackage_Input,
  type ManagerOrderUpdatePayload,
} from '../../client';
import OrdersTabSwitcher from './OrdersTabSwitcher.vue';
import OrdersViewToggle from './OrdersViewToggle.vue';
import OrderKanbanBoard from './OrderKanbanBoard.vue';
import OrdersListTable from './OrdersListTable.vue';
import OrderEditDrawer from './OrderEditDrawer.vue';
import { STATUS_LABELS, STATUS_ORDER, buildCustomerOrderRenderItems } from './order-utils';
import { getApiErrorMessage, parseApiFieldErrors } from '../../utils/api-errors';

const ORDERS_SEGMENT_STORAGE_KEY = 'manager_orders_segment';
const ORDERS_VIEW_STORAGE_KEY = 'manager_orders_view';
const ORDERS_GROUP_BY_CUSTOMER_STORAGE_KEY = 'manager_orders_group_by_customer_v2';
const ORDERS_CUSTOMER_ALIASES_STORAGE_KEY = 'manager_orders_customer_aliases';

const segment = ref<Segment>('b2c');
const view = ref<DashboardView>('kanban');
const statusFilter = ref('');
const overdueOnly = ref(false);
const sort = ref('created_at_desc');
const search = ref('');
const loading = ref(false);
const saving = ref(false);
const orders = ref<ManagerOrderListItemResponse[]>([]);
const movingOrderIds = ref<number[]>([]);
const toast = ref('');
const isHydrated = ref(false);

const drawerOpen = ref(false);
const selectedOrder = ref<ManagerOrderDetailResponse | null>(null);
const pendingOpenOrderId = ref<number | null>(null);
const openedByUrlOrderId = ref<number | null>(null);
const orderServerErrors = ref<Record<string, string>>({});
const orderFormError = ref('');

const showLoginModal = ref(false);
const loginUsername = ref('');
const loginPassword = ref('');
const loginLoading = ref(false);
const loginError = ref('');

const hideOnHold = ref(true);
const groupByCustomer = ref(true);
const filtersOpen = ref(false);
const customerAliases = ref<Record<number, string>>({});
const selectedOrderIds = ref<number[]>([]);
const transferLoading = ref(false);
const importFileInput = ref<HTMLInputElement | null>(null);
const importPackage = ref<ManagerOrderTransferPackage_Input | null>(null);
const importPreview = ref<ManagerOrderImportPreviewResponse | null>(null);
const importFileName = ref('');
const importModalOpen = ref(false);

const visibleOrders = computed(() => (
  hideOnHold.value ? orders.value.filter((order) => !order.is_on_hold) : orders.value
));

const groupedOrders = computed(() => {
  const groups: Record<string, ManagerOrderListItemResponse[]> = {};
  for (const statusKey of STATUS_ORDER) groups[statusKey] = [];
  for (const order of visibleOrders.value) {
    const key = order.status;
    if (!groups[key]) groups[key] = [];
    groups[key].push(order);
  }
  return groups;
});

const groupedOrderItems = computed(() => {
  const groups = groupedOrders.value;
  const items: Record<string, ReturnType<typeof buildCustomerOrderRenderItems>> = {};
  for (const statusKey of STATUS_ORDER) {
    items[statusKey] = buildCustomerOrderRenderItems(groups[statusKey] || [], segment.value, groupByCustomer.value, customerAliases.value);
  }
  return items;
});

const listItems = computed(() => buildCustomerOrderRenderItems(visibleOrders.value, segment.value, groupByCustomer.value, customerAliases.value));
const visibleOrderIds = computed(() => visibleOrders.value.map((order) => order.id));

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2500);
};

const toggleOrderSelection = (payload: { orderId: number; selected: boolean }) => {
  const next = new Set(selectedOrderIds.value);
  if (payload.selected) next.add(payload.orderId);
  else next.delete(payload.orderId);
  selectedOrderIds.value = Array.from(next);
};

const toggleManySelection = (payload: { orderIds: number[]; selected: boolean }) => {
  const next = new Set(selectedOrderIds.value);
  payload.orderIds.forEach((orderId) => {
    if (payload.selected) next.add(orderId);
    else next.delete(orderId);
  });
  selectedOrderIds.value = Array.from(next);
};

const selectAllVisible = () => {
  selectedOrderIds.value = Array.from(new Set([...selectedOrderIds.value, ...visibleOrderIds.value]));
};

const clearSelection = () => {
  selectedOrderIds.value = [];
};

const downloadJson = (payload: unknown, filename: string) => {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

const exportSelectedOrders = async () => {
  if (!selectedOrderIds.value.length) {
    setToast('Выберите заказы для экспорта');
    return;
  }
  transferLoading.value = true;
  try {
    const payload = await ManagerOrdersService.exportManagerOrders({
      order_ids: selectedOrderIds.value,
      include_payments: true,
      include_work_stages: true,
    });
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
    downloadJson(payload, `orders-export-${stamp}.json`);
    setToast(`Экспортировано: ${selectedOrderIds.value.length}`);
  } catch (error) {
    console.error(error);
    setToast(`Ошибка экспорта: ${getApiErrorMessage(error)}`);
  } finally {
    transferLoading.value = false;
  }
};

const openImportPicker = () => {
  importFileInput.value?.click();
};

const resetImportState = () => {
  importPackage.value = null;
  importPreview.value = null;
  importFileName.value = '';
  importModalOpen.value = false;
  if (importFileInput.value) importFileInput.value.value = '';
};

const handleImportFile = async (event: Event) => {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  transferLoading.value = true;
  try {
    const raw = await file.text();
    const parsed = JSON.parse(raw) as ManagerOrderTransferPackage_Input;
    const preview = await ManagerOrdersService.previewImportManagerOrders({ package: parsed });
    importPackage.value = parsed;
    importPreview.value = preview;
    importFileName.value = file.name;
    importModalOpen.value = true;
  } catch (error) {
    console.error(error);
    setToast(`Ошибка импорта: ${getApiErrorMessage(error)}`);
    if (input) input.value = '';
  } finally {
    transferLoading.value = false;
  }
};

const commitImport = async () => {
  if (!importPackage.value || !importPreview.value?.can_import || transferLoading.value) return;
  transferLoading.value = true;
  try {
    const response = await ManagerOrdersService.importManagerOrders({ package: importPackage.value });
    setToast(`Создано заказов: ${response.created_count}`);
    resetImportState();
    clearSelection();
    await loadOrders();
    const firstCreatedOrderId = response.created_order_ids?.[0];
    if (firstCreatedOrderId) {
      await openOrder(firstCreatedOrderId);
    }
  } catch (error) {
    console.error(error);
    setToast(`Ошибка импорта: ${getApiErrorMessage(error)}`);
  } finally {
    transferLoading.value = false;
  }
};

let loadRequestId = 0;
const setQueryParam = (key: string, value: string) => {
  const url = new URL(window.location.href);
  if (value) {
    url.searchParams.set(key, value);
  } else {
    url.searchParams.delete(key);
  }
  window.history.replaceState({}, '', `${url.pathname}${url.search}`);
};

const restoreSegmentAndView = () => {
  const params = new URLSearchParams(window.location.search);
  const segmentFromUrl = params.get('segment');
  const viewFromUrl = params.get('view');
  const groupByFromUrl = params.get('groupBy');

  const segmentFromStorage = window.localStorage.getItem(ORDERS_SEGMENT_STORAGE_KEY);
  const viewFromStorage = window.localStorage.getItem(ORDERS_VIEW_STORAGE_KEY);
  const groupByFromStorage = window.localStorage.getItem(ORDERS_GROUP_BY_CUSTOMER_STORAGE_KEY);

  const resolvedSegment = segmentFromUrl || segmentFromStorage;
  const resolvedView = viewFromUrl || viewFromStorage;

  if (resolvedSegment === 'b2b' || resolvedSegment === 'b2c') {
    segment.value = resolvedSegment;
  }
  if (resolvedView === 'kanban' || resolvedView === 'list') {
    view.value = resolvedView as DashboardView;
  }
  if (groupByFromUrl === 'customer') {
    groupByCustomer.value = true;
  } else if (!groupByFromUrl && groupByFromStorage === 'false') {
    groupByCustomer.value = false;
  }
};

const persistSegmentAndView = () => {
  window.localStorage.setItem(ORDERS_SEGMENT_STORAGE_KEY, segment.value);
  window.localStorage.setItem(ORDERS_VIEW_STORAGE_KEY, view.value);
  setQueryParam('segment', segment.value);
  setQueryParam('view', view.value);
};

const persistGrouping = () => {
  window.localStorage.setItem(ORDERS_GROUP_BY_CUSTOMER_STORAGE_KEY, groupByCustomer.value ? 'true' : 'false');
  setQueryParam('groupBy', groupByCustomer.value ? 'customer' : '');
};

const restoreCustomerAliases = () => {
  try {
    const raw = window.localStorage.getItem(ORDERS_CUSTOMER_ALIASES_STORAGE_KEY);
    customerAliases.value = raw ? JSON.parse(raw) : {};
  } catch {
    customerAliases.value = {};
  }
};

const persistCustomerAliases = () => {
  window.localStorage.setItem(ORDERS_CUSTOMER_ALIASES_STORAGE_KEY, JSON.stringify(customerAliases.value));
};

const renameCustomerGroup = (payload: { customerId: number; alias: string | null }) => {
  const next = { ...customerAliases.value };
  if (payload.alias) {
    next[payload.customerId] = payload.alias;
  } else {
    delete next[payload.customerId];
  }
  customerAliases.value = next;
  persistCustomerAliases();
  setToast(payload.alias ? 'Название группы сохранено' : 'Название группы сброшено');
};

const renameOrderTitle = async (payload: { orderId: number; title: string | null }) => {
  const nextTitle = payload.title?.trim() || null;
  const snapshot = orders.value.map((item) => ({ ...item }));
  const item = orders.value.find((order) => order.id === payload.orderId);
  const previousSelectedTitle = selectedOrder.value?.id === payload.orderId ? selectedOrder.value.title : undefined;

  if (item) item.title = nextTitle;
  if (selectedOrder.value?.id === payload.orderId) selectedOrder.value.title = nextTitle;

  try {
    await api.patchManagerOrder(payload.orderId, { title: nextTitle });
    setToast(nextTitle ? 'Название заказа сохранено' : 'Название заказа сброшено');
  } catch (error) {
    console.error(error);
    orders.value = snapshot;
    if (selectedOrder.value?.id === payload.orderId) selectedOrder.value.title = previousSelectedTitle ?? null;
    setToast(`Не удалось сохранить название: ${getApiErrorMessage(error)}`);
  }
};

const loadOrders = async () => {
  const requestId = ++loadRequestId;
  loading.value = true;
  try {
    const response = await api.getManagerOrders({
      segment: segment.value,
      status: statusFilter.value || undefined,
      search: search.value || undefined,
      overdueOnly: overdueOnly.value,
      sort: sort.value,
      page: 1,
      limit: 100,
    });
    if (requestId !== loadRequestId) return;
    // Leads are managed in the dedicated Leads section and should not appear in Orders.
    orders.value = response.items.filter((item) => item.status !== 'new_lead');
    const loadedIds = new Set(orders.value.map((order) => order.id));
    selectedOrderIds.value = selectedOrderIds.value.filter((orderId) => loadedIds.has(orderId));
    if (pendingOpenOrderId.value && openedByUrlOrderId.value !== pendingOpenOrderId.value) {
      await openOrder(pendingOpenOrderId.value, false);
      openedByUrlOrderId.value = pendingOpenOrderId.value;
    }
  } catch (error) {
    if (requestId !== loadRequestId) return;
    console.error(error);
    const maybe = error as { status?: number };
    if (maybe?.status === 401) {
      showLoginModal.value = true;
      setToast('Требуется повторный вход');
      return;
    }
    setToast(`Не удалось загрузить сделки: ${getApiErrorMessage(error)}`);
  } finally {
    if (requestId !== loadRequestId) return;
    loading.value = false;
  }
};

let searchTimer: number | undefined;
watch(
  () => [segment.value, statusFilter.value, overdueOnly.value, sort.value],
  async () => {
    if (!isHydrated.value) return;
    persistSegmentAndView();
    await loadOrders();
  },
);
watch(view, () => {
  persistSegmentAndView();
});
watch(groupByCustomer, () => {
  if (!isHydrated.value) return;
  persistGrouping();
});
watch(search, () => {
  if (!isHydrated.value) return;
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(async () => {
    await loadOrders();
  }, 250);
});

const applyStatusLocally = (orderId: number, status: string) => {
  const item = orders.value.find((order) => order.id === orderId);
  if (item) item.status = status;
};

const onMoveOrder = async (payload: { orderId: number; oldStatus: string; newStatus: string }) => {
  if (movingOrderIds.value.includes(payload.orderId)) return;
  const snapshot = orders.value.map((item) => ({ ...item }));
  movingOrderIds.value.push(payload.orderId);
  applyStatusLocally(payload.orderId, payload.newStatus);
  try {
    await api.moveOrderStatus(payload.orderId, payload.newStatus);
    setToast('Статус обновлен');
  } catch (error) {
    console.error(error);
    orders.value = snapshot;
    setToast('Ошибка обновления статуса');
  } finally {
    movingOrderIds.value = movingOrderIds.value.filter((id) => id !== payload.orderId);
  }
};

const onGenerateDoc = async (payload: { orderId: number; docType: string }) => {
  try {
    const response = await api.generateManagerOrderDoc(payload.orderId, payload.docType);
    window.open(response.edit_url, '_blank', 'noopener,noreferrer');
  } catch (error) {
    console.error(error);
    setToast('Не удалось создать документ');
  }
};

const openOrder = async (orderId: number, updateUrl = true) => {
  try {
    orderServerErrors.value = {};
    orderFormError.value = '';
    selectedOrder.value = await api.getManagerOrderDetail(orderId);
    drawerOpen.value = true;
    if (updateUrl) {
      const url = new URL(window.location.href);
      url.searchParams.set('orderId', String(orderId));
      window.history.replaceState({}, '', `${url.pathname}${url.search}`);
      pendingOpenOrderId.value = orderId;
      openedByUrlOrderId.value = orderId;
    }
  } catch (error) {
    console.error(error);
    setToast('Не удалось открыть сделку');
  }
};

const saveOrder = async (payload: { orderId: number; data: ManagerOrderUpdatePayload }) => {
  if (saving.value) return;
  saving.value = true;
  orderServerErrors.value = {};
  orderFormError.value = '';
  try {
    selectedOrder.value = await api.patchManagerOrder(payload.orderId, payload.data);
    setToast('Сделка сохранена');
    await loadOrders();
  } catch (error) {
    console.error(error);
    const parsed = parseApiFieldErrors(error, [
      'status',
      'title',
      'manager_labels',
      'next_followup_date',
      'measurement_date',
      'installation_date',
      'comment',
      'is_paid',
      'customer_name',
      'customer_phone',
      'customer_email',
      'customer_inn',
      'customer_full_legal_name',
      'customer_legal_address',
      'customer_bank_name',
      'customer_bic',
      'customer_iban',
      'customer_delivery_address',
      'target_currency',
      'target_currency_amount',
      'products',
      'services',
    ]);
    orderServerErrors.value = parsed.fieldErrors;
    orderFormError.value = parsed.message;
    setToast(`Ошибка сохранения: ${parsed.message}`);
  } finally {
    saving.value = false;
  }
};

const handleOrderDeleted = async (orderId: number) => {
  orders.value = orders.value.filter((order) => order.id !== orderId);
  drawerOpen.value = false;
  selectedOrder.value = null;
  setToast('Сделка удалена');
  await loadOrders();
};

const clearOrderIdFromUrl = () => {
  const url = new URL(window.location.href);
  if (!url.searchParams.has('orderId')) return;
  url.searchParams.delete('orderId');
  window.history.replaceState({}, '', `${url.pathname}${url.search}`);
};

const handleLogin = async () => {
  loginLoading.value = true;
  loginError.value = '';
  try {
    await api.login(loginUsername.value, loginPassword.value);
    showLoginModal.value = false;
    await loadOrders();
  } catch {
    loginError.value = 'Неверный логин или пароль';
  } finally {
    loginLoading.value = false;
  }
};

onMounted(async () => {
  restoreCustomerAliases();
  restoreSegmentAndView();
  const params = new URLSearchParams(window.location.search);
  const searchParam = params.get('search');
  if (searchParam) {
    search.value = searchParam;
  }
  const orderIdParam = params.get('orderId');
  if (orderIdParam) {
    const parsed = Number(orderIdParam);
    if (Number.isFinite(parsed) && parsed > 0) {
      pendingOpenOrderId.value = parsed;
    }
  }
  persistSegmentAndView();
  persistGrouping();
  try {
    await loadOrders();
  } finally {
    isHydrated.value = true;
  }
});

watch(drawerOpen, (isOpen) => {
  if (!isOpen) {
    clearOrderIdFromUrl();
    openedByUrlOrderId.value = null;
    pendingOpenOrderId.value = null;
    orderServerErrors.value = {};
    orderFormError.value = '';
  }
});
</script>

<template>
  <div class="min-h-screen bg-gray-50 text-slate-900">
    <div class="mx-auto max-w-[1400px] px-4 py-6 md:px-8">
      <header class="mb-4 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <div class="flex items-center gap-1 pl-9 sm:gap-2 md:pl-0">
          <div class="flex min-w-0 shrink items-center gap-1 sm:gap-2">
            <h1 class="shrink-0 text-lg font-bold dark:text-white md:text-xl">Заказы</h1>
            <OrdersTabSwitcher v-model="segment" />
          </div>
          <div class="ml-auto flex shrink-0 items-center justify-end gap-1 sm:gap-2">
            <button
              type="button"
              class="inline-flex h-8 items-center justify-center gap-1 rounded-xl border border-gray-200 bg-gray-50 px-2 text-xs font-semibold text-gray-700 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 sm:h-9 sm:px-3"
              :disabled="transferLoading || !selectedOrderIds.length"
              title="Экспорт выбранных заказов"
              @click="exportSelectedOrders"
            >
              <Download class="h-4 w-4" />
              <span class="hidden sm:inline">Экспорт</span>
              <span v-if="selectedOrderIds.length" class="rounded-full bg-teal-100 px-1.5 py-0.5 text-[10px] text-teal-800">{{ selectedOrderIds.length }}</span>
            </button>
            <button
              type="button"
              class="inline-flex h-8 items-center justify-center gap-1 rounded-xl border border-gray-200 bg-gray-50 px-2 text-xs font-semibold text-gray-700 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 sm:h-9 sm:px-3"
              :disabled="transferLoading"
              title="Импорт заказов из JSON"
              @click="openImportPicker"
            >
              <Upload class="h-4 w-4" />
              <span class="hidden sm:inline">Импорт</span>
            </button>
            <input ref="importFileInput" class="hidden" type="file" accept="application/json,.json" @change="handleImportFile" />
            <OrdersViewToggle v-model="view" />
            <button
              type="button"
              class="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-gray-200 bg-gray-50 text-gray-700 transition hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 sm:h-9 sm:w-9"
              :class="filtersOpen ? 'bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-300' : ''"
              :aria-expanded="filtersOpen"
              aria-label="Опции и фильтры"
              title="Опции и фильтры"
              @click="filtersOpen = !filtersOpen"
            >
              <SlidersHorizontal class="h-4 w-4" />
            </button>
          </div>
        </div>
        
        <Transition name="fade">
          <div v-if="filtersOpen" class="mt-3 grid gap-3 rounded-2xl border border-gray-100 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/50 md:grid-cols-3 lg:grid-cols-4">
            <template v-if="view === 'list'">
              <input v-model="search" class="field-input" placeholder="Поиск (клиент, УНП, ID)..." />
              <select v-model="statusFilter" class="field-input">
                <option value="">Все статусы</option>
                <option v-for="statusKey in STATUS_ORDER" :key="statusKey" :value="statusKey">
                  {{ STATUS_LABELS[statusKey] || statusKey }}
                </option>
              </select>
              <label class="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2 text-gray-700 transition hover:bg-gray-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700">
                <input v-model="overdueOnly" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
                <span class="text-sm font-medium">Только просроченные</span>
              </label>
            </template>
            <label class="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2 text-gray-700 transition hover:bg-gray-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700">
              <input v-model="groupByCustomer" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
              <span class="text-sm font-medium">Группировать</span>
            </label>
            <label class="inline-flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2 text-gray-700 transition hover:bg-gray-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700">
              <input v-model="hideOnHold" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
              <span class="text-sm font-medium">Скрывать отложенные</span>
            </label>
            <div v-if="view === 'list'" class="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-800">
              <button type="button" class="text-sm font-medium text-teal-700 disabled:text-gray-400" :disabled="!visibleOrderIds.length" @click="selectAllVisible">Выбрать все</button>
              <span class="text-xs text-gray-400">/</span>
              <button type="button" class="text-sm font-medium text-gray-600 disabled:text-gray-400" :disabled="!selectedOrderIds.length" @click="clearSelection">Сбросить</button>
            </div>
          </div>
        </Transition>
      </header>

      <!-- Toast -->
      <Transition name="fade">
        <div v-if="toast" class="fixed top-6 right-6 z-[100] bg-teal-600 text-white px-6 py-3 rounded-xl shadow-2xl font-medium animate-in slide-in-from-top-4 duration-300">
          {{ toast }}
        </div>
      </Transition>
      <p v-if="loading" class="mb-4 text-sm text-gray-500">Загрузка сделок...</p>

      <OrderKanbanBoard
        v-if="view === 'kanban'"
        :grouped-items="groupedOrderItems"
        :segment="segment"
        :moving-order-ids="movingOrderIds"
        @open="openOrder"
        @generate="onGenerateDoc"
        @move="onMoveOrder"
        @rename-customer="renameCustomerGroup"
        @rename-order="renameOrderTitle"
      />

      <OrdersListTable
        v-else
        :items="listItems"
        :segment="segment"
        :sort="sort"
        :selected-order-ids="selectedOrderIds"
        @update:sort="sort = $event"
        @open="openOrder"
        @generate="onGenerateDoc"
        @rename-order="renameOrderTitle"
        @toggle-select="toggleOrderSelection"
        @toggle-select-many="toggleManySelection"
      />
    </div>

    <OrderEditDrawer
      v-model="drawerOpen"
      :order="selectedOrder"
      :server-errors="orderServerErrors"
      :form-error="orderFormError"
      :saving="saving"
      @save="saveOrder"
      @deleted="handleOrderDeleted"
      @reload="openOrder($event, false)"
    />

    <div v-if="showLoginModal" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4">
      <div class="w-full max-w-sm rounded-[2rem] border border-gray-200 bg-white text-gray-700 p-6">
        <h2 class="mb-4 text-xl font-semibold">Вход в Manager</h2>
        <div class="space-y-3">
          <input v-model="loginUsername" class="field-input" placeholder="Логин" />
          <input v-model="loginPassword" type="password" class="field-input" placeholder="Пароль" @keyup.enter="handleLogin" />
          <p v-if="loginError" class="text-sm text-red-400">{{ loginError }}</p>
          <button class="btn-mini w-full justify-center" :disabled="loginLoading" @click="handleLogin">
            {{ loginLoading ? 'Входим...' : 'Войти' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="importModalOpen && importPreview" class="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4">
      <div class="w-full max-w-2xl rounded-[1.5rem] border border-gray-200 bg-white p-5 text-gray-700 shadow-2xl">
        <div class="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">Импорт заказов</h2>
            <p class="mt-1 text-sm text-gray-500">{{ importFileName || 'orders-export.json' }}</p>
          </div>
          <button class="btn-mini-outline" type="button" @click="resetImportState">Закрыть</button>
        </div>

        <div class="grid gap-3 sm:grid-cols-3">
          <div class="rounded-xl border border-gray-100 bg-slate-50 p-3">
            <p class="text-xs text-gray-500">Заказы</p>
            <p class="text-xl font-bold text-gray-900">{{ importPreview.orders_count }}</p>
          </div>
          <div class="rounded-xl border border-gray-100 bg-slate-50 p-3">
            <p class="text-xs text-gray-500">Товары найдены</p>
            <p class="text-xl font-bold text-teal-700">{{ importPreview.products_matched }} / {{ importPreview.products_total }}</p>
          </div>
          <div class="rounded-xl border border-gray-100 bg-slate-50 p-3">
            <p class="text-xs text-gray-500">Новые клиенты</p>
            <p class="text-xl font-bold text-gray-900">{{ importPreview.customers?.filter((item) => item.status === 'will_create').length || 0 }}</p>
          </div>
        </div>

        <div v-if="importPreview.warnings?.length" class="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <p v-for="warning in importPreview.warnings" :key="warning">{{ warning }}</p>
        </div>

        <div v-if="importPreview.products_missing" class="mt-4 max-h-56 overflow-auto rounded-xl border border-red-100">
          <table class="w-full text-left text-sm">
            <thead class="bg-red-50 text-xs uppercase text-red-700">
              <tr>
                <th class="px-3 py-2">Товар</th>
                <th class="px-3 py-2">Причина</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in importPreview.products?.filter((product) => product.status !== 'matched')" :key="`${item.source_order_id}-${item.product_title}`" class="border-t border-red-100">
                <td class="px-3 py-2">{{ item.product_title }}</td>
                <td class="px-3 py-2 text-red-700">{{ item.reason || 'not_found' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button class="btn-mini-outline justify-center" type="button" :disabled="transferLoading" @click="resetImportState">Отмена</button>
          <button class="btn-mini justify-center" type="button" :disabled="transferLoading || !importPreview.can_import" @click="commitImport">
            {{ transferLoading ? 'Импорт...' : 'Создать заказы' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
