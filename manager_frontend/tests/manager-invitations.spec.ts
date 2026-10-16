import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ preview: vi.fn(), accept: vi.fn(), choices: vi.fn(), list: vi.fn(), create: vi.fn(), revoke: vi.fn() }));
vi.mock('../src/services/manager-invitations', async original => ({ ...await original<typeof import('../src/services/manager-invitations')>(), managerInvitationsApi: mocks }));
vi.mock('../src/services/manager-companies', () => ({ managerCompaniesApi: { choices: mocks.choices } }));
import InvitationAcceptView from '../src/views/InvitationAcceptView.vue';
import TeamInvitationsPanel from '../src/components/manager/TeamInvitationsPanel.vue';
import { managerSession } from '../src/services/manager-session';
const preview = { company_name: 'Партнёр Минск', role: 'manager', expires_at: new Date(Date.now() + 86400000).toISOString() };
beforeEach(() => { vi.clearAllMocks(); mocks.preview.mockResolvedValue(preview); mocks.choices.mockResolvedValue({ username: 'maria' }); mocks.accept.mockResolvedValue({ tenant_id: 8, default_storefront_slug: 'minsk' }); mocks.list.mockResolvedValue({ items: [], total: 0, page: 1, limit: 50 }); managerSession.auth.value = { role: 'owner' } as any; });
describe('invitation acceptance', () => {
  it('previews without joining and requires explicit current account choice', async () => {
    const navigate = vi.fn(), wrapper = mount(InvitationAcceptView, { props: { token: 'secret', navigateAfterAccept: navigate } }); await flushPromises();
    expect(wrapper.text()).toContain('Партнёр Минск'); expect(mocks.accept).not.toHaveBeenCalled(); expect(wrapper.get('button').attributes('disabled')).toBeDefined();
    await wrapper.get('input[value="existing"]').setValue(true); await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(mocks.accept).toHaveBeenCalledWith({ token: 'secret', mode: 'existing' }); expect(navigate).toHaveBeenCalledWith('/manager/?company=8&site=minsk'); wrapper.unmount();
  });
  it('allows credentials for a person without a selected workspace and retains errors locally', async () => {
    mocks.choices.mockRejectedValue({ status: 403 }); mocks.accept.mockRejectedValue({ status: 401, body: { detail: 'Неверный пароль' } });
    const wrapper = mount(InvitationAcceptView, { props: { token: 'secret' } }); await flushPromises(); expect(wrapper.find('input[value="existing"]').exists()).toBe(false);
    await wrapper.get('input[value="existing_credentials"]').setValue(true); await wrapper.get('input[autocomplete="username"]').setValue('other'); await wrapper.get('input[type="password"]').setValue('provided-password'); await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(mocks.accept).toHaveBeenCalledWith({ token: 'secret', mode: 'existing_credentials', username: 'other', password: 'provided-password' }); expect(wrapper.get('[role="alert"]').text()).toContain('Неверный пароль'); wrapper.unmount();
  });
  it('creates a personal account only after choosing new and submitting all personal proof', async () => {
    const wrapper = mount(InvitationAcceptView, { props: { token: 'secret', navigateAfterAccept: vi.fn() } }); await flushPromises(); await wrapper.get('input[value="new"]').setValue(true);
    await wrapper.get('input[autocomplete="name"]').setValue('Мария'); await wrapper.get('input[autocomplete="username"]').setValue('maria-new'); await wrapper.get('input[type="password"]').setValue('new-secret-password'); await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(mocks.accept).toHaveBeenCalledWith({ token: 'secret', mode: 'new', username: 'maria-new', password: 'new-secret-password', display_name: 'Мария' }); wrapper.unmount();
  });
  it('never submits expired or missing invitations', async () => {
    mocks.preview.mockResolvedValue({ ...preview, expires_at: '2020-01-01' }); const wrapper = mount(InvitationAcceptView, { props: { token: 'expired' } }); await flushPromises(); expect(wrapper.find('form').exists()).toBe(false); expect(mocks.accept).not.toHaveBeenCalled(); wrapper.unmount();
    mocks.preview.mockClear(); const missing = mount(InvitationAcceptView, { props: { token: '' } }); await flushPromises(); expect(mocks.preview).not.toHaveBeenCalled(); expect(missing.text()).toContain('нет приглашения'); missing.unmount();
  });
});
describe('company invitations', () => {
  it('creates a copyable link with a role and revokes only the selected pending invitation', async () => {
    mocks.create.mockResolvedValue({ id: 6, role: 'catalog_editor', expires_at: preview.expires_at, invite_url: 'https://manager.test/manager/invite#token=secret' });
    mocks.list.mockResolvedValue({ items: [{ id: 6, role: 'catalog_editor', status: 'pending', created_at: '2026-10-16', expires_at: preview.expires_at }], total: 1 });
    const writeText = vi.fn().mockResolvedValue(undefined); Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    const wrapper = mount(TeamInvitationsPanel); await flushPromises(); await wrapper.get('select').setValue('catalog_editor'); await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(mocks.create).toHaveBeenCalledWith('catalog_editor'); expect(wrapper.get('input[readonly]').element.value).toContain('#token=secret');
    await wrapper.findAll('button').find(button => button.text() === 'Скопировать ссылку')!.trigger('click'); await flushPromises(); expect(writeText).toHaveBeenCalledWith('https://manager.test/manager/invite#token=secret');
    await wrapper.findAll('button').find(button => button.text() === 'Отозвать')!.trigger('click'); await flushPromises(); expect(mocks.revoke).toHaveBeenCalledWith(6); expect(wrapper.find('input[readonly]').exists()).toBe(false); wrapper.unmount();
  });
  it('prevents admins inviting an owner', async () => {
    managerSession.auth.value = { role: 'admin' } as any; const wrapper = mount(TeamInvitationsPanel); await flushPromises(); expect(wrapper.get('option[value="owner"]').attributes('disabled')).toBeDefined(); await wrapper.get('select').setValue('owner'); await wrapper.get('form').trigger('submit'); expect(mocks.create).not.toHaveBeenCalled(); wrapper.unmount();
  });
});
