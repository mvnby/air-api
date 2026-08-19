import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getLeadsCounter: vi.fn(),
  getLeadsInbox: vi.fn(),
  getManagerOrderDetail: vi.fn(),
  getManagerOrders: vi.fn(),
  getWebRebuildStatus: vi.fn(),
  listStorefronts: vi.fn(),
  login: vi.fn(),
  loginTelegram: vi.fn(),
  patchManagerOrder: vi.fn(),
  readMe: vi.fn(),
}));

vi.mock('../src/api', () => ({
  api: {
    getLeadsCounter: mocks.getLeadsCounter,
    getLeadsInbox: mocks.getLeadsInbox,
    getManagerOrderDetail: mocks.getManagerOrderDetail,
    getManagerOrders: mocks.getManagerOrders,
    getWebRebuildStatus: mocks.getWebRebuildStatus,
    patchManagerOrder: mocks.patchManagerOrder,
    rebuildWeb: vi.fn(),
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
    loginTelegram: mocks.loginTelegram,
  },
  ManagerMailService: {},
  ManagerOrdersService: {},
  ManagerService: {
    readUserMe: mocks.readMe,
    listManagerStorefronts: mocks.listStorefronts,
  },
}));

vi.mock('../src/components/leads/LeadInboxCard.vue', () => ({
  default: {
    name: 'LeadInboxCard',
    props: ['item'],
    template: '<article data-testid="old-tenant-lead">{{ item.request_text }}</article>',
  },
}));
vi.mock('../src/components/leads/LeadQualifyModal.vue', () => ({
  default: { name: 'LeadQualifyModal', template: '<div />' },
}));
vi.mock('../src/components/ui/AddressSuggestInput.vue', () => ({
  default: { name: 'AddressSuggestInput', template: '<div />' },
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

import App from '../src/App.vue';
import { clearManagerSession, managerSession, recoverManagerSessionFromUnauthorized } from '../src/services/manager-session';
import {
  installManagerStorefrontFetchScope,
  managerStorefrontSelection,
} from '../src/services/manager-storefront-selection';

const networkFetch = vi.fn();
const originalFetch = window.fetch;
let wrapper: VueWrapper | null = null;

const oldAuth = {
  username: 'old-owner',
  status: 'authenticated',
  staff_user_id: 10,
  role: 'owner',
  tenant_id: 1,
  storefront_id: 11,
  is_system_tenant: true,
  capabilities: ['crm.manage', 'catalog.master.read', 'storefront.offers.read', 'platform.manage', 'staff.manage', 'infrastructure.manage'],
};

const oldStorefronts = {
  items: [{
    slug: 'old-city',
    display_name: 'Старая витрина',
    city: 'Старый город',
    default_locale: 'ru-BY',
    currency: 'BYN',
    is_default: true,
    is_current: true,
  }],
};

const newAuth = {
  username: 'new-manager',
  status: 'authenticated',
  staff_user_id: 20,
  role: 'manager',
  tenant_id: 2,
  storefront_id: 22,
  is_system_tenant: false,
  capabilities: ['crm.manage', 'catalog.master.read', 'storefront.offers.read'],
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

const oldLead = {
  id: 55,
  status: 'new_lead',
  source: 'website',
  request_text: 'Лид старой витрины',
  created_at: '2026-07-31T09:00:00Z',
};

const oldLeadResponse = {
  items: [oldLead],
  total: 1,
  meta: { page: 1, limit: 100, total: 1, pages: 1 },
};

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

const okResponse = () => new Response('{}', {
  status: 200,
  headers: { 'Content-Type': 'application/json' },
});
const unauthorizedResponse = () => new Response('', { status: 401 });

const rejectedManagerRequest = async (url: string, method = 'GET') => {
  const response = await window.fetch(url, { method });
  if (response.status === 401) throw { status: 401 };
  return response;
};

const mountApp = async (path = '/manager/leads') => {
  window.history.replaceState({}, '', path);
  const reloadPage = vi.fn();
  wrapper = mount(App, {
    props: { reloadPage },
    global: { stubs: { UiFeedbackHost: true } },
  });
  await flushPromises();
  await flushPromises();
  if (managerSession.isAuthenticated.value) {
    await vi.waitFor(() => {
      expect(wrapper!.get('main').html()).not.toContain('<!---->');
    });
  }
  return reloadPage;
};

const expireFromLeadInbox = async () => {
  mocks.getLeadsInbox.mockImplementation(() => rejectedManagerRequest('/api/manager/leads/inbox'));
  const archiveButton = wrapper!.findAll('button').find((button) => button.text() === 'Архив');
  expect(archiveButton).toBeDefined();
  await archiveButton!.trigger('click');
  await flushPromises();
};

beforeAll(() => {
  window.fetch = networkFetch as unknown as typeof fetch;
  installManagerStorefrontFetchScope(window, () => {
    recoverManagerSessionFromUnauthorized();
  });
});

beforeEach(() => {
  clearManagerSession();
  window.localStorage.clear();
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  networkFetch.mockImplementation(async () => okResponse());
  mocks.login.mockResolvedValue({ access_token: 'session', token_type: 'bearer' });
  mocks.loginTelegram.mockResolvedValue({ access_token: 'session', token_type: 'bearer' });
  mocks.readMe.mockResolvedValue(oldAuth);
  mocks.listStorefronts.mockResolvedValue(oldStorefronts);
  mocks.getLeadsCounter.mockResolvedValue({ count: 7 });
  mocks.getLeadsInbox.mockResolvedValue(oldLeadResponse);
  mocks.getManagerOrders.mockResolvedValue(oldOrdersResponse);
  mocks.getManagerOrderDetail.mockResolvedValue({ ...oldOrder });
  mocks.patchManagerOrder.mockResolvedValue({ ...oldOrder });
  mocks.getWebRebuildStatus.mockResolvedValue({
    current_revision: 1,
    current_revision_updated_at: '2026-08-01T00:00:00Z',
    published_revision: 1,
    needs_rebuild: false,
    state: 'idle',
  });
});

afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
  clearManagerSession();
  window.localStorage.clear();
  vi.restoreAllMocks();
});

afterAll(() => {
  window.fetch = originalFetch;
});

describe('App Manager session boundary', () => {
  it('keeps an initial /me 401 in the ordinary login flow', async () => {
    networkFetch.mockImplementation(async () => unauthorizedResponse());
    mocks.readMe.mockImplementationOnce(async () => {
      await rejectedManagerRequest('/api/manager/me');
      return oldAuth;
    });

    await mountApp();

    expect(managerSession.isAuthenticated.value).toBe(false);
    expect(managerSession.recoveryRequired.value).toBe(false);
    expect(wrapper!.find('[data-testid="manager-root"]').exists()).toBe(false);
    expect(wrapper!.get('[role="dialog"]').text()).toContain('Вход в менеджер');
    expect(wrapper!.text()).not.toContain('Сессия завершилась');
  });

  it('unmounts old LeadInbox data and clears its shell counter after any Manager 401', async () => {
    await mountApp();
    expect(wrapper!.get('[data-testid="old-tenant-lead"]').text()).toBe('Лид старой витрины');
    expect(wrapper!.get('[data-testid="manager-leads-count"]').text()).toBe('7');

    networkFetch.mockImplementation(async () => unauthorizedResponse());
    await expireFromLeadInbox();

    expect(managerSession.recoveryRequired.value).toBe(true);
    expect(wrapper!.find('[data-testid="manager-root"]').exists()).toBe(false);
    expect(wrapper!.find('[data-testid="old-tenant-lead"]').exists()).toBe(false);
    expect(wrapper!.find('[data-testid="manager-leads-count"]').exists()).toBe(false);
    expect(wrapper!.get('[role="dialog"]').text()).toContain('Сессия завершилась');
    expect(wrapper!.text()).not.toContain('Вход в менеджер');

    networkFetch.mockImplementation(async () => okResponse());
    mocks.getLeadsInbox.mockResolvedValue(oldLeadResponse);
    managerSession.recoveryRequired.value = false;
    managerSession.isAuthenticated.value = true;
    await flushPromises();
    expect(wrapper!.find('[data-testid="manager-leads-count"]').exists()).toBe(false);
  });

  it('unmounts the Manager root when opening an order returns 401', async () => {
    window.localStorage.setItem('manager_orders_view', 'list');
    await mountApp('/manager/orders');
    const list = wrapper!.getComponent({ name: 'OrdersListTable' });
    expect(list.props('items')).toHaveLength(1);

    networkFetch.mockImplementation(async () => unauthorizedResponse());
    mocks.getManagerOrderDetail.mockImplementation(
      () => rejectedManagerRequest('/api/manager/orders/77'),
    );
    list.vm.$emit('open', oldOrder.id);
    await flushPromises();

    expect(managerSession.recoveryRequired.value).toBe(true);
    expect(wrapper!.find('[data-testid="manager-root"]').exists()).toBe(false);
    expect(wrapper!.find('[data-testid="orders-list"]').exists()).toBe(false);
  });

  it('unmounts the Manager root when saving an order returns 401', async () => {
    window.localStorage.setItem('manager_orders_view', 'list');
    await mountApp('/manager/orders');
    const list = wrapper!.getComponent({ name: 'OrdersListTable' });
    list.vm.$emit('open', oldOrder.id);
    await flushPromises();
    const drawer = wrapper!.getComponent({ name: 'OrderEditDrawer' });
    expect(drawer.props('order')).toMatchObject({ id: oldOrder.id });

    networkFetch.mockImplementation(async () => unauthorizedResponse());
    mocks.patchManagerOrder.mockImplementation(
      () => rejectedManagerRequest('/api/manager/orders/77', 'PATCH'),
    );
    drawer.vm.$emit('save', { orderId: oldOrder.id, data: { title: 'Новое имя' } });
    await flushPromises();

    expect(managerSession.recoveryRequired.value).toBe(true);
    expect(wrapper!.find('[data-testid="manager-root"]').exists()).toBe(false);
    expect(wrapper!.find('[data-testid="order-drawer"]').exists()).toBe(false);
  });

  it('keeps recovery blocking and reloads exactly once after nested login', async () => {
    const reloadPage = await mountApp();
    networkFetch.mockImplementation(async () => unauthorizedResponse());
    await expireFromLeadInbox();

    mocks.readMe.mockResolvedValue(newAuth);
    mocks.listStorefronts.mockResolvedValue(newStorefronts);
    await wrapper!.get('input[placeholder="Логин"]').setValue('new-manager');
    await wrapper!.get('input[placeholder="Пароль"]').setValue('new-password');
    await wrapper!.get('[role="dialog"] form').trigger('submit');
    await flushPromises();

    expect(reloadPage).toHaveBeenCalledTimes(1);
    expect(managerSession.isAuthenticated.value).toBe(true);
    expect(managerSession.recoveryRequired.value).toBe(true);
    expect(managerSession.auth.value?.username).toBe('new-manager');
    expect(managerStorefrontSelection.selectedSlug.value).toBe('minsk');
    expect(wrapper!.find('[data-testid="manager-root"]').exists()).toBe(false);
    expect(wrapper!.find('[data-testid="old-tenant-lead"]').exists()).toBe(false);
    expect(wrapper!.get('[role="dialog"]').text()).toContain('Входим...');

    await wrapper!.get('[role="dialog"] form').trigger('submit');
    await window.fetch('/api/manager/orders/88');
    await flushPromises();
    expect(reloadPage).toHaveBeenCalledTimes(1);
    expect(managerSession.auth.value?.username).toBe('new-manager');
  });

  it('keeps identity empty and recovery blocking after rejected nested login', async () => {
    const reloadPage = await mountApp();
    networkFetch.mockImplementation(async () => unauthorizedResponse());
    await expireFromLeadInbox();

    mocks.login.mockRejectedValue({ status: 401 });
    await wrapper!.get('input[placeholder="Логин"]').setValue('old-owner');
    await wrapper!.get('input[placeholder="Пароль"]').setValue('wrong-password');
    await wrapper!.get('[role="dialog"] form').trigger('submit');
    await flushPromises();

    expect(reloadPage).not.toHaveBeenCalled();
    expect(managerSession.isAuthenticated.value).toBe(false);
    expect(managerSession.currentUserRole.value).toBe('');
    expect(managerSession.auth.value).toBeNull();
    expect(managerSession.recoveryRequired.value).toBe(true);
    expect(managerStorefrontSelection.selectedSlug.value).toBeNull();
    expect(wrapper!.find('[data-testid="manager-root"]').exists()).toBe(false);
    expect(wrapper!.get('[role="dialog"]').text()).toContain('Неверный логин или пароль');
  });

  it('applies one recovery transition for concurrent Manager 401 responses', async () => {
    await mountApp();
    const prepareAuthentication = vi.spyOn(managerStorefrontSelection, 'prepareAuthentication');
    networkFetch.mockImplementation(async () => unauthorizedResponse());

    await Promise.all([
      window.fetch('/api/manager/orders/77'),
      window.fetch('/api/manager/leads/inbox'),
      window.fetch('/api/manager/customers'),
    ]);
    await flushPromises();

    expect(managerSession.recoveryRequired.value).toBe(true);
    expect(prepareAuthentication).toHaveBeenCalledTimes(1);
    expect(wrapper!.find('[data-testid="manager-root"]').exists()).toBe(false);
  });
});
