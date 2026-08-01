import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getOrders: vi.fn(),
  login: vi.fn(),
  readMe: vi.fn(),
  listStorefronts: vi.fn(),
}));

vi.mock('../src/api', () => ({
  api: {
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
  default: { name: 'OrderKanbanBoard', template: '<div />' },
}));
vi.mock('../src/components/orders/OrdersListTable.vue', () => ({
  default: { name: 'OrdersListTable', template: '<div />' },
}));
vi.mock('../src/components/orders/OrderEditDrawer.vue', () => ({
  default: { name: 'OrderEditDrawer', template: '<div />' },
}));

import OrdersDashboard from '../src/components/orders/OrdersDashboard.vue';
import { clearManagerSession, managerSession } from '../src/services/manager-session';
import {
  MANAGER_STOREFRONT_HEADER,
  getManagerStorefrontRequestHeaders,
  managerStorefrontSelection,
} from '../src/services/manager-storefront-selection';

let wrapper: VueWrapper | null = null;

const emptyOrders = {
  items: [],
  meta: { page: 1, limit: 100, total: 0, pages: 1 },
};

beforeEach(() => {
  window.localStorage.clear();
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
  it('drops the old storefront before re-login and applies the new identity scope and role', async () => {
    const headersSeen: Array<Record<string, string>> = [];
    mocks.getOrders
      .mockImplementationOnce(async () => {
        expect(getManagerStorefrontRequestHeaders('/api/manager/orders')).toEqual({
          [MANAGER_STOREFRONT_HEADER]: 'old-city',
        });
        throw { status: 401 };
      })
      .mockImplementationOnce(async () => {
        headersSeen.push(getManagerStorefrontRequestHeaders('/api/manager/orders'));
        return emptyOrders;
      });
    mocks.login.mockImplementation(async () => {
      expect(managerStorefrontSelection.selectedSlug.value).toBeNull();
      expect(managerSession.currentUserRole.value).toBe('');
      return { access_token: 'new-session', token_type: 'bearer' };
    });
    mocks.readMe.mockImplementation(async () => {
      expect(getManagerStorefrontRequestHeaders('/api/manager/me')).toEqual({});
      return {
        username: 'new-manager',
        status: 'authenticated',
        staff_user_id: 20,
        role: 'manager',
        tenant_id: 2,
        storefront_id: 22,
      };
    });
    mocks.listStorefronts.mockImplementation(async () => {
      expect(getManagerStorefrontRequestHeaders('/api/manager/storefronts')).toEqual({});
      return {
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
    });

    wrapper = shallowMount(OrdersDashboard);
    await flushPromises();
    expect(wrapper.get('h2').text()).toBe('Вход в Manager');

    await wrapper.get('input[placeholder="Логин"]').setValue('new-manager');
    await wrapper.get('input[placeholder="Пароль"]').setValue('new-password');
    await wrapper.get('button.btn-mini.w-full').trigger('click');
    await flushPromises();

    expect(mocks.login).toHaveBeenCalledWith({
      username: 'new-manager',
      password: 'new-password',
    });
    expect(mocks.readMe).toHaveBeenCalledTimes(1);
    expect(mocks.listStorefronts).toHaveBeenCalledTimes(1);
    expect(managerSession.currentUserRole.value).toBe('manager');
    expect(managerSession.auth.value?.username).toBe('new-manager');
    expect(managerStorefrontSelection.selectedSlug.value).toBe('minsk');
    expect(headersSeen).toEqual([{ [MANAGER_STOREFRONT_HEADER]: 'minsk' }]);
    expect(wrapper.find('h2').exists()).toBe(false);
  });
});
