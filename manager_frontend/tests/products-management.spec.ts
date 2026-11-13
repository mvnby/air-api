import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';

vi.mock('../src/services/catalog-management-api', () => ({
  defaultManagementFilters: () => ({ includeOrderable: true }),
  catalogManagementApi: { list: vi.fn(), selection: vi.fn() },
}));
vi.mock('../src/composables/useCatalogUsage', () => ({
  useCatalogUsage: () => ({ enabled: ref(false), track: vi.fn(), flush: vi.fn(), setOptIn: vi.fn() }),
}));
vi.mock('../src/services/ui-feedback', () => ({ confirmDialog: vi.fn().mockResolvedValue(false) }));
vi.mock('../src/components/CatalogBulkEditDialog.vue', () => ({ default: { template: '<div />' } }));
vi.mock('../src/components/BulkCompatibilityModal.vue', () => ({ default: { template: '<div />' } }));
vi.mock('../src/components/ProductEditModal.vue', () => ({ default: { template: '<div />' } }));
vi.mock('../src/components/OnlinerImportModal.vue', () => ({ default: { template: '<div />' } }));
vi.mock('../src/components/ProductImageCropDialog.vue', () => ({ default: { template: '<div />' } }));
vi.mock('../src/components/yandex-business/YandexBusinessFeedSettingsDialog.vue', () => ({ default: { template: '<div />' } }));
vi.mock('../src/components/catalog/CatalogUsageReport.vue', () => ({ default: { template: '<div />' } }));

import { managerSession } from '../src/services/manager-session';
import { api } from '../src/api';
import ProductsView from '../src/views/ProductsView.vue';
import { catalogManagementApi } from '../src/services/catalog-management-api';
import CatalogDecisionProductDetailsDialog from '../src/components/catalog-decision/CatalogDecisionProductDetailsDialog.vue';
import { saveProductWorkspaceContext } from '../src/utils/product-workspace';

const filtersStub = {
  name: 'CatalogManagementFilters',
  props: ['modelValue', 'sort'],
  template: '<div data-test="management-filters" />',
};
const result = (items: any[]) => ({ items, meta: { page: 1, pages: 1, total: items.length, limit: 40 } });
const product = { id: 11, title: 'MDV Aurora 12', slug: 'mdv-aurora-12', main_image: null, images: [], gallery_images: [], tags: [] } as any;

class TestIntersectionObserver {
  static instances: TestIntersectionObserver[] = [];
  observe = vi.fn();
  disconnect = vi.fn();
  unobserve = vi.fn();
  constructor(readonly callback: IntersectionObserverCallback) {
    TestIntersectionObserver.instances.push(this);
  }
  intersect() {
    this.callback([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
  }
}
(globalThis as any).IntersectionObserver = TestIntersectionObserver;

describe('product management list', () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear(); TestIntersectionObserver.instances = []; vi.mocked(catalogManagementApi.list).mockReset(); managerSession.auth.value = { username: 'owner', staff_user_id: 1, tenant_id: 1, capabilities: ['crm.manage', 'platform.manage', 'catalog.master.edit', 'catalog.master.delete'] } as any; });
  let wrapper: ReturnType<typeof mount> | undefined;
  const start = async (path = '/manager/products') => {
    history.replaceState({}, '', path);
    wrapper = mount(ProductsView, { global: { stubs: { CatalogManagementFilters: filtersStub, CatalogDecisionProductDetailsDialog: true } } });
    await flushPromises();
    return wrapper;
  };

  afterEach(() => {
    wrapper?.unmount(); wrapper = undefined;
    vi.useRealTimers();
    vi.restoreAllMocks();
    history.replaceState({}, '', '/');
  });

  it('keeps drafts in the first management list request', async () => {
    vi.mocked(catalogManagementApi.list).mockResolvedValue(result([product]));
    await start();
    expect(catalogManagementApi.list).toHaveBeenCalledWith(
      expect.objectContaining({ includeOrderable: true }), 1, 'recommended',
    );
    expect((vi.mocked(catalogManagementApi.list).mock.calls[0]![0] as any).isPublished).toBeUndefined();
  });

  it('observes the initial scroll sentinel and replaces it after a list refresh', async () => {
    vi.mocked(catalogManagementApi.list).mockResolvedValue({ ...result([product]), meta: { page: 1, pages: 2, total: 2, limit: 40 } });
    const view = await start();
    const observer = TestIntersectionObserver.instances[0]!;
    expect(observer.observe).toHaveBeenCalledTimes(1);
    const firstSentinel = observer.observe.mock.calls[0]![0];
    expect(view.element.contains(firstSentinel)).toBe(true);

    observer.intersect();
    await flushPromises();
    expect(catalogManagementApi.list).toHaveBeenLastCalledWith(expect.anything(), 2, 'recommended');

    await view.get('button[title="Обновить"]').trigger('click');
    await flushPromises();
    expect(observer.unobserve).toHaveBeenCalledWith(firstSentinel);
    expect(observer.observe).toHaveBeenCalledTimes(2);
    expect(view.element.contains(observer.observe.mock.calls[1]![0])).toBe(true);
  });

  it('does not create a scroll observer after unmounting during the initial request', async () => {
    let finish!: (value: any) => void;
    vi.mocked(catalogManagementApi.list).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }) as any);
    const view = await start();
    view.unmount(); wrapper = undefined;
    finish(result([product]));
    await flushPromises();
    expect(TestIntersectionObserver.instances).toHaveLength(0);
  });

  it('does not register listeners or request products after leaving during brand lookup', async () => {
    let finish!: (value: any) => void;
    vi.spyOn(api, 'listManagerBrands').mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }) as any);
    const addListener = vi.spyOn(document, 'addEventListener');
    const view = await start('/manager/products?seriesId=7&brand=mdv');
    view.unmount(); wrapper = undefined;
    addListener.mockClear();
    finish({ items: [{ id: 1, slug: 'mdv' }] });
    await flushPromises();
    expect(addListener.mock.calls.filter(([name]) => name === 'paste')).toHaveLength(0);
    expect(catalogManagementApi.list).not.toHaveBeenCalled();
    expect(TestIntersectionObserver.instances).toHaveLength(0);
  });

  it('stops restoring saved pages after a failed page without automatic retries', async () => {
    saveProductWorkspaceContext({ returnTo: '/manager/products', productIds: [11], currentProductId: 11, scrollTop: 200, page: 2, listState: {} });
    vi.mocked(catalogManagementApi.list)
      .mockResolvedValueOnce({ ...result([product]), meta: { page: 1, pages: 2, total: 2, limit: 40 } })
      .mockRejectedValueOnce(new Error('Page unavailable'))
      .mockResolvedValue({ ...result([product]), meta: { page: 2, pages: 2, total: 2, limit: 40 } });
    const view = await start();
    expect(catalogManagementApi.list).toHaveBeenCalledTimes(2);
    expect(view.text()).toContain('MDV Aurora 12');
    expect(view.text()).toContain('Page unavailable');
  });

  it('loads restored filters once and cancels a pending filter search on unmount', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    saveProductWorkspaceContext({ returnTo: '/manager/products', productIds: [11], currentProductId: 11, scrollTop: 0, page: 1, listState: { managementFilters: { search: 'saved search' } } });
    vi.mocked(catalogManagementApi.list).mockResolvedValue(result([product]));
    const view = await start();
    await vi.advanceTimersByTimeAsync(1000);
    expect(catalogManagementApi.list).toHaveBeenCalledTimes(1);
    expect(catalogManagementApi.list).toHaveBeenCalledWith(expect.objectContaining({ search: 'saved search' }), 1, 'recommended');
    view.findComponent(filtersStub).vm.$emit('update:modelValue', { search: 'new search' });
    await flushPromises();
    view.unmount(); wrapper = undefined;
    await vi.advanceTimersByTimeAsync(1000);
    expect(catalogManagementApi.list).toHaveBeenCalledTimes(1);
    expect(TestIntersectionObserver.instances[0]!.disconnect).toHaveBeenCalledOnce();
  });

  it('invalidates pending results immediately while new filters are debounced', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    vi.mocked(catalogManagementApi.list).mockResolvedValueOnce(result([product]));
    const view = await start();
    let finishOld!: (value: any) => void;
    vi.mocked(catalogManagementApi.list)
      .mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }) as any)
      .mockResolvedValueOnce(result([{ ...product, id: 30, title: 'Current result' }]));
    await view.get('button[title="Обновить"]').trigger('click');
    view.findComponent(filtersStub).vm.$emit('update:modelValue', { includeOrderable: false });
    await flushPromises();
    finishOld(result([{ ...product, id: 20, title: 'Obsolete result' }]));
    await flushPromises();
    expect(view.text()).not.toContain('Obsolete result');
    expect(view.text()).toContain('Загрузка товаров...');
    await vi.advanceTimersByTimeAsync(350);
    await flushPromises();
    expect(view.text()).toContain('Current result');
    expect(catalogManagementApi.list).toHaveBeenCalledTimes(3);
  });

  it('shows the official sign while preserving raw price and fixed cost precision', async () => {
    vi.mocked(catalogManagementApi.list).mockResolvedValue(result([{
      ...product, price: 10.234, min_cost_byn: 0, recommended_price_byn: null, margin_abs_preview: -0.01,
    }]));
    const view = await start();
    expect(view.text()).toContain('10.234 BYN');
    expect(view.text()).toContain('Себестоимость: 0.00 BYN');
    expect(view.text()).toContain('РРЦ: —');
    expect(view.text()).toContain('Маржа: -0.01 BYN');
    expect(view.find('svg[viewBox="0 0 360.67 446.4"]').exists()).toBe(true);
  });

  it('hides procurement and bulk tools for a catalog editor and opens the master card directly', async () => {
    managerSession.auth.value = { capabilities: ['catalog.master.read', 'catalog.master.edit'] } as any;
    vi.mocked(catalogManagementApi.list).mockResolvedValue(result([{ ...product, price: 10.234, min_cost_byn: 2, recommended_price_byn: 3, margin_abs_preview: 8 }]));
    const view = await start();
    expect(view.text()).toContain('10.234 BYN');
    for (const label of ['Себестоимость', 'Маржа', 'К РРЦ', 'Импорт', 'Скачать YML']) expect(view.text()).not.toContain(label);
    await view.find('div.absolute button').trigger('click');
    expect(view.findAll('button').filter(button => button.text().includes('Изменить выбранные'))).toHaveLength(0);
    expect(view.findAll('button').filter(button => button.text() === 'Удалить')).toHaveLength(0);
    await view.find('[title="Открыть товар"]').trigger('click');
    expect(location.pathname).toBe('/manager/products/11');
    expect(view.findComponent(CatalogDecisionProductDetailsDialog).props('item')).toBeNull();
  });

  it('does not let a stale list response replace newer filter results', async () => {
    vi.mocked(catalogManagementApi.list).mockResolvedValueOnce(result([product]));
    const view = await start();
    let finishOld!: (value: any) => void;
    vi.mocked(catalogManagementApi.list)
      .mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }))
      .mockResolvedValueOnce(result([{ ...product, id: 30, title: 'New result' }]));
    view.findComponent(filtersStub).vm.$emit('update:modelValue', { includeOrderable: false });
    await new Promise(resolve => window.setTimeout(resolve, 400));
    await flushPromises();
    view.findComponent(filtersStub).vm.$emit('update:modelValue', { includeOrderable: true, missing: 'image' });
    await new Promise(resolve => window.setTimeout(resolve, 400));
    await flushPromises();
    finishOld(result([{ ...product, id: 20, title: 'Stale result' }]));
    await flushPromises();
    expect(view.text()).toContain('New result');
    expect(view.text()).not.toContain('Stale result');
  });

  it('opens the reader from an image click and retains the separate editor action', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    vi.mocked(catalogManagementApi.list).mockResolvedValue(result([product]));
    const view = await start();
    await view.find('div.absolute button').trigger('click');
    expect(view.text()).toContain('Выбрано: 1');
    view.findComponent(filtersStub).vm.$emit('update:modelValue', { includeOrderable: true, missing: 'image' });
    await flushPromises();
    expect(view.text()).not.toContain('Выбрано:');
    await vi.advanceTimersByTimeAsync(350);
    await flushPromises();
    await view.find('[title="Открыть товар"]').trigger('click');
    expect(location.pathname).toBe('/manager/products');
    expect(view.findComponent(CatalogDecisionProductDetailsDialog).props('item')).toMatchObject({ id: 11 });
    view.findComponent(CatalogDecisionProductDetailsDialog).vm.$emit('edit', 11);
    expect(location.pathname).toBe('/manager/products/11');
  });

  it('provides a keyboard-accessible reader button in table mode', async () => {
    vi.mocked(catalogManagementApi.list).mockResolvedValue(result([product]));
    const view = await start();
    await view.get('button[title="Таблица"]').trigger('click');
    await view.get('button[aria-label="Открыть карточку MDV Aurora 12"]').trigger('click');
    expect(view.findComponent(CatalogDecisionProductDetailsDialog).props('item')).toMatchObject({ id: 11 });
    expect(location.pathname).toBe('/manager/products');
  });
});
