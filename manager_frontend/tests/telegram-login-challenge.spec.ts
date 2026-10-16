import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ startLogin: vi.fn(), loginStatus: vi.fn(), completeLogin: vi.fn() }));
vi.mock('../src/services/manager-telegram', async original => ({ ...await original<typeof import('../src/services/manager-telegram')>(), managerTelegramApi: mocks }));
import TelegramLoginChallenge from '../src/components/manager/TelegramLoginChallenge.vue';
const challenge = { challenge_id: 'login-proof', expires_at: new Date(Date.now() + 300_000).toISOString(), status: 'pending', deep_link: 'https://t.me/kitlane_test_bot?start=login_proof', browser_code: '12345678' };
describe('Telegram browser login', () => {
  beforeEach(() => { vi.useFakeTimers(); vi.clearAllMocks(); mocks.startLogin.mockResolvedValue(challenge); mocks.completeLogin.mockResolvedValue({}); });
  afterEach(() => vi.useRealTimers());
  it('shows the browser code and completes only after private bot approval', async () => {
    mocks.loginStatus.mockResolvedValueOnce({ ...challenge, status: 'approval_pending' }).mockResolvedValueOnce({ ...challenge, status: 'approved' });
    const wrapper = mount(TelegramLoginChallenge); await wrapper.get('button').trigger('click'); await flushPromises();
    expect(wrapper.get('[aria-label="Код подтверждения входа"]').text()).toBe('12345678'); expect(mocks.completeLogin).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1500); await flushPromises(); expect(mocks.completeLogin).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2000); await flushPromises(); expect(mocks.completeLogin).toHaveBeenCalledWith('login-proof'); expect(wrapper.emitted('authenticated')).toHaveLength(1); wrapper.unmount();
  });
  it.each(['denied', 'expired'])('shows %s without completing a login', async status => {
    mocks.loginStatus.mockResolvedValue({ ...challenge, status });
    const wrapper = mount(TelegramLoginChallenge); await wrapper.get('button').trigger('click'); await flushPromises(); await vi.advanceTimersByTimeAsync(1500); await flushPromises();
    expect(mocks.completeLogin).not.toHaveBeenCalled(); expect(wrapper.find('a').exists()).toBe(false); expect(wrapper.emitted('authenticated')).toBeUndefined(); wrapper.unmount();
  });
  it('cancels pending work on unmount and rejects unsafe server links', async () => {
    mocks.startLogin.mockResolvedValue({ ...challenge, deep_link: 'https://malicious.example/login' });
    const wrapper = mount(TelegramLoginChallenge); await wrapper.get('button').trigger('click'); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('некорректную ссылку'); wrapper.unmount(); await vi.advanceTimersByTimeAsync(10_000); expect(mocks.loginStatus).not.toHaveBeenCalled();
  });
});
