import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
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

import ProductsView from '../src/views/ProductsView.vue';
import { catalogManagementApi } from '../src/services/catalog-management-api';

const filtersStub = {
  name: 'CatalogManagementFilters',
  props: ['modelValue', 'sort'],
  template: '<div data-test="management-filters" />',
};
const result = (items: any[]) => ({ items, meta: { page: 1, pages: 1, total: items.length, limit: 40 } });
const product = { id: 11, title: 'MDV Aurora 12', slug: 'mdv-aurora-12', main_image: null, images: [], gallery_images: [], tags: [] } as any;

class TestIntersectionObserver {
  observe() {}
  disconnect() {}
  unobserve() {}
}
(globalThis as any).IntersectionObserver = TestIntersectionObserver;

describe('product management list', () => {
  let wrapper: ReturnType<typeof mount> | undefined;
  const start = async () => {
    history.replaceState({}, '', '/manager/products');
    wrapper = mount(ProductsView, { global: { stubs: { CatalogManagementFilters: filtersStub } } });
    await flushPromises();
    return wrapper;
  };

  afterEach(() => {
    wrapper?.unmount(); wrapper = undefined;
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

  it('opens the product workspace from an image click and clears selection on filters', async () => {
    vi.mocked(catalogManagementApi.list).mockResolvedValue(result([product]));
    const view = await start();
    await view.find('div.absolute button').trigger('click');
    expect(view.text()).toContain('Выбрано: 1');
    view.findComponent(filtersStub).vm.$emit('update:modelValue', { includeOrderable: true, missing: 'image' });
    await flushPromises();
    expect(view.text()).not.toContain('Выбрано:');
    await view.find('[title="Открыть товар"]').trigger('click');
    expect(location.pathname).toBe('/manager/products/11');
  });
});
