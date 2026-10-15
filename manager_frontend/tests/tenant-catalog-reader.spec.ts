import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import TenantCatalogView from '../src/views/TenantCatalogView.vue';
import CatalogDecisionProductDetailsDialog from '../src/components/catalog-decision/CatalogDecisionProductDetailsDialog.vue';
import { ManagerTenantCatalogService } from '../src/client';
import { managerSession } from '../src/services/manager-session';
import { catalogDecisionSelectionStorageKey, loadCatalogDecisionSelection } from '../src/services/catalog-decision-selection';

const auth = { username: 'partner', tenant_id: 2, staff_user_id: 7, capabilities: ['crm.manage', 'catalog.master.read'] } as any;
let wrapper: ReturnType<typeof mount>;
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks(); managerSession.auth.value = null; localStorage.clear(); });

describe('partner catalog reader integration', () => {
  it('opens a product and shares a selection with the equipment workspace without leaving the list', async () => {
    managerSession.auth.value = auth;
    vi.spyOn(ManagerTenantCatalogService, 'listManagerTenantCatalogProducts').mockResolvedValue({
      items: [{ id: 11, title: 'Полная система', main_image: null, effective_price: 1500, allowed: true }],
      meta: { page: 1, pages: 1, total: 1, limit: 100 },
    } as any);
    wrapper = mount(TenantCatalogView, { global: { stubs: { CatalogDecisionProductDetailsDialog: true } } });
    await flushPromises();
    await wrapper.get('button[aria-label="Открыть карточку Полная система"]').trigger('click');
    const reader = wrapper.findComponent(CatalogDecisionProductDetailsDialog);
    expect(reader.props('open')).toBe(true);
    reader.vm.$emit('toggle', { id: 11, title: 'Полная система' }); await flushPromises();
    expect(reader.props('selected')).toBe(true);
    expect(reader.props('open')).toBe(true);
    expect(loadCatalogDecisionSelection(catalogDecisionSelectionStorageKey(auth))).toEqual([{ id: 11, title: 'Полная система' }]);
    expect(wrapper.get('a[href="/manager/catalog-decision"]').text()).toContain('Открыть подбор');
    reader.vm.$emit('close'); await flushPromises();
    expect(reader.props('open')).toBe(false);
    expect(ManagerTenantCatalogService.listManagerTenantCatalogProducts).toHaveBeenCalledTimes(1);
  });
});
