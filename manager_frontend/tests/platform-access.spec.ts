import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ list: vi.fn(), update: vi.fn() }));
vi.mock('../src/client', () => ({ OpenAPI: {}, ManagerAccessService: { listManagerAccess: mocks.list, updateManagerAccess: mocks.update } }));
import PlatformAccessView from '../src/views/PlatformAccessView.vue';
import { managerSession } from '../src/services/manager-session';
import { MANAGER_CAPABILITY, isManagerPathAllowed } from '../src/manager-capabilities';
import { toggleCatalogPermission } from '../src/services/manager-access';

const item = { membership_id: 7, staff_user_id: 20, display_name: 'Мария', tenant_id: 2, tenant_name: 'Компания', role: 'catalog_editor', status: 'active', permissions: [], updated_at: '2026-10-16T08:00:00Z' };
describe('catalog access separation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    managerSession.auth.value = { capabilities: [MANAGER_CAPABILITY.infrastructureManage], role: 'owner', is_platform_owner: true } as any;
    mocks.list.mockResolvedValue({ items: [{ ...item }], meta: { page: 1, limit: 50, total: 1, pages: 1 } });
  });
  it('lets catalog editors open cards and reference data without CRM or platform tools', () => {
    const auth = { capabilities: [MANAGER_CAPABILITY.catalogMasterRead, MANAGER_CAPABILITY.catalogMasterEdit] };
    for (const path of ['/manager/products', '/manager/products/2', '/manager/products/2/media', '/manager/brands', '/manager/features', '/manager/tags']) expect(isManagerPathAllowed(auth, path), path).toBe(true);
    for (const path of ['/manager/orders', '/manager/customers', '/manager/catalog-decision', '/manager/platform/access', '/manager/media', '/manager/suppliers', '/manager/supply', '/manager/settings/platform']) expect(isManagerPathAllowed(auth, path), path).toBe(false);
  });
  it('retains unrelated grants and applies the delete-requires-edit invariant', () => {
    expect(toggleCatalogPermission(['crm.manage'], 'delete', true)).toEqual(['crm.manage', 'catalog.master.delete', 'catalog.master.edit']);
    expect(toggleCatalogPermission(['crm.manage', 'catalog.master.delete', 'catalog.master.edit'], 'edit', false)).toEqual(['crm.manage']);
    expect(toggleCatalogPermission(['catalog.master.edit', 'catalog.master.delete'], 'delete', false)).toEqual(['catalog.master.edit']);
  });
  it('does not fetch or render grant controls for company owners', async () => {
    managerSession.auth.value = { role: 'owner', capabilities: [MANAGER_CAPABILITY.staffManage] } as any;
    const wrapper = mount(PlatformAccessView);
    await flushPromises();
    expect(mocks.list).not.toHaveBeenCalled();
    expect(wrapper.findAll('[role="switch"]')).toHaveLength(0);
    expect(isManagerPathAllowed(managerSession.auth.value, '/manager/platform/access')).toBe(false);
    wrapper.unmount();
  });
  it('saves direct toggles with the current row version and does not offer owner grants', async () => {
    mocks.update.mockResolvedValue({ ...item, permissions: ['catalog.master.edit', 'catalog.master.delete'], updated_at: '2026-10-16T09:00:00Z' });
    const wrapper = mount(PlatformAccessView);
    await flushPromises();
    expect(mocks.list).toHaveBeenCalledWith(1, 50, undefined);
    expect(wrapper.text()).toContain('Мария');
    expect(wrapper.text()).toContain('Компания');
    expect(wrapper.findAll('[role="switch"]')).toHaveLength(2);
    await wrapper.get('input[aria-label="Удаление: Мария, Компания"]').setValue(true);
    await flushPromises();
    expect(mocks.update).toHaveBeenCalledWith(7, { permissions: ['catalog.master.delete', 'catalog.master.edit'], expected_updated_at: item.updated_at });
    expect(wrapper.findAll<HTMLInputElement>('[role="switch"]').every(control => control.element.checked)).toBe(true);
    await wrapper.get('input[aria-label="Удаление: Мария, Компания"]').setValue(false);
    expect(mocks.update).toHaveBeenLastCalledWith(7, { permissions: ['catalog.master.edit'], expected_updated_at: '2026-10-16T09:00:00Z' });
    wrapper.unmount();
  });
  it('restores the switch after a failed save and shows the row error', async () => {
    mocks.update.mockRejectedValue(new Error('Доступ изменён другим владельцем'));
    const wrapper = mount(PlatformAccessView);
    await flushPromises();
    await wrapper.get('input[aria-label="Редактирование: Мария, Компания"]').setValue(true);
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Доступ изменён другим владельцем');
    expect(wrapper.get<HTMLInputElement>('input[aria-label="Редактирование: Мария, Компания"]').element.checked).toBe(false);
    wrapper.unmount();
  });
});
