import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getOrderDetail: vi.fn(),
  getOrders: vi.fn(),
  login: vi.fn(),
  readMe: vi.fn(),
  listStorefronts: vi.fn(),
}));

vi.mock('../src/api', () => ({
  api: {
    getManagerOrderDetail: mocks.getOrderDetail,
    getManagerOrders: mocks.getOrders,
  },
}));

vi.mock('../src/client', () => ({
  OpenAPI: {
    BASE: '',
    VERSION: '0.1.0',
    WITH_CREDENTIALS: true,
    CREDENTIALS: 'include',
  },
  LoginService: {
    loginAccessToken: mocks.login,
    loginTelegram: vi.fn(),
  },
  ManagerService: {
    readUserMe: mocks.readMe,
    listManagerStorefronts: mocks.listStorefronts,
  },
  ManagerOrdersService: {},
}));

vi.mock('../src/components/orders/OrdersTabSwitcher.vue', () => ({
  default: { name: 'OrdersTabSwitcher', template: '<div />' },
}));
vi.mock('../src/components/orders/OrdersViewToggle.vue', () => ({
  default: { name: 'OrdersViewToggle', template: '<div />' },
}));
vi.mock('../src/components/orders/OrderKanbanBoard.vue', () => ({
  default: {
    name: 'OrderKanbanBoard',
    props: ['groupedItems', 'segment', 'movingOrderIds'],
    template: '<div />',
  },
}));
vi.mock('../src/components/orders/OrdersListTable.vue', () => ({
  default: {
    name: 'OrdersListTable',
    props: ['items', 'segment', 'sort', 'selectedOrderIds'],
    emits: ['update:sort', 'open', 'toggle-select', 'toggle-select-many'],
    template: '<div data-testid="orders-list" />',
  },
}));
vi.mock('../src/components/orders/OrderEditDrawer.vue', () => ({
  default: {
    name: 'OrderEditDrawer',
    props: ['modelValue', 'order', 'serverErrors', 'formError', 'saving'],
    emits: ['update:modelValue', 'save', 'updated', 'deleted', 'reload'],
    template: '<div data-testid="order-drawer" />',
  },
}));
vi.mock('../src/components/orders/OrdersImportPreviewModal.vue', () => ({
  default: { name: 'OrdersImportPreviewModal', template: '<div />' },
}));

import OrdersDashboard from '../src/components/orders/OrdersDashboard.vue';
import { clearManagerSession, managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';

let wrapper: VueWrapper | null = null;

const oldOrder = {
  id: 77,
  status: 'new_lead',
  title: 'Старая сделка',
  created_at: '2026-07-31T10:00:00Z',
  total_amount: 1200,
  total_cost: 800,
  margin: 400,
  is_paid: false,
  is_on_hold: false,
  needs_attention: false,
  awaiting_measurement: false,
  client_thinking: false,
  ready_for_execution: false,
};

const oldOrdersResponse = {
  items: [oldOrder],
  meta: { page: 1, limit: 100, total: 1, pages: 1 },
};

const newAuth = {
  username: 'new-manager',
  status: 'authenticated',
  staff_user_id: 20,
  role: 'manager',
  tenant_id: 2,
  storefront_id: 22,
};

const newStorefronts = {
  items: [{
    slug: 'minsk',
    display_name: 'MVN Минск',
    city: 'Минск',
    default_locale: 'ru-BY',
    currency: 'BYN',
    is_default: true,
    is_current: true,
  }],
};

const enterRecoveryWithOldState = async () => {
  const reloadPage = vi.fn();
  mocks.getOrders
    .mockResolvedValueOnce(oldOrdersResponse)
    .mockRejectedValueOnce({ status: 401 });
  mocks.getOrderDetail.mockResolvedValue({ ...oldOrder });

  wrapper = mount(OrdersDashboard, { props: { reloadPage } });
  await flushPromises();

  const list = wrapper.getComponent({ name: 'OrdersListTable' });
  list.vm.$emit('toggle-select', { orderId: oldOrder.id, selected: true });
  list.vm.$emit('open', oldOrder.id);
  await flushPromises();

  const drawer = wrapper.getComponent({ name: 'OrderEditDrawer' });
  expect(list.props('items')).toHaveLength(1);
  expect(list.props('selectedOrderIds')).toEqual([oldOrder.id]);
  expect(drawer.props('modelValue')).toBe(true);
  expect(drawer.props('order')).toMatchObject({ id: oldOrder.id });
  expect(new URL(window.location.href).searchParams.get('orderId')).toBe(String(oldOrder.id));

  list.vm.$emit('update:sort', 'margin_desc');
  await flushPromises();

  expect(mocks.getOrders).toHaveBeenCalledTimes(2);
  expect(list.props('items')).toEqual([]);
  expect(list.props('selectedOrderIds')).toEqual([]);
  expect(drawer.props('modelValue')).toBe(false);
  expect(drawer.props('order')).toBeNull();
  expect(new URL(window.location.href).searchParams.has('orderId')).toBe(false);
  expect(managerSession.isAuthenticated.value).toBe(false);
  expect(managerSession.currentUserRole.value).toBe('');
  expect(managerSession.auth.value).toBeNull();
  expect(managerSession.recoveryRequired.value).toBe(true);
  expect(managerStorefrontSelection.selectedSlug.value).toBeNull();
  expect(wrapper.get('[role="dialog"]').text()).toContain('Сессия завершилась');

  return reloadPage;
};

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem('manager_orders_view', 'list');
  window.localStorage.setItem('manager_orders_group_by_customer_v2', 'false');
  window.history.replaceState({}, '', '/manager/orders');
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  managerSession.isAuthenticated.value = true;
  managerSession.currentUserRole.value = 'owner';
  managerSession.auth.value = {
    username: 'old-owner',
    status: 'authenticated',
    staff_user_id: 10,
    role: 'owner',
    tenant_id: 1,
    storefront_id: 11,
  };
  managerSession.recoveryRequired.value = false;
  managerStorefrontSelection.selectedSlug.value = 'old-city';
});

afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
  clearManagerSession();
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe('OrdersDashboard session recovery', () => {
  it('clears the previous identity immediately and reloads once after successful login', async () => {
    const reloadPage = await enterRecoveryWithOldState();
    mocks.login.mockImplementation(async () => {
      expect(managerSession.isAuthenticated.value).toBe(false);
      expect(managerSession.auth.value).toBeNull();
      expect(managerSession.currentUserRole.value).toBe('');
      expect(managerStorefrontSelection.selectedSlug.value).toBeNull();
      return { access_token: 'new-session', token_type: 'bearer' };
    });
    mocks.readMe.mockResolvedValue(newAuth);
    mocks.listStorefronts.mockResolvedValue(newStorefronts);

    await wrapper!.get('input[placeholder="Логин"]').setValue('new-manager');
    await wrapper!.get('input[placeholder="Пароль"]').setValue('new-password');
    await wrapper!.get('form').trigger('submit');
    await flushPromises();

    expect(mocks.login).toHaveBeenCalledWith({
      username: 'new-manager',
      password: 'new-password',
    });
    expect(mocks.readMe).toHaveBeenCalledTimes(1);
    expect(mocks.listStorefronts).toHaveBeenCalledTimes(1);
    expect(mocks.getOrders).toHaveBeenCalledTimes(2);
    expect(reloadPage).toHaveBeenCalledTimes(1);
    expect(managerSession.isAuthenticated.value).toBe(true);
    expect(managerSession.currentUserRole.value).toBe('manager');
    expect(managerSession.auth.value?.username).toBe('new-manager');
    expect(managerStorefrontSelection.selectedSlug.value).toBe('minsk');
    expect(wrapper!.get('[role="dialog"]').text()).toContain('Входим...');

    wrapper!.getComponent({ name: 'OrdersListTable' }).vm.$emit('update:sort', 'created_at_asc');
    await flushPromises();
    expect(mocks.getOrders).toHaveBeenCalledTimes(2);
  });

  it('keeps a clean blocking recovery state when login is rejected', async () => {
    const reloadPage = await enterRecoveryWithOldState();
    mocks.login.mockRejectedValue({ status: 401 });

    await wrapper!.get('input[placeholder="Логин"]').setValue('old-owner');
    await wrapper!.get('input[placeholder="Пароль"]').setValue('wrong-password');
    await wrapper!.get('form').trigger('submit');
    await flushPromises();

    expect(reloadPage).not.toHaveBeenCalled();
    expect(mocks.readMe).not.toHaveBeenCalled();
    expect(mocks.listStorefronts).not.toHaveBeenCalled();
    expect(mocks.getOrders).toHaveBeenCalledTimes(2);
    expect(managerSession.isAuthenticated.value).toBe(false);
    expect(managerSession.currentUserRole.value).toBe('');
    expect(managerSession.auth.value).toBeNull();
    expect(managerSession.recoveryRequired.value).toBe(true);
    expect(managerStorefrontSelection.selectedSlug.value).toBeNull();
    expect(wrapper!.get('[role="dialog"]').text()).toContain('Неверный логин или пароль');
    expect(wrapper!.getComponent({ name: 'OrdersListTable' }).props('items')).toEqual([]);
    expect(wrapper!.getComponent({ name: 'OrderEditDrawer' }).props('order')).toBeNull();
  });
});
