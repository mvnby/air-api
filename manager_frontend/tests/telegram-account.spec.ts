import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ startLink: vi.fn(), linkStatus: vi.fn(), confirmLink: vi.fn(), disconnect: vi.fn(), profileGet: vi.fn(), profileUpdate: vi.fn(), refresh: vi.fn() }));
vi.mock('../src/services/manager-telegram', async original => ({ ...await original<typeof import('../src/services/manager-telegram')>(), managerTelegramApi: mocks }));
vi.mock('../src/services/manager-profile', () => ({ managerProfileApi: { get: mocks.profileGet, update: mocks.profileUpdate }, refreshManagerIdentity: mocks.refresh }));
import TelegramAccountPanel from '../src/components/profile/TelegramAccountPanel.vue';
import { managerSession } from '../src/services/manager-session';
const profile = { staff_user_id: 7, display_name: 'Мария', username: 'maria', phone: null, email: null, avatar_url: null, updated_at: 'v1', telegram_linked: false, telegram_username: null, telegram_notifications_enabled: false };
const challenge = { challenge_id: 'challenge-id', expires_at: new Date(Date.now() + 300_000).toISOString(), status: 'pending', deep_link: 'https://t.me/kitlane_test_bot?start=proof', telegram: null };
const button = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('button').find(item => item.text() === text)!;
describe('personal Telegram link', () => {
  beforeEach(() => { vi.useFakeTimers(); vi.clearAllMocks(); managerSession.auth.value = { can_change_password: true } as any; mocks.startLink.mockResolvedValue(challenge); mocks.profileGet.mockResolvedValue({ ...profile, telegram_linked: true }); mocks.refresh.mockResolvedValue(undefined); });
  afterEach(() => vi.useRealTimers());
  it('requires confirming exactly the bot-proven candidate before linking', async () => {
    mocks.linkStatus.mockResolvedValue({ ...challenge, status: 'claimed', telegram: { id: 123, username: 'maria', display_name: 'Мария Иванова' } });
    mocks.confirmLink.mockResolvedValue({ status: 'linked' });
    const wrapper = mount(TelegramAccountPanel, { props: { profile } });
    await button(wrapper, 'Подключить Telegram').trigger('click'); await flushPromises();
    expect(mocks.confirmLink).not.toHaveBeenCalled(); expect(wrapper.get('a').attributes('href')).toBe(challenge.deep_link);
    await vi.advanceTimersByTimeAsync(1500); await flushPromises();
    expect(wrapper.text()).toContain('Мария Иванова'); expect(wrapper.find('input[type="number"]').exists()).toBe(false);
    await button(wrapper, 'Подтвердить подключение').trigger('click'); await flushPromises();
    expect(mocks.confirmLink).toHaveBeenCalledWith('challenge-id', 123); expect(mocks.refresh).toHaveBeenCalledOnce(); expect(wrapper.emitted('updated')).toHaveLength(1); wrapper.unmount();
  });
  it('does not link an expired proof and stops polling after cancel', async () => {
    mocks.linkStatus.mockResolvedValue({ ...challenge, status: 'expired' });
    const wrapper = mount(TelegramAccountPanel, { props: { profile } });
    await button(wrapper, 'Подключить Telegram').trigger('click'); await flushPromises();
    await vi.advanceTimersByTimeAsync(1500); await flushPromises();
    expect(wrapper.text()).toContain('Время подключения истекло'); expect(mocks.confirmLink).not.toHaveBeenCalled();
    await button(wrapper, 'Начать заново').trigger('click'); await vi.advanceTimersByTimeAsync(10_000);
    expect(mocks.linkStatus).toHaveBeenCalledOnce(); wrapper.unmount();
  });
  it('updates notifications independently using the current profile version', async () => {
    mocks.profileUpdate.mockResolvedValue({ ...profile, telegram_linked: true, telegram_notifications_enabled: true });
    const wrapper = mount(TelegramAccountPanel, { props: { profile: { ...profile, telegram_linked: true } } });
    await wrapper.get('[role="switch"]').setValue(true); await flushPromises();
    expect(mocks.profileUpdate).toHaveBeenCalledWith({ telegram_notifications_enabled: true, expected_updated_at: 'v1' }); wrapper.unmount();
  });
  it('disconnects only after entering the alternate account password', async () => {
    mocks.disconnect.mockResolvedValue(undefined);
    const wrapper = mount(TelegramAccountPanel, { props: { profile: { ...profile, telegram_linked: true } } });
    await button(wrapper, 'Отключить Telegram').trigger('click'); expect(mocks.disconnect).not.toHaveBeenCalled();
    await wrapper.get('input[type="password"]').setValue('personal password'); await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(mocks.disconnect).toHaveBeenCalledWith('personal password'); expect(mocks.refresh).toHaveBeenCalledOnce(); wrapper.unmount();
  });
  it('does not offer disconnect without an alternate credential', () => {
    managerSession.auth.value = { can_change_password: false } as any;
    const wrapper = mount(TelegramAccountPanel, { props: { profile: { ...profile, telegram_linked: true } } });
    expect(button(wrapper, 'Отключить Telegram').attributes('disabled')).toBeDefined(); expect(wrapper.find('form').exists()).toBe(false); wrapper.unmount();
  });
});
