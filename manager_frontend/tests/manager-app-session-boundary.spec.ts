import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { computed, effectScope, ref } from 'vue';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getLeadsCounter: vi.fn(),
  getLeadsInbox: vi.fn(),
  getManagerOrderDetail: vi.fn(),
  getManagerOrders: vi.fn(),
  getWebRebuildStatus: vi.fn(),
  listStorefronts: vi.fn(),
  companies: vi.fn(),
  sites: vi.fn(),
  login: vi.fn(),
  loginTelegram: vi.fn(),
  logout: vi.fn(),
  patchManagerOrder: vi.fn(),
  readMe: vi.fn(),
  resumeConnectorLogin: vi.fn(),
}));

vi.mock('../src/services/connector-login-continuation', async importOriginal => ({
  ...await importOriginal<typeof import('../src/services/connector-login-continuation')>(),
  resumeConnectorLogin: mocks.resumeConnectorLogin,
}));

vi.mock('../src/services/manager-companies', () => ({ managerCompaniesApi: { choices: mocks.companies, sites: mocks.sites } }));

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
    logoutAccessToken: mocks.logout,
  },
  ManagerMailService: {},
  ManagerOrdersService: { patchManagerOrder: mocks.patchManagerOrder },
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

vi.mock('../src/views/SupplierFeedsView.vue', () => ({
  __esModule: true,
  default: {
    name: 'SupplierFeedsView',
    props: ['initialTab'],
    template: '<div data-testid="supplier-entry">{{ initialTab }}</div>',
  },
}));

import App from '../src/App.vue';
import { managerProfileApi } from '../src/services/manager-profile';
import { managerInvitationsApi } from '../src/services/manager-invitations';
import { useOrderDrawerSaving } from '../src/composables/useOrderDrawerSaving';
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
  capabilities: ['crm.manage', 'catalog.master.read', 'storefront.offers.read', 'storefront.collections.manage', 'platform.manage', 'staff.manage', 'infrastructure.manage'],
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
  capabilities: ['crm.manage', 'catalog.master.read', 'storefront.offers.read', 'storefront.collections.manage'],
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

const companyChoices = (auth: typeof oldAuth, sites: typeof oldStorefronts) => ({ ...auth, default_tenant_id: auth.tenant_id, items: [{ tenant_id: auth.tenant_id, slug: 'company', display_name: 'Компания', role: auth.role, membership_id: 1, access_kind: 'membership', is_system: auth.is_system_tenant, demo_read_only: false, default_storefront_slug: sites.items[0]!.slug }], total: 1, page: 1, limit: 100 });
const companySites = (sites: typeof oldStorefronts) => ({ items: sites.items.map(site => ({ ...site, id: 1, status: 'active', domains: [] })) });

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
    global: { stubs: { UiFeedbackHost: true, ProfileSecurityView: true } },
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
  const archiveButton = wrapper!.findAll('button').find((button) => button.attributes('aria-label') === 'Архив');
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
  window.sessionStorage.clear();
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  networkFetch.mockImplementation(async () => okResponse());
  mocks.login.mockResolvedValue({ access_token: 'session', token_type: 'bearer' });
  mocks.resumeConnectorLogin.mockReturnValue(true);
  mocks.loginTelegram.mockResolvedValue({ access_token: 'session', token_type: 'bearer' });
  mocks.logout.mockResolvedValue(undefined);
  vi.spyOn(managerProfileApi, 'get').mockResolvedValue({ staff_user_id: 10, display_name: 'Old owner', username: 'old-owner', can_change_password: true, must_change_password: false, personal_read_only: false } as never);
  mocks.companies.mockResolvedValue(companyChoices(oldAuth, oldStorefronts));
  mocks.sites.mockResolvedValue(companySites(oldStorefronts));
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
  it('separates a current catalog from the last failed verification without exposing its technical error', async () => {
    mocks.getWebRebuildStatus.mockResolvedValue({
      current_revision: 4,
      current_revision_updated_at: '2026-09-12T08:00:00Z',
      published_revision: 4,
      needs_rebuild: false,
      state: 'idle',
      last_error: 'Standalone SSR catalog sync verification failed',
    });

    await mountApp();

    expect(wrapper!.text()).toContain('Каталог актуален');
    expect(wrapper!.text()).toContain('Каталог сайта соответствует текущей ревизии.');
    expect(wrapper!.text()).toContain('Последняя проверка завершилась ошибкой.');
    expect(wrapper!.text()).not.toContain('Standalone SSR catalog sync verification failed');
    expect(wrapper!.get('button[aria-label="Проверить сайт"]').exists()).toBe(true);
  });

  it('explains stale and queued catalog synchronization states in business terms', async () => {
    mocks.getWebRebuildStatus.mockResolvedValue({
      current_revision: 5,
      current_revision_updated_at: '2026-09-12T08:00:00Z',
      published_revision: 4,
      needs_rebuild: true,
      state: 'idle',
    });

    await mountApp();

    expect(wrapper!.text()).toContain('Каталог требует синхронизации');
    expect(wrapper!.text()).toContain('Каталог сайта не соответствует текущей ревизии. Нужна синхронизация.');
    expect(wrapper!.get('button[aria-label="Обновить сайт"]').exists()).toBe(true);

    wrapper!.unmount();
    wrapper = null;
    clearManagerSession();
    mocks.getWebRebuildStatus.mockResolvedValue({
      current_revision: 5,
      current_revision_updated_at: '2026-09-12T08:00:00Z',
      published_revision: 4,
      needs_rebuild: true,
      state: 'queued',
    });

    await mountApp();

    expect(wrapper!.text()).toContain('Проверка каталога запущена');
    expect(wrapper!.text()).toContain('Проверяем, соответствует ли каталог сайта текущей ревизии.');
  });

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
    // Persistence now belongs to the drawer, rather than a dashboard save event.
    const saveScope = effectScope();
    const title = ref('Старое имя');
    const savedFormSnapshot = ref(title.value);
    const persistence = saveScope.run(() => useOrderDrawerSaving({
      order: ref(oldOrder as any),
      ready: computed(() => managerSession.isAuthenticated.value),
      activeProposalId: ref(null), activeProposalLocked: ref(false), productLines: ref([]),
      currentFormSnapshot: () => title.value,
      currentLinesSnapshot: () => '{}',
      savedFormSnapshot, savedLinesSnapshot: ref('{}'),
      hasUnsavedChanges: computed(() => title.value !== savedFormSnapshot.value),
      buildSavePayload: () => ({ title: title.value }),
      hydrateOrder: vi.fn(), localFormError: ref(''), localServerErrors: ref({}),
      clearDraft: vi.fn(), onUpdated: vi.fn(),
    }))!;
    persistence.resetBaseline();
    title.value = 'Новое имя';
    expect(await persistence.flush()).toBe(false);
    saveScope.stop();
    await flushPromises();

    expect(managerSession.recoveryRequired.value).toBe(true);
    expect(wrapper!.find('[data-testid="manager-root"]').exists()).toBe(false);
    expect(wrapper!.find('[data-testid="order-drawer"]').exists()).toBe(false);
  });

  it('keeps recovery blocking and reloads exactly once after nested login', async () => {
    const reloadPage = await mountApp();
    networkFetch.mockImplementation(async () => unauthorizedResponse());
    await expireFromLeadInbox();

    mocks.companies.mockResolvedValue(companyChoices(newAuth, newStorefronts));
    mocks.sites.mockResolvedValue(companySites(newStorefronts));
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

  it('ends the visible manager session before returning to the ordinary login flow', async () => {
    await mountApp();
    expect(wrapper!.find('[data-testid="manager-root"]').exists()).toBe(true);

    await wrapper!.get('[data-testid="manager-logout"]').trigger('click');
    await flushPromises();

    expect(mocks.logout).toHaveBeenCalledTimes(1);
    expect(managerSession.isAuthenticated.value).toBe(false);
    expect(managerSession.auth.value).toBeNull();
    expect(managerSession.recoveryRequired.value).toBe(false);
    expect(managerStorefrontSelection.selectedSlug.value).toBeNull();
    expect(wrapper!.find('[data-testid="manager-root"]').exists()).toBe(false);
    expect(wrapper!.get('[role="dialog"]').text()).toContain('Вход в менеджер');
  });

  it('keeps the manager session mounted if the server cannot clear its cookie', async () => {
    await mountApp();
    mocks.logout.mockRejectedValueOnce({ status: 503, message: 'Unavailable' });

    await wrapper!.get('[data-testid="manager-logout"]').trigger('click');
    await flushPromises();

    expect(mocks.logout).toHaveBeenCalledTimes(1);
    expect(managerSession.isAuthenticated.value).toBe(true);
    expect(managerSession.auth.value?.username).toBe('old-owner');
    expect(wrapper!.find('[data-testid="manager-root"]').exists()).toBe(true);
    expect(wrapper!.find('[role="dialog"]').exists()).toBe(false);
  });
});

describe('supplier navigation entry points', () => {
  it('opens prices separately from the supplier profile and highlights only that entry', async () => {
    await mountApp('/manager/suppliers');
    expect(wrapper!.get('[data-testid="supplier-entry"]').text()).toBe('profile');
    const prices = wrapper!.findAll('button').find(button => button.attributes('aria-label') === 'Прайсы поставщиков');
    expect(prices).toBeDefined();
    await prices!.trigger('click');
    await flushPromises();
    expect(window.location.pathname).toBe('/manager/suppliers/prices');
    expect(wrapper!.get('[data-testid="supplier-entry"]').text()).toBe('prices');
    expect(wrapper!.findAll('[aria-current="page"]').map(button => button.attributes('aria-label'))).toEqual(['Прайсы поставщиков']);
    const suppliers = wrapper!.findAll('button').find(button => button.attributes('aria-label') === 'Поставщики');
    await suppliers!.trigger('click');
    await flushPromises();
    expect(wrapper!.get('[data-testid="supplier-entry"]').text()).toBe('profile');
  });
});

describe('personal connector login continuation', () => {
  const target = '/api/connector/oauth/authorize?' + new URLSearchParams({
    client_id: 'kitlane-chatgpt', state: 'resume-test', code_challenge: 'challenge',
    code_challenge_method: 'S256', response_type: 'code',
  });
  const path = '/manager/?' + new URLSearchParams({ connector_return: target });

  it('resumes a restored named session without a manual page refresh', async () => {
    await mountApp(path);
    expect(mocks.resumeConnectorLogin).toHaveBeenCalledWith(target, expect.objectContaining({ username: oldAuth.username, tenant_id: oldAuth.tenant_id, can_change_password: true, must_change_password: false }));
  });

  it('shows the connection purpose and resumes after password login', async () => {
    mocks.readMe.mockRejectedValueOnce(new Error('unauthorized'));
    await mountApp(path);
    expect(wrapper!.get('[role="dialog"]').text()).toContain('Вход для подключения ChatGPT');
    await wrapper!.get('#manager-login-username').setValue('old-owner');
    await wrapper!.get('#manager-login-password').setValue('local-test-password');
    await wrapper!.get('form').trigger('submit');
    await flushPromises();
    expect(mocks.login).toHaveBeenCalledWith({ username: 'old-owner', password: 'local-test-password' });
    expect(mocks.resumeConnectorLogin).toHaveBeenCalledWith(target, expect.objectContaining({ username: oldAuth.username, tenant_id: oldAuth.tenant_id, can_change_password: true, must_change_password: false }));
  });

  it('asks a legacy shared account to use a personal login', async () => {
    mocks.readMe.mockResolvedValue({ ...oldAuth, staff_user_id: undefined, auth_source: 'legacy' });
    await mountApp(path);
    expect(mocks.resumeConnectorLogin).not.toHaveBeenCalled();
    expect(wrapper!.get('[role="dialog"]').text()).toContain('ваш личный логин Kitlane');
  });

  it('opens the profile before connecting an account with a temporary password', async () => {
    mocks.readMe.mockResolvedValue({ ...oldAuth, must_change_password: false });
    vi.mocked(managerProfileApi.get).mockResolvedValue({ staff_user_id: 10, must_change_password: true, can_change_password: true, personal_read_only: false } as never);
    await mountApp(path);
    await flushPromises();
    expect(mocks.resumeConnectorLogin).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe('/manager/profile');
  });
});


describe('company bootstrap and public invitation boundary', () => {
  it('does not mount orders or call /me before company discovery finishes', async () => {
    let resolve: ((value: unknown) => void) | undefined;
    mocks.companies.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    await mountApp('/manager/orders?company=1&site=old-city');
    expect(mocks.readMe).not.toHaveBeenCalled(); expect(mocks.getManagerOrders).not.toHaveBeenCalled(); expect(wrapper!.find('[data-testid="manager-root"]').exists()).toBe(false);
    resolve!(companyChoices(oldAuth, oldStorefronts)); await flushPromises(); await flushPromises();
    expect(mocks.readMe).toHaveBeenCalledOnce(); expect(managerSession.isAuthenticated.value).toBe(true);
  });
  it('bootstraps an ordinary manager through allowed storefront discovery while restricted company sites deny access', async () => {
    mocks.companies.mockResolvedValue(companyChoices(newAuth, newStorefronts));
    mocks.sites.mockRejectedValue({ status: 403 });
    mocks.listStorefronts.mockResolvedValue(newStorefronts);
    mocks.readMe.mockImplementation(async () => {
      expect(mocks.listStorefronts).toHaveBeenCalledOnce();
      expect(managerStorefrontSelection.selectedTenantId.value).toBe(2);
      expect(managerStorefrontSelection.selectedSlug.value).toBe('minsk');
      return newAuth;
    });
    await mountApp('/manager/orders?company=2&site=minsk');
    expect(mocks.sites).not.toHaveBeenCalled(); expect(mocks.getManagerOrders).toHaveBeenCalled(); expect(managerSession.isAuthenticated.value).toBe(true);
  });
  it('keeps business screens closed if /me returns a different company than the validated selection', async () => {
    mocks.readMe.mockResolvedValue(newAuth);
    await mountApp('/manager/orders?company=1&site=old-city');
    expect(wrapper!.text()).toContain('Сервер не подтвердил выбранную компанию'); expect(mocks.getManagerOrders).not.toHaveBeenCalled(); expect(managerSession.isAuthenticated.value).toBe(false);
  });
  it('denies an explicit unknown company without requesting orders or silently opening the default', async () => {
    await mountApp('/manager/orders?company=999&site=old-city');
    expect(wrapper!.text()).toContain('Компания или сайт недоступны'); expect(mocks.readMe).not.toHaveBeenCalled(); expect(mocks.getManagerOrders).not.toHaveBeenCalled(); expect(mocks.sites).not.toHaveBeenCalled();
  });
  it('removes the invite token before preview and bypasses normal company bootstrap', async () => {
    const preview = vi.spyOn(managerInvitationsApi, 'preview').mockImplementation(async token => {
      expect(token).toBe('private-token-01234567890123456789'); expect(window.location.hash).toBe('');
      return { company_name: 'Новая компания', role: 'manager', expires_at: '2099-01-01T00:00:00Z' };
    });
    const accept = vi.spyOn(managerInvitationsApi, 'accept').mockRejectedValue({ status: 409, body: { detail: 'Ссылка уже использована' } });
    mocks.companies.mockRejectedValue({ status: 403 });
    const inviteUrl = '/manager/invite#token=private-token-01234567890123456789';
    await mountApp(inviteUrl);
    expect(preview).toHaveBeenCalledOnce(); expect(wrapper!.text()).toContain('Новая компания'); expect(mocks.readMe).not.toHaveBeenCalled(); expect(mocks.getManagerOrders).not.toHaveBeenCalled(); expect(wrapper!.find('[role="dialog"]').exists()).toBe(false);
    expect(JSON.stringify(window.sessionStorage)).not.toContain('private-token'); expect(JSON.stringify(window.localStorage)).not.toContain('private-token');
    await wrapper!.get('input[value="existing_credentials"]').setValue(true);
    await wrapper!.get('input[autocomplete="username"]').setValue('maria');
    await wrapper!.get('input[type="password"]').setValue('personal-password');
    await wrapper!.get('form').trigger('submit'); await flushPromises();
    expect(accept).toHaveBeenCalledWith({ token: 'private-token-01234567890123456789', mode: 'existing_credentials', username: 'maria', password: 'personal-password' });
    preview.mockRestore(); accept.mockRestore();
  });
});
