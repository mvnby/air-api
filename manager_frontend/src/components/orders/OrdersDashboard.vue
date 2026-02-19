<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import type { DashboardView, Segment } from '../../api';
import { api } from '../../api';
import type { ManagerOrderDetailResponse, ManagerOrderListItemResponse, ManagerOrderUpdatePayload } from '../../client';
import OrdersTabSwitcher from './OrdersTabSwitcher.vue';
import OrdersViewToggle from './OrdersViewToggle.vue';
import OrderKanbanBoard from './OrderKanbanBoard.vue';
import OrdersListTable from './OrdersListTable.vue';
import OrderEditDrawer from './OrderEditDrawer.vue';
import { STATUS_LABELS, STATUS_ORDER } from './order-utils';
import { getApiErrorMessage, parseApiFieldErrors } from '../../utils/api-errors';

const ORDERS_SEGMENT_STORAGE_KEY = 'manager_orders_segment';
const ORDERS_VIEW_STORAGE_KEY = 'manager_orders_view';

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

const groupedOrders = computed(() => {
  const groups: Record<string, ManagerOrderListItemResponse[]> = {};
  for (const statusKey of STATUS_ORDER) groups[statusKey] = [];
  for (const order of orders.value) {
    const key = order.status;
    if (!groups[key]) groups[key] = [];
    groups[key].push(order);
  }
  return groups;
});

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2500);
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

  const segmentFromStorage = window.localStorage.getItem(ORDERS_SEGMENT_STORAGE_KEY);
  const viewFromStorage = window.localStorage.getItem(ORDERS_VIEW_STORAGE_KEY);

  const resolvedSegment = segmentFromUrl || segmentFromStorage;
  const resolvedView = viewFromUrl || viewFromStorage;

  if (resolvedSegment === 'b2b' || resolvedSegment === 'b2c') {
    segment.value = resolvedSegment;
  }
  if (resolvedView === 'kanban' || resolvedView === 'list') {
    view.value = resolvedView as DashboardView;
  }
};

const persistSegmentAndView = () => {
  window.localStorage.setItem(ORDERS_SEGMENT_STORAGE_KEY, segment.value);
  window.localStorage.setItem(ORDERS_VIEW_STORAGE_KEY, view.value);
  setQueryParam('segment', segment.value);
  setQueryParam('view', view.value);
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
    orders.value = response.items;
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
    persistSegmentAndView();
    await loadOrders();
  },
);
watch(view, () => {
  persistSegmentAndView();
});
watch(search, () => {
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
    const response = await api.moveOrderStatus(payload.orderId, payload.newStatus);
    if (!response.success) throw new Error(response.error || 'Move failed');
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
    drawerOpen.value = false;
    setToast('Сделка сохранена');
    await loadOrders();
  } catch (error) {
    console.error(error);
    const parsed = parseApiFieldErrors(error, [
      'status',
      'next_followup_date',
      'assessment_date',
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

const checkAuth = async () => {
  try {
    await api.checkAuth();
    showLoginModal.value = false;
    await loadOrders();
  } catch {
    showLoginModal.value = true;
  }
};

onMounted(async () => {
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
  await checkAuth();
});

watch(drawerOpen, (isOpen) => {
  if (!isOpen) {
    clearOrderIdFromUrl();
    openedByUrlOrderId.value = null;
    orderServerErrors.value = {};
    orderFormError.value = '';
  }
});
</script>

<template>
  <div class="min-h-screen bg-gray-50 text-slate-900">
    <div class="mx-auto max-w-[1400px] px-4 py-6 md:px-8">
      <header class="mb-5 rounded-[2rem] border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-sm p-5">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h1 class="text-2xl font-bold dark:text-white">CRM Orders Dashboard</h1>
          <OrdersViewToggle v-model="view" />
        </div>
        <div class="mb-4">
          <OrdersTabSwitcher v-model="segment" />
        </div>
        <div class="grid gap-3 md:grid-cols-4">
          <input v-model="search" class="field-input" placeholder="Поиск: клиент, телефон, УНП, ID" />
          <select v-model="statusFilter" class="field-input">
            <option value="">Все статусы</option>
            <option v-for="statusKey in STATUS_ORDER" :key="statusKey" :value="statusKey">
              {{ STATUS_LABELS[statusKey] || statusKey }}
            </option>
          </select>
          <select v-model="sort" class="field-input">
            <option value="created_at_desc">Новые сверху</option>
            <option value="created_at_asc">Старые сверху</option>
            <option value="updated_at_desc">Недавно обновленные</option>
            <option value="margin_desc">Макс. маржа</option>
            <option value="followup_asc">Ближайшее касание</option>
          </select>
          <label class="inline-flex items-center gap-2 rounded-[12px] border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-300 px-3 py-2">
            <input v-model="overdueOnly" type="checkbox" />
            Только просроченные касания
          </label>
        </div>
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
        :grouped-orders="groupedOrders"
        :segment="segment"
        :moving-order-ids="movingOrderIds"
        @open="openOrder"
        @generate="onGenerateDoc"
        @move="onMoveOrder"
      />

      <OrdersListTable
        v-else
        :orders="orders"
        :segment="segment"
        @open="openOrder"
        @generate="onGenerateDoc"
      />
    </div>

    <OrderEditDrawer
      v-model="drawerOpen"
      :order="selectedOrder"
      :server-errors="orderServerErrors"
      :form-error="orderFormError"
      :saving="saving"
      @save="saveOrder"
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
  </div>
</template>
