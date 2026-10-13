import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { nextTick } from 'vue';

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
  last_used_at: null,
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
afterEach(() => { clearManagerSession(); vi.useRealTimers(); });

describe('ChatGPT connections in Manager profile', () => {
  it('separates active connections from collapsed revoked and expired history without revoking anything', async () => {
    const active = grant();
    const revoked = { ...grant(), id: 42, revoked_at: '2020-10-01T12:34:00Z' };
    const expired = { ...grant(), id: 43, expires_at: '2020-10-01T12:34:00Z' };
    mocks.request.mockResolvedValue({ items: [revoked, active, expired], csrf_token: 'fresh' });
    const wrapper = mount(ConnectorConnections);
    await flushPromises();
    const current = wrapper.get('[data-testid="connector-active"]');
    const history = wrapper.get('[data-testid="connector-history"]');
    expect(current.text()).toContain('Активные подключения (1)');
    expect(current.find('[data-connection-id="41"]').exists()).toBe(true);
    expect(current.find('[data-connection-id="42"]').exists()).toBe(false);
    expect(history.attributes('open')).toBeUndefined();
    expect(history.get('summary').text()).toBe('История подключений (2)');
    expect(history.text()).toContain('Доступ отозван');
    expect(history.text()).toContain('Срок доступа истёк');
    expect(history.find('button').exists()).toBe(false);
    expect(mocks.request).toHaveBeenCalledTimes(1);
    expect(mocks.request.mock.calls[0][1].method).toBe('GET');
  });

  it('shows creation and actual use with time, preserving an unknown legacy timestamp', async () => {
    const known = { ...grant(), created_at: '2026-10-01T12:34:05', last_used_at: '2026-10-02T16:47:08' };
    mocks.request.mockResolvedValue({ items: [known, { ...grant(), id: 42 }], csrf_token: 'fresh' });
    const wrapper = mount(ConnectorConnections);
    await flushPromises();
    const row = wrapper.get('[data-connection-id="41"]');
    expect(row.text()).toContain('01.10.2026');
    expect(row.text()).toContain('12:34:05');
    expect(row.text()).toContain('02.10.2026');
    expect(row.text()).toContain('16:47:08');
    expect(row.get('time[datetime="2026-10-02T16:47:08"]').exists()).toBe(true);
    expect(wrapper.get('[data-connection-id="42"]').text()).toContain('Последнее использование: Данных пока нет');
  });

  it('shows an empty active section when only historical connections remain', async () => {
    mocks.request.mockResolvedValue({ items: [{ ...grant(), expires_at: '2020-10-01T00:00:00Z' }], csrf_token: 'fresh' });
    const wrapper = mount(ConnectorConnections);
    await flushPromises();
    expect(wrapper.get('[data-testid="connector-active"]').text()).toContain('Активных подключений нет');
    expect(wrapper.get('[data-testid="connector-history"]').attributes('open')).toBeUndefined();
  });

  it('moves an expired connection to history while the profile stays open without changing its access', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
    const expiring = { ...grant(), expires_at: new Date(Date.now() + 1000).toISOString() };
    mocks.request.mockResolvedValue({ items: [expiring], csrf_token: 'fresh' });
    const wrapper = mount(ConnectorConnections);
    await flushPromises();
    expect(wrapper.find('[data-testid="connector-history"]').exists()).toBe(false);
    vi.advanceTimersByTime(30_000);
    await nextTick();
    expect(wrapper.get('[data-testid="connector-active"]').text()).toContain('Активных подключений нет');
    expect(wrapper.get('[data-testid="connector-history"]').text()).toContain('Срок доступа истёк');
    expect(mocks.request).toHaveBeenCalledTimes(1);
    wrapper.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
  it('offers a short private setup guide with usable copy action', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    mocks.request.mockResolvedValue({ items: [], csrf_token: 'fresh' });
    const wrapper = mount(ConnectorConnections);
    await flushPromises();
    const guide = wrapper.get('[data-testid="connector-quickstart"]');
    expect(guide.attributes('open')).toBeDefined();
    expect(guide.text()).toContain('У каждого сотрудника своё подключение');
    await guide.get('button').trigger('click');
    await flushPromises();
    expect(writeText).toHaveBeenCalledWith('https://api.mvn.by/api/connector/mcp');
    expect(guide.text()).toContain('Адрес скопирован');
  });

  it('explains all currently issued mail and document permissions', async () => {
    mocks.request.mockResolvedValue({ items: [{ ...grant(), scopes: ['kitlane:maintenance:write', 'kitlane:catalog:write', 'kitlane:mail:read', 'kitlane:mail:drafts:write', 'kitlane:mail:send'] }], csrf_token: 'fresh' });
    const wrapper = mount(ConnectorConnections);
    await flushPromises();
    expect(wrapper.text()).toContain('Отправка писем после подтверждения в Manager');
    expect(wrapper.text()).toContain('Подбор оборудования и черновики КП и счетов');
    expect(wrapper.text()).not.toContain('kitlane:mail:send');
  });
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
    expect(wrapper.get('[data-testid="connector-active"]').text()).toContain('Активных подключений нет');
    expect(wrapper.get('[data-testid="connector-history"]').attributes('open')).toBeUndefined();
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
