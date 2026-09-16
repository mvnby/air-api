import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import CatalogDecisionWorkspaceView from '../src/views/CatalogDecisionWorkspaceView.vue';
import CatalogDecisionFilters from '../src/components/catalog-decision/CatalogDecisionFilters.vue';
import CatalogDecisionCompareDialog from '../src/components/catalog-decision/CatalogDecisionCompareDialog.vue';
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
    CatalogDecisionCompareDialog: true, CatalogDecisionProductDetailsDialog: true,
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


describe('catalog workspace usability', () => {
  it('restores bookmarked criteria and retains exact target context on changes', async () => {
    const wrapper = await startWorkspace('?orderId=42&proposalId=51&coolingBtuClasses=30&retailMaxByn=4000&page=2&sort=retail_price');
    expect(catalogDecisionApi.list).toHaveBeenCalledWith(2, 40, expect.objectContaining({ coolingBtuClasses: [30], retailMaxByn: 4000 }), 'retail_price', 'asc');
    wrapper.findComponent(CatalogDecisionFilters).vm.$emit('update:modelValue', { isPublished: true, wifi: 'ready' });
    await flushPromises();
    expect(new URLSearchParams(location.search).get('wifi')).toBe('ready');
    expect(new URLSearchParams(location.search).get('proposalId')).toBe('51');
    expect(new URLSearchParams(location.search).has('coolingBtuClasses')).toBe(false);
  });

  it('retains table rows while loading but blocks selection of stale results', async () => {
    const wrapper = await startWorkspace();
    let finish!: (value: any) => void;
    vi.mocked(catalogDecisionApi.list).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    wrapper.findComponent(CatalogDecisionFilters).vm.$emit('update:modelValue', { heatingMin: -30 });
    await flushPromises();
    const table = wrapper.findComponent(CatalogDecisionTable);
    expect(table.props('items')).toEqual([selectedModel]);
    expect(table.props('busy')).toBe(true);
    table.vm.$emit('toggle', selectedModel);
    await flushPromises();
    expect(wrapper.findComponent(CatalogDecisionSelectionTray).props('items')).toEqual([]);
    finish({ items: [], meta: { page: 1, pages: 0, total: 0, limit: 40 } });
    await flushPromises();
    expect(wrapper.text()).toContain('Страница 1 из 1');
    expect(wrapper.text()).toContain('Показать также заказные');
  });

  it('hydrates restored cross-page selections with fresh server values for comparison', async () => {
    saveCatalogDecisionSelection([{ id: 11, title: 'Old title' }, { id: 22, title: 'Other page' }], catalogDecisionSelectionStorageKey(identity));
    const wrapper = await startWorkspace();
    vi.mocked(catalogDecisionApi.list).mockResolvedValueOnce({ items: [{ ...selectedModel, retail_price_byn: 2200 }, { id: 22, title: 'Other model', retail_price_byn: 3300 } as any], meta: { page: 1, pages: 1, total: 2, limit: 24 } });
    wrapper.findComponent(CatalogDecisionSelectionTray).vm.$emit('compare');
    await flushPromises();
    expect(catalogDecisionApi.list).toHaveBeenLastCalledWith(1, 24, { isPublished: true, includeOrderable: true, productIds: [11, 22] }, 'title', 'asc');
    const dialog = wrapper.findComponent(CatalogDecisionCompareDialog);
    expect(dialog.props('open')).toBe(true);
    expect(dialog.props('items').map((item: any) => item.retail_price_byn)).toEqual([2200, 3300]);
    expect(loadCatalogDecisionSelection(catalogDecisionSelectionStorageKey(identity))).toEqual([{ id: 11, title: 'Old title' }, { id: 22, title: 'Other page' }]);
  });
});
