<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { managerStorefrontSelection } from '../../services/manager-storefront-selection';
import { api } from '../../api';
import {
  ManagerOrdersService,
  type ManagerOrderListItemResponse,
  type ManagerOrderTransferPackage_Input,
  type ManagerOrderUpdatePayload,
} from '../../client';
import { useOrderWaiting } from '../../composables/useOrderWaiting';
import OrderWaitingDialog from './OrderWaitingDialog.vue';
import OrdersToolbar from './OrdersToolbar.vue';
import OrderQueueBoard from './OrderQueueBoard.vue';
import { useOrderQueueData } from './useOrderQueueData';
import type { OrderQueue } from '../../services/order-board';

import { openOrderPage, savedOrderListPosition } from '../../services/order-navigation';
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
const queue = ref<OrderQueue>('active');
const historyResult = ref('');
const closedFrom = ref('');
const closedTo = ref('');
const unknownDate = ref(false);
const queueData = useOrderQueueData();
const { pages: queuePages, busy: queueBusy, errors: queueErrors, phases: queuePhases } = queueData;
const queueColumns = computed(() => queue.value === 'history' || normalizedSearch.value || workFilter.value === 'followup' || view.value === 'list' ? [''] : ['negotiation', 'execution']);
const queueLabels: Record<OrderQueue, string> = { active: 'Активные', waiting: 'Ожидание', history: 'История' };
const queueCounts = computed(() => Object.values(queuePages.value)[0]?.queue_counts || {});
const serverWorkCounts = computed(() => Object.values(queuePages.value)[0]?.work_counts || { all: 0, followup: 0, planning: 0, unpaid: 0 });
const filteredTotal = computed(() => queueColumns.value.reduce((sum, key) => sum + (queuePages.value[key]?.total_orders || 0), 0));


const toast = ref('');
const loadError = ref('');
const customerIdFilter = ref<number | undefined>();
const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2500);
};
const {
  segment, view, assignedToMe, canFilterMine, statusFilter, workFilter, workFilterCounts, hiddenOnHoldCount, sort, search, loading, orders,
  movingOrderIds, isHydrated, hideOnHold,
  groupByCustomer, filtersOpen, customerAliases, selectedOrderIds, transferLoading, importFileInput,
  importPackage, importPreview, importFileName, importModalOpen, normalizedSearch,
  hasActiveOrderFilters, setQueryParam,
  restorePreferences, persistSegmentAndView, persistGrouping, restoreCustomerAliases,
  renameCustomerGroup, toggleOrderSelection, toggleManySelection, selectAllVisible,
  clearSelection, clearIdentityScopedState,
} = useOrdersDashboardModel(setToast);

const waiting = useOrderWaiting({ updated: async () => { await loadOrders(); }, notify: setToast });
const toggleOrderWaiting = (orderId: number) => {
  const order = orders.value.find(item => item.id === orderId);
  if (order) void waiting.toggle(order);
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
let restoredPosition = false;
const board = ref<InstanceType<typeof OrderQueueBoard> | null>(null);
const identityScope = computed(() => `${managerSession.auth.value?.staff_user_id || managerSession.auth.value?.username}:${managerSession.auth.value?.tenant_id}:${managerStorefrontSelection.selectedSlug.value}`);
watch(identityScope, () => { loadRequestId++; queueData.reset(); clearIdentityScopedState(); }, { flush: 'sync' });

const restoreOrders = (snapshot: ManagerOrderListItemResponse[]) => {
  const byId = new Map(snapshot.map(order => [order.id, order]));
  for (const page of Object.values(queuePages.value)) page.items = page.items?.map(order => byId.get(order.id) || order);
  orders.value = snapshot;
};

watch(queueData.accessError, error => { if (error) loadError.value = error.message; });

const renameOrderTitle = async (payload: { orderId: number; title: string | null }) => {
  const nextTitle = payload.title?.trim() || null;
  const snapshot = orders.value.map((item) => ({ ...item }));
  const item = orders.value.find((order) => order.id === payload.orderId);

  if (item) item.title = nextTitle;

  try {
    await api.patchManagerOrder(payload.orderId, { title: nextTitle });
    setToast(nextTitle ? 'Название заказа сохранено' : 'Название заказа сброшено');
  } catch (error) {
    console.error(error);
    restoreOrders(snapshot);
    setToast(`Не удалось сохранить название: ${getApiErrorMessage(error)}`);
  }
};

const loadOrders = async () => {
  if (recoveryRequired.value) return;
  const requestId = ++loadRequestId;
  loading.value = true;
  loadError.value = '';
  try {
    const saved = savedOrderListPosition();
    const shouldRestore = !restoredPosition && saved?.url === `${window.location.pathname}${window.location.search}`;
    if (shouldRestore && saved.board) queueData.phases.value = { ...saved.board.columnFilters };
    const responses = await queueData.load({
      segment: segment.value,
      queue: normalizedSearch.value ? 'all' : queue.value,
      assigned_to_me: assignedToMe.value,
      customer_id: customerIdFilter.value,
      status: statusFilter.value || undefined,
      search: normalizedSearch.value || undefined,
      work_filter: workFilter.value,
      group_by_customer: queue.value !== 'history' && groupByCustomer.value && !normalizedSearch.value && workFilter.value !== 'followup',
      result: queue.value === 'history' && !normalizedSearch.value && workFilter.value !== 'followup' ? historyResult.value || undefined : undefined,
      closed_from: queue.value === 'history' && !normalizedSearch.value && workFilter.value !== 'followup' ? closedFrom.value || undefined : undefined,
      closed_to: queue.value === 'history' && !normalizedSearch.value && workFilter.value !== 'followup' ? closedTo.value || undefined : undefined,
      include_unknown_date: unknownDate.value,
      sort: queue.value === 'history' ? 'closed_at_desc' : sort.value,
    }, queueColumns.value);
    if (requestId !== loadRequestId) return;
    orders.value = responses.flatMap(page => page?.items || []);
    const loadedIds = new Set(orders.value.map((order) => order.id));
    selectedOrderIds.value = selectedOrderIds.value.filter((orderId) => loadedIds.has(orderId));
    // Render loaded filter counts before restoring scroll; their wrapping changes mobile height.
    loading.value = false;
    await nextTick();
    const position = savedOrderListPosition();
    if (!restoredPosition && position?.url === `${window.location.pathname}${window.location.search}`) {
      restoredPosition = true;
      if (position.board) {
        for (const [key, count] of Object.entries(position.board.loadedPages || {})) {
          const slash = key.indexOf('/');
          const column = slash < 0 ? key : key.slice(0, slash);
          const group = slash < 0 ? undefined : key.slice(slash + 1);
          for (let page = queuePages.value[key]?.page || 0; page < count; page++) await queueData.more(column, group);
        }
        await board.value?.restoreState(position.board);
      }
      await nextTick();
      window.scrollTo(0, position.top);
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
  () => [segment.value, statusFilter.value, sort.value, assignedToMe.value, queue.value, workFilter.value, groupByCustomer.value, view.value, historyResult.value, closedFrom.value, closedTo.value, unknownDate.value, search.value],
  (next, previous) => {
    if (!isHydrated.value) return;
    // Invalidate the old response as soon as the inputs change, including the debounce window.
    loadRequestId += 1;
    queueData.reset();
    orders.value = [];
    persistSegmentAndView();
    setQueryParam('queue', queue.value);
    setQueryParam('result', historyResult.value);
    setQueryParam('closedFrom', closedFrom.value);
    setQueryParam('closedTo', closedTo.value);
    setQueryParam('unknownDate', unknownDate.value ? 'true' : '');
    setQueryParam('search', normalizedSearch.value);
    setQueryParam('assigned_to_me', assignedToMe.value ? '1' : '');
    setQueryParam('status', statusFilter.value);
    setQueryParam('sort', sort.value);
    if (searchTimer) window.clearTimeout(searchTimer);
    if (next.slice(0, -1).some((value, index) => value !== previous[index])) {
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
watch([workFilter, hideOnHold, filtersOpen], () => {
  if (!isHydrated.value) return;
  setQueryParam('workFilter', workFilter.value);
  setQueryParam('hideOnHold', String(hideOnHold.value));
  setQueryParam('filtersOpen', String(filtersOpen.value));
});
const clearOrderFilters = () => {
  assignedToMe.value = false;
  search.value = '';
  statusFilter.value = '';
  workFilter.value = 'all';
  historyResult.value = ''; closedFrom.value = ''; closedTo.value = ''; unknownDate.value = false;
  hideOnHold.value = false;
  const hadPhases = Object.values(queuePhases.value).some(Boolean);
  queuePhases.value = {};
  if (hadPhases) void refreshOrders();
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

watch(queuePages, () => {
  orders.value = Object.values(queuePages.value).flatMap(page => page.items || []).filter((item, index, all) => all.findIndex(other => other.id === item.id) === index);
}, { deep: true });
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
      rollback: restoreOrders,
    });
    replaceOrderLocally(updatedOrder);
    await loadOrders();
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
    await loadOrders();
    setToast('Заказ помечен отказом');
  } catch (error) {
    console.error(error);
    restoreOrders(snapshot);
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

const openOrder = (orderId: number) => openOrderPage(orderId, board.value?.captureState());

const clearCustomerFilter = () => {
  customerIdFilter.value = undefined;
  setQueryParam('customerId', '');
  void refreshOrders();
};

onMounted(async () => {
  restoreCustomerAliases();
  restorePreferences();
  const params = new URLSearchParams(window.location.search);
  const requestedQueue = params.get('queue');
  if (requestedQueue === 'active' || requestedQueue === 'waiting' || requestedQueue === 'history') queue.value = requestedQueue;
  hideOnHold.value = false;
  historyResult.value = params.get('result') || '';
  closedFrom.value = params.get('closedFrom') || '';
  closedTo.value = params.get('closedTo') || '';
  unknownDate.value = params.get('unknownDate') === 'true';
  const customerId = Number(params.get('customerId'));
  if (Number.isSafeInteger(customerId) && customerId > 0) customerIdFilter.value = customerId;
  const searchParam = params.get('search');
  if (searchParam) {
    search.value = searchParam;
    filtersOpen.value = params.get('filtersOpen') !== 'false';
  }
  persistSegmentAndView();
  persistGrouping();
  // Flush preference watchers before enabling live filter changes during the first request.
  await nextTick();
  isHydrated.value = true;
  await loadOrders();
});

</script>

<template>
  <div class="orders-queue-page bg-gray-50 text-slate-900 dark:bg-slate-900 dark:text-slate-100">
    <div class="orders-queue-inner mx-auto w-full max-w-[1400px] px-4 py-4 md:px-8">
      <OrdersToolbar
        v-model:assigned-to-me="assignedToMe" :can-filter-mine="canFilterMine"
        v-model:segment="segment" v-model:view="view" v-model:search="search"
        v-model:status-filter="statusFilter" v-model:work-filter="workFilter"
        v-model:group-by-customer="groupByCustomer"
        v-model:filters-open="filtersOpen" :counts="serverWorkCounts as typeof workFilterCounts"
        :hidden-on-hold-count="hiddenOnHoldCount" :visible-count="filteredTotal"
        :selected-count="selectedOrderIds.length" :has-active-filters="hasActiveOrderFilters || Boolean(historyResult || closedFrom || closedTo) || Object.values(queuePhases).some(Boolean)"
        :loading="loading" :load-failed="Boolean(loadError) || queueColumns.some(column => Boolean(queueErrors[column]))" :transfer-loading="transferLoading"
        @reset="clearOrderFilters" @search-now="refreshOrders"
        @import="openImportPicker" @export="exportSelectedOrders"
        @select-all="selectAllVisible" @clear-selection="clearSelection"
      />
      <nav class="mb-3 grid grid-cols-3 gap-1 sm:flex sm:gap-2" aria-label="Очереди заказов">
        <button v-for="(label, key) in queueLabels" :key="key" type="button" class="rounded-lg border px-2 py-2 text-xs sm:px-3 sm:text-sm" :class="queue === key ? 'bg-brand-600 text-white' : 'bg-white dark:bg-slate-800'" :aria-pressed="queue === key" @click="queue = key; workFilter = 'all'">
          {{ label }} <span v-if="!loading && !loadError">{{ queueCounts[key] || 0 }}</span>
        </button>
      </nav>
      <p v-if="normalizedSearch" class="mb-2 text-sm text-slate-500">Поиск во всех очередях. Очередь указана рядом с заказом.</p>
      <p v-else-if="workFilter === 'followup'" class="mb-2 text-sm text-slate-500">Контакты из активных и ожидающих заказов. Ожидание не снимается.</p>
      <div v-if="queue === 'history' && !normalizedSearch && workFilter !== 'followup'" class="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <label>Результат <select v-model="historyResult" aria-label="Результат истории" class="rounded border bg-white p-2 dark:bg-slate-800"><option value="">Все</option><option value="won">Успех</option><option value="lost">Отказ</option><option value="unknown">Результат не указан</option></select></label>
        <label>Закрыт с <input v-model="closedFrom" aria-label="Дата закрытия с" type="date" class="rounded border bg-white p-2 dark:bg-slate-800" /></label>
        <label>по <input v-model="closedTo" aria-label="Дата закрытия по" type="date" class="rounded border bg-white p-2 dark:bg-slate-800" /></label>
        <label v-if="closedFrom || closedTo"><input v-model="unknownDate" type="checkbox" /> Включить без даты закрытия</label>
      </div>
      <div v-if="customerIdFilter" class="flex items-center gap-3 mb-3 text-sm">
        <a :href="`/manager/customers/profile?customerId=${customerIdFilter}`" class="text-brand-600">Заказы клиента #{{ customerIdFilter }}</a>
        <button type="button" class="text-slate-500 underline" @click="clearCustomerFilter">Все клиенты</button>
      </div>
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
      <OrderQueueBoard ref="board" v-else
        :key="`${queue}:${segment}:${groupByCustomer}:${normalizedSearch}:${workFilter}`"
        :pages="queuePages" :phases="queuePhases" :columns="queueColumns" :busy="queueBusy" :errors="queueErrors"
        :segment="segment" :moving-order-ids="waiting.busyOrderId.value ? [...movingOrderIds, waiting.busyOrderId.value] : movingOrderIds" :compact="queue === 'history' && !normalizedSearch && workFilter !== 'followup'"
        :show-queue="Boolean(normalizedSearch) || workFilter === 'followup'"
        :list-mode="view === 'list'" :sort="sort" :selected-order-ids="selectedOrderIds" :customer-aliases="customerAliases"
        @update:sort="sort = $event" @toggle-select="toggleOrderSelection" @toggle-select-many="toggleManySelection" @rename-customer="renameCustomerGroup"
        @more="queueData.more" @phase="queueData.setPhase" @open="openOrder" @generate="onGenerateDoc"
        @waiting="toggleOrderWaiting" @move="onMoveOrder" @cancel-order="onCancelOrder" @close-debt="onCloseDebt" @rename-order="renameOrderTitle"
      />
    </div>

    <OrderWaitingDialog :order="waiting.selected.value" :busy="waiting.busy.value" :error="waiting.error.value" :stale="waiting.stale.value" @submit="waiting.submit" @refresh="waiting.refresh" @close="waiting.close" />
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

<style scoped>
.orders-queue-page { flex:1; min-height:0; overflow:hidden; }
.orders-queue-inner { display:flex; height:100%; min-height:0; flex-direction:column; }
.orders-queue-inner > header, .orders-queue-inner > nav { flex-shrink:0; }
@media (max-width:767px) {
  .orders-queue-page { flex:none; overflow:visible; }
  .orders-queue-inner { height:auto; }
}
</style>
