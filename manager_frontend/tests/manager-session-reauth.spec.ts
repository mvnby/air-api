import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getOrderDetail: vi.fn(),
  getOrders: vi.fn(),
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
  LoginService: {},
  ManagerService: {},
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

describe('OrdersDashboard local session cleanup', () => {
  it('clears loaded, selected and opened order state immediately after list 401', async () => {
    mocks.getOrders
      .mockResolvedValueOnce({
        items: [oldOrder],
        meta: { page: 1, limit: 100, total: 1, pages: 1 },
      })
      .mockRejectedValueOnce({ status: 401 });
    mocks.getOrderDetail.mockResolvedValue({ ...oldOrder });

    wrapper = mount(OrdersDashboard);
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

    list.vm.$emit('update:sort', 'margin_desc');
    await flushPromises();

    expect(mocks.getOrders).toHaveBeenCalledTimes(2);
    expect(list.props('items')).toEqual([]);
    expect(list.props('selectedOrderIds')).toEqual([]);
    expect(drawer.props('modelValue')).toBe(false);
    expect(drawer.props('order')).toBeNull();
    expect(managerSession.isAuthenticated.value).toBe(false);
    expect(managerSession.auth.value).toBeNull();
    expect(managerSession.recoveryRequired.value).toBe(true);
    expect(managerStorefrontSelection.selectedSlug.value).toBeNull();
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);

    list.vm.$emit('update:sort', 'created_at_asc');
    await flushPromises();
    expect(mocks.getOrders).toHaveBeenCalledTimes(2);
  });
});
