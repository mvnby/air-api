import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('../src/client/core/request', () => ({ request: mocks.request }));
vi.mock('../src/client', () => ({ ManagerService: { changeManagerAccountPassword: vi.fn() } }));

import ConnectorConnections from '../src/components/ConnectorConnections.vue';
import ProfileSecurityView from '../src/views/ProfileSecurityView.vue';
import { clearManagerSession, managerSession } from '../src/services/manager-session';

const grant = () => ({
  id: 41, client_id: 'kitlane-chatgpt', tenant_id: 2, storefront_id: 3,
  scopes: ['kitlane:read', 'kitlane:incoming:write'],
  created_at: new Date().toISOString(), expires_at: new Date(Date.now() + 86400000).toISOString(), revoked_at: null,
});

enableAutoUnmount(afterEach);

beforeEach(() => {
  vi.clearAllMocks();
  mocks.request.mockResolvedValue({ items: [grant()], csrf_token: 'fresh-session-csrf' });
  managerSession.isAuthenticated.value = true;
  managerSession.auth.value = {
    username: 'manager', status: 'authenticated', staff_user_id: 7, role: 'manager',
    tenant_id: 2, storefront_id: 3, capabilities: [], can_change_password: true,
  };
});
afterEach(() => clearManagerSession());

describe('ChatGPT connections in Manager profile', () => {
  it('is reachable by an ordinary named manager through the existing profile', async () => {
    const wrapper = mount(ProfileSecurityView);
    await flushPromises();
    expect(wrapper.get('[data-testid="connector-connections"]').text()).toContain('Добавление входящих');
    expect(mocks.request.mock.calls[0][1]).toEqual({ method: 'GET', url: '/api/manager/connector/grants' });
  });

  it('hides connector grants for the legacy shared account', async () => {
    managerSession.auth.value = { ...managerSession.auth.value!, auth_source: 'legacy' };
    const wrapper = mount(ProfileSecurityView);
    await flushPromises();
    expect(wrapper.find('[data-testid="connector-connections"]').exists()).toBe(false);
    expect(mocks.request).not.toHaveBeenCalled();
  });

  it('revokes with a fresh session CSRF nonce and removes the active action', async () => {
    const wrapper = mount(ConnectorConnections);
    await flushPromises();
    await wrapper.get('[data-grant-id="41"]').trigger('click');
    await flushPromises();

    expect(mocks.request).toHaveBeenCalledTimes(3);
    expect(mocks.request.mock.calls[1][1].method).toBe('GET');
    expect(mocks.request.mock.calls[2][1]).toEqual({
      method: 'POST', url: '/api/manager/connector/grants/41/revoke', headers: { 'X-CSRF-Token': 'fresh-session-csrf' },
    });
    expect(wrapper.text()).toContain('Доступ отозван');
    expect(wrapper.find('[data-grant-id="41"]').exists()).toBe(false);
  });

  it('keeps access visible after a failed revoke and allows another attempt', async () => {
    const wrapper = mount(ConnectorConnections);
    await flushPromises();
    mocks.request.mockImplementation((_config, options) => options.method === 'POST'
      ? Promise.reject(new Error('network'))
      : Promise.resolve({ items: [grant()], csrf_token: 'fresh' }));
    await wrapper.get('[data-grant-id="41"]').trigger('click');
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain('Доступ ещё действует');
    expect(wrapper.get('[data-grant-id="41"]').attributes('disabled')).toBeUndefined();
    expect(wrapper.text()).not.toContain('Доступ отозван');
  });

  it('offers retry when listing connections fails', async () => {
    mocks.request.mockRejectedValueOnce(new Error('network'));
    const wrapper = mount(ConnectorConnections);
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить');
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    expect(wrapper.get('[data-grant-id="41"]').text()).toBe('Отключить');
  });
});
