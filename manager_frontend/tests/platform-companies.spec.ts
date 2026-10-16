import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ list: vi.fn(), update: vi.fn() }));
vi.mock('../src/services/manager-companies', () => ({ managerCompaniesApi: mocks }));
import PlatformCompaniesView from '../src/views/PlatformCompaniesView.vue';
import { isManagerPathAllowed, hasManagerCapability, MANAGER_CAPABILITY } from '../src/manager-capabilities';
const company = { id: 4, display_name: 'Партнёр', slug: 'partner', kind: 'partner', status: 'active', is_system: false, demo_read_only: false, updated_at: 'version-1', owners: [{ staff_user_id: 7, display_name: 'Мария' }], active_staff_count: 3, sites: [{ id: 1, slug: 'minsk', display_name: 'Минск', status: 'active', city: 'Минск', currency: 'BYN', default_locale: 'ru-BY', is_default: true, domains: [{ id: 1, hostname: 'partner.test', status: 'active', is_primary: true, verified_at: '2026-01-01' }] }] };
beforeEach(() => { vi.clearAllMocks(); mocks.list.mockResolvedValue({ items: [company], total: 1, page: 1, limit: 50 }); });
describe('platform companies', () => {
  it('limits the route to company management and hides global tools outside canonical company', () => {
    expect(isManagerPathAllowed({ capabilities: ['staff.manage'] }, '/manager/platform/companies')).toBe(false);
    expect(isManagerPathAllowed({ capabilities: ['platform.companies.manage'] }, '/manager/platform/companies')).toBe(true);
    expect(hasManagerCapability({ capabilities: ['platform.manage', 'infrastructure.manage'], is_system_tenant: false }, MANAGER_CAPABILITY.platformManage)).toBe(false);
  });
  it('shows read-only sites/domains and writes the current company version on direct status toggle', async () => {
    mocks.update.mockResolvedValue({ ...company, status: 'disabled', updated_at: 'version-2' }); const wrapper = mount(PlatformCompaniesView); await flushPromises();
    expect(wrapper.text()).toContain('partner.test'); expect(wrapper.text()).toContain('Подключён'); expect(wrapper.text()).not.toContain('Сайт: minsk'); expect(wrapper.text()).toContain('Мария'); await wrapper.get('[role="switch"]').setValue(false); await flushPromises(); expect(mocks.update).toHaveBeenCalledWith(company, { status: 'disabled' }); expect(wrapper.text()).toContain('Отключена'); wrapper.unmount();
  });
  it('protects system disabling and preserves edits after a stale version error', async () => {
    mocks.list.mockResolvedValue({ items: [{ ...company, is_system: true }], total: 1 }); mocks.update.mockRejectedValue({ status: 409, body: { detail: 'Компания изменилась. Обновите страницу.' } }); const wrapper = mount(PlatformCompaniesView); await flushPromises(); expect(wrapper.get('[role="switch"]').attributes('disabled')).toBeDefined();
    await wrapper.get('input[maxlength="200"]').setValue('Новое имя'); await wrapper.findAll('form')[1]!.trigger('submit'); await flushPromises(); expect(wrapper.get('[role="alert"]').text()).toContain('Компания изменилась'); expect(wrapper.get('input[maxlength="200"]').element.value).toBe('Новое имя'); wrapper.unmount();
  });
});
