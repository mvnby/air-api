import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import CatalogDecisionWorkspaceView from '../src/views/CatalogDecisionWorkspaceView.vue';
import CatalogDecisionFilters from '../src/components/catalog-decision/CatalogDecisionFilters.vue';
import CatalogDecisionTable from '../src/components/catalog-decision/CatalogDecisionTable.vue';
import CatalogDecisionSelectionTray from '../src/components/catalog-decision/CatalogDecisionSelectionTray.vue';
import { catalogDecisionApi } from '../src/services/catalog-decision-api';
import { catalogDecisionSelectionStorageKey, saveCatalogDecisionSelection, loadCatalogDecisionSelection } from '../src/services/catalog-decision-selection';
import { catalogDecisionUrl, readCatalogDecisionContext, orderWorkspaceUrl } from '../src/services/catalog-decision-context';
import { ManagerOrdersService, ManagerCatalogDecisionService } from '../src/client';
import { managerSession } from '../src/services/manager-session';

import { MANAGER_CAPABILITY, requiredCapabilityForManagerPath } from '../src/manager-capabilities';

describe('catalog decision workspace boundary', () => {
  it('keeps the supplier-aware system workspace out of tenant navigation', () => {
    expect(requiredCapabilityForManagerPath('/manager/catalog-decision'))
      .toBe(MANAGER_CAPABILITY.platformManage);
  });
});

const identity = { username: 'manager-test', tenant_id: 1, staff_user_id: 7, capabilities: ['platform.manage'] } as any;
const selectedModel = { id: 11, title: 'Console 12', heating_min_c: -30 } as any;
const targetOrder = { id: 42, title: 'Офис', status: 'negotiation', proposals: [
  { id: 50, name: 'Основное', status: 'draft', is_selected: true },
  { id: 51, name: 'Для кабинета', status: 'draft', is_selected: false },
] } as any;
let workspace: ReturnType<typeof mount> | undefined;
const startWorkspace = async (search = '') => {
  history.replaceState({}, '', `/manager/catalog-decision${search}`);
  managerSession.auth.value = identity;
  vi.spyOn(catalogDecisionApi, 'list').mockResolvedValue({ items: [selectedModel], meta: { page: 1, pages: 1, total: 1, limit: 40 } });
  vi.spyOn(catalogDecisionApi, 'filterOptions').mockResolvedValue({ brands: [], series: [] });
  vi.spyOn(ManagerOrdersService, 'getManagerOrderDetail').mockResolvedValue(targetOrder);
  workspace = mount(CatalogDecisionWorkspaceView, { global: { stubs: {
    CatalogDecisionFilters: true, CatalogDecisionTable: true, CatalogDecisionSelectionTray: true,
    CatalogDecisionCollectionDialog: true, CatalogDecisionOrderDialog: true, CatalogDecisionQuickOrderDialog: true,
  } } });
  await flushPromises();
  return workspace;
};
afterEach(() => {
  workspace?.unmount(); workspace = undefined;
  vi.restoreAllMocks(); vi.useRealTimers();
  localStorage.clear(); managerSession.auth.value = null;
  history.replaceState({}, '', '/');
});

describe('order-bound equipment selection', () => {
  it('round trips the exact order and proposal, retaining order list filters', () => {
    const url = catalogDecisionUrl(42, 51, '/manager/orders/kanban?view=list&status=negotiation');
    const context = readCatalogDecisionContext(new URL(url, 'https://manager.local').search);
    expect(context).toEqual({ orderId: 42, proposalId: 51, returnTo: '/manager/orders/kanban?view=list&status=negotiation&orderId=42&proposalId=51' });
    expect(orderWorkspaceUrl(42, 51, 'https://evil.example/path')).toBe('/manager/orders/kanban?orderId=42&proposalId=51');
    expect(() => readCatalogDecisionContext('?orderId=42')).toThrow('корректный заказ');
    expect(() => readCatalogDecisionContext('?orderId=4.2&proposalId=51')).toThrow();
  });

  it('keeps general and different proposal baskets separate, then adds to the exact target', async () => {
    const key = catalogDecisionSelectionStorageKey(identity);
    saveCatalogDecisionSelection([{ id: 90, title: 'Общая корзина' }], key);
    saveCatalogDecisionSelection([{ id: 91, title: 'Другой вариант' }], `${key}:order-42:proposal-50`);
    const attach = vi.spyOn(ManagerCatalogDecisionService, 'attachManagerCatalogDecisionToOrder').mockResolvedValue(targetOrder);
    const wrapper = await startWorkspace('?orderId=42&proposalId=51');
    const tray = wrapper.findComponent(CatalogDecisionSelectionTray);
    expect(tray.props('items')).toEqual([]);
    expect(wrapper.text()).toContain('Для кабинета');
    wrapper.findComponent(CatalogDecisionTable).vm.$emit('toggle', selectedModel);
    await flushPromises();
    expect(loadCatalogDecisionSelection(`${key}:order-42:proposal-51`)).toEqual([{ id: 11, title: 'Console 12' }]);
    tray.vm.$emit('attach-target');
    await flushPromises();
    expect(attach).toHaveBeenCalledWith(42, { product_ids: [11], mode: 'append_to_proposal', proposal_id: 51 });
    expect(location.pathname + location.search).toBe('/manager/orders/kanban?orderId=42&proposalId=51');
    expect(loadCatalogDecisionSelection(`${key}:order-42:proposal-51`)).toEqual([]);
    expect(loadCatalogDecisionSelection(key)).toEqual([{ id: 90, title: 'Общая корзина' }]);
    expect(loadCatalogDecisionSelection(`${key}:order-42:proposal-50`)).toEqual([{ id: 91, title: 'Другой вариант' }]);
  });

  it('retains selection and target when attaching fails', async () => {
    vi.spyOn(ManagerCatalogDecisionService, 'attachManagerCatalogDecisionToOrder').mockRejectedValue(new Error('temporary failure'));
    const wrapper = await startWorkspace('?orderId=42&proposalId=51');
    wrapper.findComponent(CatalogDecisionTable).vm.$emit('toggle', selectedModel);
    await flushPromises();
    wrapper.findComponent(CatalogDecisionSelectionTray).vm.$emit('attach-target');
    await flushPromises();
    expect(location.pathname).toBe('/manager/catalog-decision');
    expect(wrapper.findComponent(CatalogDecisionSelectionTray).props('items')).toHaveLength(1);
    expect(wrapper.find('[role="alert"]').exists()).toBe(true);
  });

  it('blocks a missing target instead of silently using the general order dialog', async () => {
    const attach = vi.spyOn(ManagerCatalogDecisionService, 'attachManagerCatalogDecisionToOrder');
    const wrapper = await startWorkspace('?orderId=42&proposalId=99');
    expect(wrapper.text()).toContain('Вариант предложения больше недоступен');
    const tray = wrapper.findComponent(CatalogDecisionSelectionTray);
    expect(tray.props('targeted')).toBe(true);
    expect(tray.props('canAttach')).toBe(false);
    tray.vm.$emit('attach-target');
    await flushPromises();
    expect(attach).not.toHaveBeenCalled();
  });

  it('does not let an old search response overwrite the new frost results', async () => {
    const wrapper = await startWorkspace();
    let finishOld!: (value: any) => void;
    const list = vi.mocked(catalogDecisionApi.list);
    list.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }));
    wrapper.findComponent(CatalogDecisionFilters).vm.$emit('update:modelValue', { heatingMin: -20 });
    await flushPromises();
    list.mockResolvedValueOnce({ items: [{ ...selectedModel, id: 30 }], meta: { page: 1, pages: 1, total: 1, limit: 40 } });
    wrapper.findComponent(CatalogDecisionFilters).vm.$emit('update:modelValue', { heatingMin: -30 });
    await flushPromises();
    finishOld({ items: [{ ...selectedModel, id: 20 }], meta: { page: 1, pages: 1, total: 1, limit: 40 } });
    await flushPromises();
    expect(wrapper.findComponent(CatalogDecisionTable).props('items').map((item: any) => item.id)).toEqual([30]);
  });
});
