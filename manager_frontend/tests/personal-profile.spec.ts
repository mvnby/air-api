import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ get: vi.fn(), update: vi.fn(), uploadAvatar: vi.fn(), removeAvatar: vi.fn() }));
vi.mock('../src/services/manager-profile', async original => ({ ...await original<typeof import('../src/services/manager-profile')>(), managerProfileApi: mocks }));
vi.mock('../src/components/profile/AvatarCropDialog.vue', () => ({ default: { name: 'AvatarCropDialog', props: ['file', 'busy', 'errorMessage'], emits: ['save'], template: '<div />' } }));
vi.mock('../src/components/profile/TelegramAccountPanel.vue', () => ({ default: { template: '<div />' } }));
import PersonalProfilePanel from '../src/components/profile/PersonalProfilePanel.vue';
import { managerSession } from '../src/services/manager-session';
const profile = { staff_user_id: 7, display_name: 'Мария Иванова', username: 'maria', phone: '+375291234567', email: null, avatar_url: '/api/manager/staff/7/avatar?v=first', updated_at: '2026-10-16T12:00:00Z', telegram_linked: false, telegram_username: null, telegram_notifications_enabled: false };
const start = async () => { const wrapper = mount(PersonalProfilePanel); await flushPromises(); return wrapper; };
describe('self profile', () => {
  beforeEach(() => {
    vi.clearAllMocks(); managerSession.isAuthenticated.value = true;
    managerSession.auth.value = { staff_user_id: 7, username: 'maria', role: 'manager', display_name: 'Old name', auth_source: 'staff_password' } as any;
    mocks.get.mockResolvedValue({ ...profile });
  });
  it('saves only personal contacts and updates the current identity without a login reset', async () => {
    const wrapper = await start(); const previous = managerSession.auth.value;
    const inputs = wrapper.findAll('input');
    expect(wrapper.get('input[readonly]').element.value).toBe('maria');
    await inputs.find(input => input.attributes('autocomplete') === 'name')!.setValue(' Мария Петрова ');
    await wrapper.get('input[type="tel"]').setValue('');
    mocks.update.mockResolvedValue({ ...profile, display_name: 'Мария Петрова', phone: null, updated_at: '2026-10-16T13:00:00Z' });
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(mocks.update).toHaveBeenCalledWith({ display_name: 'Мария Петрова', phone: null, email: null, expected_updated_at: profile.updated_at });
    expect(managerSession.auth.value).not.toBe(previous); expect(managerSession.auth.value?.display_name).toBe('Мария Петрова');
    expect(managerSession.isAuthenticated.value).toBe(true); expect(wrapper.text()).toContain('Профиль сохранён'); wrapper.unmount();
  });
  it('preserves entered contacts when an avatar is removed and uses the current version', async () => {
    const wrapper = await start(); await wrapper.get('input[type="tel"]').setValue('new phone');
    mocks.removeAvatar.mockResolvedValue({ ...profile, avatar_url: null, updated_at: '2026-10-16T13:00:00Z' });
    await wrapper.findAll('button').find(button => button.text() === 'Удалить фото')!.trigger('click'); await flushPromises();
    expect(mocks.removeAvatar).toHaveBeenCalledWith(profile.updated_at);
    expect((wrapper.get('input[type="tel"]').element as HTMLInputElement).value).toBe('new phone');
    expect(wrapper.find('img').exists()).toBe(false); wrapper.unmount();
  });
  it('uploads the prepared crop with optimistic version and updates avatar in session', async () => {
    const wrapper = await start(); const file = new File(['prepared'], 'avatar.webp', { type: 'image/webp' });
    mocks.uploadAvatar.mockResolvedValue({ ...profile, avatar_url: '/api/manager/staff/7/avatar?v=second' });
    wrapper.getComponent({ name: 'AvatarCropDialog' }).vm.$emit('save', file); await flushPromises();
    expect(mocks.uploadAvatar).toHaveBeenCalledWith(file, profile.updated_at);
    expect((managerSession.auth.value as any).avatar_url).toContain('v=second'); wrapper.unmount();
  });
  it('shows a conflict without silently replacing unsaved contacts', async () => {
    const wrapper = await start(); await wrapper.get('input[type="tel"]').setValue('unsaved');
    mocks.update.mockRejectedValue({ status: 409, body: { detail: 'Профиль изменился. Обновите данные.' } });
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Профиль изменился');
    expect((wrapper.get('input[type="tel"]').element as HTMLInputElement).value).toBe('unsaved'); wrapper.unmount();
  });
  it('rejects unsupported and oversized files before upload or opening the crop', async () => {
    const wrapper = await start();
    const input = wrapper.get('input[type="file"]');
    for (const [file, message] of [[new File(['svg'], 'face.svg', { type: 'image/svg+xml' }), 'JPEG, PNG или WebP'], [new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' }), '5 МБ']] as const) {
      Object.defineProperty(input.element, 'files', { configurable: true, value: [file] });
      await input.trigger('change');
      expect(wrapper.get('[role="alert"]').text()).toContain(message);
      expect(wrapper.getComponent({ name: 'AvatarCropDialog' }).props('file')).toBeNull();
    }
    expect(mocks.uploadAvatar).not.toHaveBeenCalled(); wrapper.unmount();
  });

  it('does not fetch or edit a legacy shared account', async () => {
    managerSession.auth.value = { auth_source: 'legacy' } as any;
    const wrapper = await start(); expect(mocks.get).not.toHaveBeenCalled(); expect(wrapper.find('form').exists()).toBe(false); wrapper.unmount();
  });
});
