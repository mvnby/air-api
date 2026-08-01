import { computed, ref } from 'vue';

import type { DashboardView, Segment } from '../../api';
import type {
  ManagerOrderDetailResponse,
  ManagerOrderImportPreviewResponse,
  ManagerOrderListItemResponse,
  ManagerOrderTransferPackage_Input,
} from '../../client';
import { managerSession } from '../../services/manager-session';
import { managerStorefrontSelection } from '../../services/manager-storefront-selection';
import {
  BOARD_COLUMNS,
  buildCustomerOrderRenderItems,
  getOrderBoardColumn,
} from './order-utils';

const ORDERS_SEGMENT_STORAGE_KEY = 'manager_orders_segment';
const ORDERS_VIEW_STORAGE_KEY = 'manager_orders_view';
const ORDERS_GROUP_BY_CUSTOMER_STORAGE_KEY = 'manager_orders_group_by_customer_v2';
const ORDERS_CUSTOMER_ALIASES_STORAGE_PREFIX = 'manager_orders_customer_aliases_v2';

const setQueryParam = (key: string, value: string) => {
  const url = new URL(window.location.href);
  if (value) url.searchParams.set(key, value);
  else url.searchParams.delete(key);
  window.history.replaceState({}, '', `${url.pathname}${url.search}`);
};

export const useOrdersDashboardModel = (notify: (message: string) => void) => {
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
  const isHydrated = ref(false);

  const drawerOpen = ref(false);
  const selectedOrder = ref<ManagerOrderDetailResponse | null>(null);
  const pendingOpenOrderId = ref<number | null>(null);
  const openedByUrlOrderId = ref<number | null>(null);
  const orderServerErrors = ref<Record<string, string>>({});
  const orderFormError = ref('');

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

  const visibleOrders = computed(() => orders.value.filter((order) => (
    !hideOnHold.value || !order.is_on_hold
  )));
  const normalizedSearch = computed(() => search.value.trim());
  const hasActiveOrderFilters = computed(() => Boolean(
    normalizedSearch.value || statusFilter.value || overdueOnly.value,
  ));
  const groupedOrders = computed(() => {
    const groups: Record<string, ManagerOrderListItemResponse[]> = {};
    for (const column of BOARD_COLUMNS) groups[column.value] = [];
    for (const order of visibleOrders.value) {
      const key = getOrderBoardColumn(order);
      if (!groups[key]) groups[key] = [];
      groups[key].push(order);
    }
    return groups;
  });
  const groupedOrderItems = computed(() => {
    const items: Record<string, ReturnType<typeof buildCustomerOrderRenderItems>> = {};
    for (const column of BOARD_COLUMNS) {
      items[column.value] = buildCustomerOrderRenderItems(
        groupedOrders.value[column.value] || [],
        segment.value,
        groupByCustomer.value,
        customerAliases.value,
      );
    }
    return items;
  });
  const listItems = computed(() => buildCustomerOrderRenderItems(
    visibleOrders.value,
    segment.value,
    groupByCustomer.value,
    customerAliases.value,
  ));
  const visibleOrderIds = computed(() => visibleOrders.value.map((order) => order.id));

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
    selectedOrderIds.value = Array.from(new Set([
      ...selectedOrderIds.value,
      ...visibleOrderIds.value,
    ]));
  };
  const clearSelection = () => {
    selectedOrderIds.value = [];
  };

  const restorePreferences = () => {
    const params = new URLSearchParams(window.location.search);
    const resolvedSegment = params.get('segment')
      || window.localStorage.getItem(ORDERS_SEGMENT_STORAGE_KEY);
    const resolvedView = params.get('view')
      || window.localStorage.getItem(ORDERS_VIEW_STORAGE_KEY);
    const groupByFromUrl = params.get('groupBy');
    const groupByFromStorage = window.localStorage.getItem(ORDERS_GROUP_BY_CUSTOMER_STORAGE_KEY);

    if (resolvedSegment === 'all' || resolvedSegment === 'b2b' || resolvedSegment === 'b2c') {
      segment.value = resolvedSegment;
    }
    if (resolvedView === 'kanban' || resolvedView === 'list') view.value = resolvedView;
    if (groupByFromUrl === 'customer') groupByCustomer.value = true;
    else if (!groupByFromUrl && groupByFromStorage === 'false') groupByCustomer.value = false;
  };
  const persistSegmentAndView = () => {
    window.localStorage.setItem(ORDERS_SEGMENT_STORAGE_KEY, segment.value);
    window.localStorage.setItem(ORDERS_VIEW_STORAGE_KEY, view.value);
    setQueryParam('segment', segment.value);
    setQueryParam('view', view.value);
  };
  const persistGrouping = () => {
    window.localStorage.setItem(
      ORDERS_GROUP_BY_CUSTOMER_STORAGE_KEY,
      groupByCustomer.value ? 'true' : 'false',
    );
    setQueryParam('groupBy', groupByCustomer.value ? 'customer' : '');
  };

  const customerAliasesStorageKey = (): string | null => {
    const auth = managerSession.auth.value;
    if (!auth) return null;
    const userKey = auth.staff_user_id || auth.username;
    const storefrontKey = managerStorefrontSelection.selectedSlug.value
      || `storefront-${auth.storefront_id}`;
    return [
      ORDERS_CUSTOMER_ALIASES_STORAGE_PREFIX,
      auth.tenant_id,
      encodeURIComponent(storefrontKey),
      encodeURIComponent(String(userKey)),
    ].join(':');
  };
  const restoreCustomerAliases = () => {
    try {
      const key = customerAliasesStorageKey();
      const raw = key ? window.localStorage.getItem(key) : null;
      customerAliases.value = raw ? JSON.parse(raw) : {};
    } catch {
      customerAliases.value = {};
    }
  };
  const persistCustomerAliases = () => {
    const key = customerAliasesStorageKey();
    if (key) window.localStorage.setItem(key, JSON.stringify(customerAliases.value));
  };
  const renameCustomerGroup = (payload: { customerId: number; alias: string | null }) => {
    const next = { ...customerAliases.value };
    if (payload.alias) next[payload.customerId] = payload.alias;
    else delete next[payload.customerId];
    customerAliases.value = next;
    persistCustomerAliases();
    notify(payload.alias ? 'Название группы сохранено' : 'Название группы сброшено');
  };

  const clearOrderIdFromUrl = () => {
    const url = new URL(window.location.href);
    if (!url.searchParams.has('orderId')) return;
    url.searchParams.delete('orderId');
    window.history.replaceState({}, '', `${url.pathname}${url.search}`);
  };
  const clearIdentityScopedState = () => {
    orders.value = [];
    movingOrderIds.value = [];
    selectedOrderIds.value = [];
    drawerOpen.value = false;
    selectedOrder.value = null;
    pendingOpenOrderId.value = null;
    openedByUrlOrderId.value = null;
    orderServerErrors.value = {};
    orderFormError.value = '';
    customerAliases.value = {};
    search.value = '';
    loading.value = false;
    saving.value = false;
    transferLoading.value = false;
    importPackage.value = null;
    importPreview.value = null;
    importFileName.value = '';
    importModalOpen.value = false;
    if (importFileInput.value) importFileInput.value.value = '';
    clearOrderIdFromUrl();
  };

  return {
    segment, view, statusFilter, overdueOnly, sort, search, loading, saving, orders,
    movingOrderIds, isHydrated, drawerOpen, selectedOrder, pendingOpenOrderId,
    openedByUrlOrderId, orderServerErrors, orderFormError, hideOnHold,
    groupByCustomer, filtersOpen, customerAliases, selectedOrderIds, transferLoading,
    importFileInput, importPackage, importPreview, importFileName, importModalOpen,
    normalizedSearch, hasActiveOrderFilters, groupedOrderItems, listItems, visibleOrderIds,
    setQueryParam, restorePreferences, persistSegmentAndView, persistGrouping,
    restoreCustomerAliases, renameCustomerGroup, toggleOrderSelection,
    toggleManySelection, selectAllVisible, clearSelection, clearOrderIdFromUrl,
    clearIdentityScopedState,
  };
};
