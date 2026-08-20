import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  changePassword: vi.fn(),
}));

vi.mock('../src/client', () => ({
  ManagerService: {
    changeManagerAccountPassword: mocks.changePassword,
  },
}));

import ProfileSecurityView from '../src/views/ProfileSecurityView.vue';
import { isManagerPathAllowed } from '../src/manager-capabilities';
import { passwordPolicyMessage } from '../src/services/manager-account-security';
import { clearManagerSession, managerSession } from '../src/services/manager-session';

const staffAuth = {
  username: 'manager',
  status: 'authenticated',
  staff_user_id: 7,
  role: 'manager',
  tenant_id: 2,
  storefront_id: 3,
  capabilities: ['crm.manage'],
  can_change_password: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  managerSession.isAuthenticated.value = true;
  managerSession.auth.value = { ...staffAuth };
});

afterEach(() => clearManagerSession());

describe('ProfileSecurityView', () => {
  it('is available to an ordinary authenticated manager without a special capability', () => {
    expect(isManagerPathAllowed(staffAuth, '/manager/profile')).toBe(true);
    const wrapper = mount(ProfileSecurityView);
    expect(wrapper.get('h1').text()).toBe('Профиль / Безопасность');
  });

  it('generates a policy-compliant password with browser crypto', async () => {
    const values = new Uint8Array(24).fill(7);
    const getRandomValues = vi.spyOn(window.crypto, 'getRandomValues').mockImplementation((array) => {
      (array as Uint8Array).set(values);
      return array;
    });
    const wrapper = mount(ProfileSecurityView);

    await wrapper.get('button[type="button"]').trigger('click');

    const password = (wrapper.get('#new-password').element as HTMLInputElement).value;
    expect(getRandomValues).toHaveBeenCalledOnce();
    expect(password).toHaveLength(24);
    expect(wrapper.get('#new-password').attributes('type')).toBe('text');
    expect((wrapper.get('#password-confirmation').element as HTMLInputElement).value).toBe(password);
  });

  it('counts Unicode code points the same way as the backend policy', () => {
    expect(passwordPolicyMessage('😀'.repeat(11))).toContain('минимум 12');
    expect(passwordPolicyMessage('😀'.repeat(12))).toBeNull();
  });

  it('requires saving a generated password and supports explicit clipboard copy', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    mocks.changePassword.mockResolvedValue(undefined);
    const wrapper = mount(ProfileSecurityView);
    await wrapper.get('#current-password').setValue('current-password');
    await wrapper.get('button[type="button"]').trigger('click');

    await wrapper.get('form').trigger('submit');
    expect(wrapper.get('[role="alert"]').text()).toContain('Сохраните');
    expect(mocks.changePassword).not.toHaveBeenCalled();

    const generated = (wrapper.get('#new-password').element as HTMLInputElement).value;
    await wrapper.get('[data-testid="copy-generated-password"]').trigger('click');
    await flushPromises();
    expect(writeText).toHaveBeenCalledWith(generated);
    expect((wrapper.get('[data-testid="generated-password-saved"]').element as HTMLInputElement).checked).toBe(true);

    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(mocks.changePassword).toHaveBeenCalledOnce();
  });

  it('requires saving again when copied generated credentials are edited', async () => {
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    const wrapper = mount(ProfileSecurityView);
    await wrapper.get('#current-password').setValue('current-password');
    await wrapper.get('button[type="button"]').trigger('click');
    await wrapper.get('[data-testid="copy-generated-password"]').trigger('click');
    await flushPromises();
    expect((wrapper.get('[data-testid="generated-password-saved"]').element as HTMLInputElement).checked).toBe(true);

    await wrapper.get('#new-password').setValue('edited-password-2026');
    await wrapper.get('#password-confirmation').setValue('edited-password-2026');
    await flushPromises();
    expect((wrapper.get('[data-testid="generated-password-saved"]').element as HTMLInputElement).checked).toBe(false);

    await wrapper.get('form').trigger('submit');
    expect(wrapper.get('[role="alert"]').text()).toContain('Сохраните');
    expect(mocks.changePassword).not.toHaveBeenCalled();
  });

  it('keeps generated credentials unsaved when clipboard copy fails', async () => {
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
    });
    const wrapper = mount(ProfileSecurityView);
    await wrapper.get('#current-password').setValue('current-password');
    await wrapper.get('button[type="button"]').trigger('click');
    await wrapper.get('[data-testid="copy-generated-password"]').trigger('click');
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain('вручную');
    expect((wrapper.get('[data-testid="generated-password-saved"]').element as HTMLInputElement).checked).toBe(false);
    await wrapper.get('form').trigger('submit');
    expect(mocks.changePassword).not.toHaveBeenCalled();
  });

  it('does not confirm a stale clipboard snapshot after fields change', async () => {
    let resolveCopy: (() => void) | undefined;
    const writeText = vi.fn().mockImplementation(() => new Promise<void>((resolve) => {
      resolveCopy = resolve;
    }));
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    const wrapper = mount(ProfileSecurityView);
    await wrapper.get('#current-password').setValue('current-password');
    await wrapper.get('button[type="button"]').trigger('click');
    const copiedSnapshot = (wrapper.get('#new-password').element as HTMLInputElement).value;

    const copyRequest = wrapper.get('[data-testid="copy-generated-password"]').trigger('click');
    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith(copiedSnapshot));
    await wrapper.get('#new-password').setValue('changed-during-copy-2026');
    await wrapper.get('#password-confirmation').setValue('changed-during-copy-2026');
    resolveCopy?.();
    await copyRequest;
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain('ещё раз');
    expect((wrapper.get('[data-testid="generated-password-saved"]').element as HTMLInputElement).checked).toBe(false);
    await wrapper.get('form').trigger('submit');
    expect(mocks.changePassword).not.toHaveBeenCalled();
  });

  it('shows a local mismatch error and does not call the API', async () => {
    const wrapper = mount(ProfileSecurityView);
    await wrapper.get('#current-password').setValue('current-password');
    await wrapper.get('#new-password').setValue('new-password-2026');
    await wrapper.get('#password-confirmation').setValue('different-password');

    await wrapper.get('form').trigger('submit');

    expect(wrapper.get('[role="alert"]').text()).toContain('не совпадают');
    expect(mocks.changePassword).not.toHaveBeenCalled();
  });

  it('rejects a password outside the client policy before submitting', async () => {
    const wrapper = mount(ProfileSecurityView);
    await wrapper.get('#current-password').setValue('current-password');
    await wrapper.get('#new-password').setValue('short');
    await wrapper.get('#password-confirmation').setValue('short');

    await wrapper.get('form').trigger('submit');

    expect(wrapper.get('[role="alert"]').text()).toContain('минимум 12');
    expect(mocks.changePassword).not.toHaveBeenCalled();
  });

  it('clears the manager session and emits the login-boundary event after success', async () => {
    mocks.changePassword.mockResolvedValue(undefined);
    const wrapper = mount(ProfileSecurityView);
    await wrapper.get('#current-password').setValue('current-password');
    await wrapper.get('#new-password').setValue('new-password-2026');
    await wrapper.get('#password-confirmation').setValue('new-password-2026');

    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(mocks.changePassword).toHaveBeenCalledWith({
      current_password: 'current-password',
      new_password: 'new-password-2026',
    });
    expect(managerSession.isAuthenticated.value).toBe(false);
    expect(managerSession.auth.value).toBeNull();
    expect(wrapper.emitted('passwordChanged')).toHaveLength(1);
  });

  it('shows legacy self-service as unavailable and never submits', async () => {
    managerSession.auth.value = {
      ...staffAuth,
      auth_source: 'legacy',
      can_change_password: false,
    };
    const wrapper = mount(ProfileSecurityView);

    expect(wrapper.get('[data-testid="password-change-unavailable"]').text()).toContain('недоступна');
    expect(wrapper.find('form').exists()).toBe(false);
    expect(mocks.changePassword).not.toHaveBeenCalled();
  });
});
