<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue';
import { api } from '../../api';
import {
  ManagerOrdersService,
  type ManagerOrderDetailResponse,
  type ManagerOrderListItemResponse,
  type ManagerOrderTransferPackage_Input,
  type ManagerOrderUpdatePayload,
} from '../../client';
import OrdersToolbar from './OrdersToolbar.vue';
import OrderKanbanBoard from './OrderKanbanBoard.vue';
import OrdersListTable from './OrdersListTable.vue';
import OrderEditDrawer from './OrderEditDrawer.vue';
import {
  formatMoney,
} from './order-utils';
import { getApiErrorMessage } from '../../utils/api-errors';
import { confirmDialog, promptDialog } from '../../services/ui-feedback';
import { managerSession, requireManagerSessionRecovery } from '../../services/manager-session';
import OrdersImportPreviewModal from './OrdersImportPreviewModal.vue';
import { useOrdersDashboardModel } from './useOrdersDashboardModel';
import {
  buildBoardTransitionPayload,
  needsExecutionWithoutPaymentConfirmation,
  runOptimisticOrderTransition,
} from './order-transition';

const { recoveryRequired } = managerSession;

const toast = ref('');
const loadError = ref('');
const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2500);
};
const {
  segment, view, statusFilter, workFilter, workFilterCounts, hiddenOnHoldCount, sort, search, loading, orders,
  movingOrderIds, isHydrated, drawerOpen, selectedOrder, pendingOpenOrderId,
  openedByUrlOrderId, orderServerErrors, orderFormError, hideOnHold,
  groupByCustomer, filtersOpen, selectedOrderIds, transferLoading, importFileInput,
  importPackage, importPreview, importFileName, importModalOpen, normalizedSearch,
  hasActiveOrderFilters, groupedOrderItems, listItems, visibleOrderIds, setQueryParam,
  restorePreferences, persistSegmentAndView, persistGrouping, restoreCustomerAliases,
  renameCustomerGroup, toggleOrderSelection, toggleManySelection, selectAllVisible,
  clearSelection, clearOrderIdFromUrl, clearIdentityScopedState,
} = useOrdersDashboardModel(setToast);

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
  if (recoveryRequired.value) return;
  const requestId = ++loadRequestId;
  loading.value = true;
  loadError.value = '';
  try {
    const params = {
      segment: segment.value,
      status: statusFilter.value || undefined,
      search: normalizedSearch.value || undefined,
      sort: sort.value,
    };
    const pageLimit = 100;
    const firstPage = await api.getManagerOrders({ ...params, page: 1, limit: pageLimit });
    if (requestId !== loadRequestId) return;
    const loadedOrders = [...firstPage.items];
    const totalPages = Math.max(1, firstPage.meta?.pages || 1);
    const pageBatchSize = 4;
    const remainingPages = Array.from({ length: Math.max(0, totalPages - 1) }, (_, index) => index + 2);
    for (let index = 0; index < remainingPages.length; index += pageBatchSize) {
      const pageBatch = remainingPages.slice(index, index + pageBatchSize);
      const nextPages = await Promise.all(
        pageBatch.map((page) => api.getManagerOrders({ ...params, page, limit: pageLimit })),
      );
      if (requestId !== loadRequestId) return;
      nextPages.forEach((page) => loadedOrders.push(...page.items));
    }
    orders.value = loadedOrders;
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
      loadRequestId += 1;
      clearIdentityScopedState();
      requireManagerSessionRecovery();
      setToast('Требуется повторный вход');
      return;
    }
    loadError.value = `Не удалось загрузить заказы: ${getApiErrorMessage(error)}`;
  } finally {
    if (requestId !== loadRequestId) return;
    loading.value = false;
  }
};

let searchTimer: number | undefined;
const refreshOrders = () => {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = undefined;
  return loadOrders();
};
watch(
  () => [segment.value, statusFilter.value, sort.value, search.value],
  (next, previous) => {
    if (!isHydrated.value) return;
    // Invalidate the old response as soon as the inputs change, including the debounce window.
    loadRequestId += 1;
    persistSegmentAndView();
    setQueryParam('search', normalizedSearch.value);
    if (searchTimer) window.clearTimeout(searchTimer);
    if (next.slice(0, 3).some((value, index) => value !== previous[index])) {
      void refreshOrders();
    } else {
      searchTimer = window.setTimeout(refreshOrders, 250);
    }
  },
);
watch(view, persistSegmentAndView);
watch(groupByCustomer, () => {
  if (isHydrated.value) persistGrouping();
});
const boardFilterReset = ref(0);
const clearOrderFilters = () => {
  search.value = '';
  statusFilter.value = '';
  workFilter.value = 'all';
  hideOnHold.value = false;
  boardFilterReset.value += 1;
  setQueryParam('search', '');
};
onUnmounted(() => {
  loadRequestId += 1;
  if (searchTimer) window.clearTimeout(searchTimer);
});

const applyStatusLocally = (orderId: number, payload: ManagerOrderUpdatePayload) => {
  const item = orders.value.find((order) => order.id === orderId);
  if (!item) return;
  if (payload.status !== undefined && payload.status !== null) item.status = payload.status;
  if (payload.negotiation_status !== undefined && payload.negotiation_status !== null) item.negotiation_status = payload.negotiation_status;
  if (payload.execution_status !== undefined && payload.execution_status !== null) item.execution_status = payload.execution_status;
  if (payload.closing_result !== undefined) item.closing_result = payload.closing_result;
  if (payload.reject_reason !== undefined) item.reject_reason = payload.reject_reason;
  if (payload.measurement_required !== undefined && payload.measurement_required !== null) item.measurement_required = payload.measurement_required;
  if (payload.execution_without_payment !== undefined && payload.execution_without_payment !== null) item.execution_without_payment = payload.execution_without_payment;
  if (payload.execution_without_payment_reason !== undefined) item.execution_without_payment_reason = payload.execution_without_payment_reason;
  const now = new Date().toISOString();
  item.status_changed_at = now;
  if (payload.negotiation_status) item.negotiation_status_changed_at = now;
  if (payload.execution_status) item.execution_status_changed_at = now;
};

const replaceOrderLocally = (updatedOrder: ManagerOrderListItemResponse) => {
  const index = orders.value.findIndex((order) => order.id === updatedOrder.id);
  if (index >= 0) orders.value[index] = updatedOrder;
};

const commitOrderMove = async (orderId: number, updatePayload: ManagerOrderUpdatePayload) => {
  const snapshot = orders.value.map((item) => ({ ...item }));
  movingOrderIds.value.push(orderId);
  try {
    const updatedOrder = await runOptimisticOrderTransition({
      snapshot,
      apply: () => applyStatusLocally(orderId, updatePayload),
      persist: () => api.patchManagerOrder(orderId, updatePayload),
      rollback: (previousOrders) => { orders.value = previousOrders; },
    });
    replaceOrderLocally(updatedOrder);
  } finally {
    movingOrderIds.value = movingOrderIds.value.filter((id) => id !== orderId);
  }
};

const onMoveOrder = async (payload: { orderId: number; oldStatus: string; newStatus: string }) => {
  if (movingOrderIds.value.includes(payload.orderId)) return;
  const item = orders.value.find((order) => order.id === payload.orderId);
  if (!item) return;

  if (needsExecutionWithoutPaymentConfirmation(item, payload.newStatus)) {
    const reason = await promptDialog({
      title: 'Назначить работы без оплаты?',
      description: 'У заказа нет полной зарегистрированной оплаты. Укажите причину перевода в работы.',
      inputLabel: 'Причина',
      initialValue: 'Доверенный клиент',
      inputKind: 'textarea',
      required: true,
      confirmText: 'Назначить работы',
      variant: 'warning',
      onConfirm: async (value) => {
        const updatePayload = buildBoardTransitionPayload(item, payload.newStatus, value || 'Без предоплаты');
        if (!updatePayload) throw new Error('Недоступный статус заказа');
        await commitOrderMove(payload.orderId, updatePayload);
      },
      getErrorMessage: (error) => `Не удалось назначить работы: ${getApiErrorMessage(error)}`,
    });
    if (reason !== null) setToast('Статус обновлен');
    return;
  }

  const updatePayload = buildBoardTransitionPayload(item, payload.newStatus);
  if (!updatePayload) return;
  try {
    await commitOrderMove(payload.orderId, updatePayload);
    setToast('Статус обновлен');
  } catch (error) {
    console.error(error);
    setToast(`Ошибка обновления статуса: ${getApiErrorMessage(error)}`);
  }
};

const onCancelOrder = async (payload: { orderId: number }) => {
  const reason = await promptDialog({
    title: 'Пометить заказ отказом',
    inputLabel: 'Причина отказа или неуспешного завершения',
    inputKind: 'textarea',
    placeholder: 'Кратко опишите причину',
    confirmText: 'Пометить отказом',
    variant: 'danger',
  });
  if (reason === null) return;
  const trimmedReason = reason.trim() || 'Без пояснения';
  const snapshot = orders.value.map((item) => ({ ...item }));
  const updatePayload: ManagerOrderUpdatePayload = {
    status: 'closed',
    closing_result: 'lost',
    reject_reason: trimmedReason,
  };
  movingOrderIds.value.push(payload.orderId);
  applyStatusLocally(payload.orderId, updatePayload);
  try {
    const updatedOrder = await api.patchManagerOrder(payload.orderId, updatePayload);
    replaceOrderLocally(updatedOrder);
    setToast('Заказ помечен отказом');
  } catch (error) {
    console.error(error);
    orders.value = snapshot;
    setToast(`Не удалось закрыть отказ: ${getApiErrorMessage(error)}`);
  } finally {
    movingOrderIds.value = movingOrderIds.value.filter((id) => id !== payload.orderId);
  }
};

const onCloseDebt = async (payload: { orderId: number }) => {
  if (movingOrderIds.value.includes(payload.orderId)) return;
  const item = orders.value.find((order) => order.id === payload.orderId);
  if (!item) return;
  const amount = Number(item.balance_due || 0);
  if (amount <= 0) {
    setToast('Долг уже закрыт');
    return;
  }
  const confirmed = await confirmDialog({
    title: `Закрыть долг по заказу #${payload.orderId}?`,
    description: `Будет добавлена оплата ${formatMoney(amount)}.`,
    confirmText: 'Добавить оплату',
    variant: 'warning',
    onConfirm: async () => {
      movingOrderIds.value.push(payload.orderId);
      try {
        await ManagerOrdersService.addManagerOrderPayment(payload.orderId, {
          amount,
          currency: 'BYN',
          type: 'postpayment',
          comment: 'Закрытие долга из канбан-карточки',
        });
        await loadOrders();
      } finally {
        movingOrderIds.value = movingOrderIds.value.filter((id) => id !== payload.orderId);
      }
    },
    getErrorMessage: (error) => `Не удалось закрыть долг: ${getApiErrorMessage(error)}`,
  });
  if (confirmed) {
    setToast('Долг закрыт');
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

const reloadOrder = async (orderId: number) => {
  await openOrder(orderId, false);
  await loadOrders();
};

const handleOrderDeleted = async (orderId: number) => {
  orders.value = orders.value.filter((order) => order.id !== orderId);
  drawerOpen.value = false;
  selectedOrder.value = null;
  setToast('Сделка удалена');
  await loadOrders();
};

const applyOrderUpdate = (order: ManagerOrderDetailResponse) => {
  selectedOrder.value = order;
  const index = orders.value.findIndex((item) => item.id === order.id);
  if (index !== -1) {
    orders.value.splice(index, 1, order);
  }
};

onMounted(async () => {
  restoreCustomerAliases();
  restorePreferences();
  const params = new URLSearchParams(window.location.search);
  const searchParam = params.get('search');
  if (searchParam) {
    search.value = searchParam;
    filtersOpen.value = true;
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
  <div class="min-h-screen bg-gray-50 text-slate-900 dark:bg-slate-900 dark:text-slate-100">
    <div class="mx-auto max-w-[1400px] px-4 py-6 md:px-8">
      <OrdersToolbar
        v-model:segment="segment" v-model:view="view" v-model:search="search"
        v-model:status-filter="statusFilter" v-model:work-filter="workFilter"
        v-model:group-by-customer="groupByCustomer" v-model:hide-on-hold="hideOnHold"
        v-model:filters-open="filtersOpen" :counts="workFilterCounts"
        :hidden-on-hold-count="hiddenOnHoldCount" :visible-count="visibleOrderIds.length"
        :selected-count="selectedOrderIds.length" :has-active-filters="hasActiveOrderFilters"
        :loading="loading" :load-failed="Boolean(loadError)" :transfer-loading="transferLoading"
        @reset="clearOrderFilters" @search-now="refreshOrders"
        @import="openImportPicker" @export="exportSelectedOrders"
        @select-all="selectAllVisible" @clear-selection="clearSelection"
      />
      <input ref="importFileInput" class="hidden" type="file" accept="application/json,.json" @change="handleImportFile" />

      <!-- Toast -->
      <Transition name="fade">
        <div v-if="toast" class="fixed top-6 right-6 z-[100] bg-brand-600 text-white px-6 py-3 rounded-xl shadow-2xl font-medium animate-in slide-in-from-top-4 duration-300">
          {{ toast }}
        </div>
      </Transition>

      <div v-if="loadError" role="alert" class="rounded-xl border border-red-200 bg-red-50 p-5 text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200">
        <p>{{ loadError }}</p>
        <button type="button" class="mt-3 rounded-lg bg-white px-3 py-2 text-sm font-semibold dark:bg-slate-800" @click="refreshOrders">Повторить</button>
      </div>
      <OrderKanbanBoard
        v-else-if="view === 'kanban'"
        :grouped-items="groupedOrderItems"
        :filter-reset="boardFilterReset"
        :segment="segment"
        :moving-order-ids="movingOrderIds"
        @open="openOrder"
        @generate="onGenerateDoc"
        @move="onMoveOrder"
        @cancel-order="onCancelOrder"
        @close-debt="onCloseDebt"
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
      @updated="applyOrderUpdate"
      @deleted="handleOrderDeleted"
      @reload="reloadOrder"
    />

    <OrdersImportPreviewModal
      v-if="importModalOpen && importPreview"
      :preview="importPreview"
      :filename="importFileName"
      :loading="transferLoading"
      @cancel="resetImportState"
      @commit="commitImport"
    />
  </div>
</template>
