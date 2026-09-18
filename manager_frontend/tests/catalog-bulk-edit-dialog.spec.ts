import { flushPromises, shallowMount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ preview: vi.fn(), apply: vi.fn(), listBrands: vi.fn(), listFeatures: vi.fn(), track: vi.fn() }));
vi.mock('../src/services/catalog-bulk-api', async () => {
  const actual = await vi.importActual<typeof import('../src/services/catalog-bulk-api')>('../src/services/catalog-bulk-api');
  return { ...actual, catalogBulkApi: { preview: mocks.preview, apply: mocks.apply } };
});
vi.mock('../src/api', () => ({ api: { listManagerBrands: mocks.listBrands } }));
vi.mock('../src/client', () => ({ ManagerFeaturesService: { listManagerFeatures: mocks.listFeatures } }));
vi.mock('../src/composables/useSpecRegistry', () => ({
  useSpecRegistry: () => ({ knownSpecKeys: [], loadSpecRegistry: vi.fn(), serializeSpecValue: (_key: string, value: string) => value }),
}));
vi.mock('../src/composables/useCatalogUsage', () => ({
  useCatalogUsage: () => ({ track: mocks.track }),
}));

import CatalogBulkEditDialog from '../src/components/CatalogBulkEditDialog.vue';

const preview = () => ({
  token: 'signed-preview', changed_count: 1, expires_in_seconds: 900,
  items: [{ product_id: 11, title: 'Товар', changed: true, before: { brand: 'До' }, after: { brand: 'После' } }],
});
const mountDialog = () => shallowMount(CatalogBulkEditDialog, {
  props: { open: true, productIds: [11, 12] },
  global: { stubs: { ProductSeriesSelector: true, SpecKeyCombobox: true, SpecValueInput: true } },
});

beforeEach(() => {
  mocks.preview.mockReset();
  mocks.apply.mockReset();
  mocks.track.mockReset();
  mocks.listBrands.mockResolvedValue({ items: [] });
  mocks.listFeatures.mockResolvedValue({ items: [] });
});
afterEach(() => vi.clearAllMocks());

describe('CatalogBulkEditDialog', () => {
  it('loads catalog inputs when mounted already open', async () => {
    const wrapper = mountDialog();
    await flushPromises();
    expect(mocks.listBrands).toHaveBeenCalledOnce();
    expect(mocks.listFeatures).toHaveBeenCalledOnce();
    wrapper.unmount();
  });

  it('clears a preview when the selected product ids change', async () => {
    mocks.preview.mockResolvedValue(preview());
    const wrapper = mountDialog();
    await flushPromises();
    await wrapper.get('[data-testid="bulk-preview"]').trigger('click');
    await flushPromises();
    expect(mocks.preview).toHaveBeenCalledWith([11, 12], { kind: 'relations', brand_id: null, series_id: null });
    expect(wrapper.text()).toContain('Изменятся: 1 из 1');

    await wrapper.setProps({ productIds: [11, 13] });
    await flushPromises();
    expect(wrapper.find('[data-testid="bulk-preview"]').exists()).toBe(true);
    expect(wrapper.text()).not.toContain('Изменятся: 1 из 1');
  });

  it('does not restore a pending preview after its selected ids changed', async () => {
    let resolvePreview!: (value: ReturnType<typeof preview>) => void;
    mocks.preview.mockImplementationOnce(() => new Promise(resolve => { resolvePreview = resolve; }));
    const wrapper = mountDialog();
    await flushPromises();
    await wrapper.get('[data-testid="bulk-preview"]').trigger('click');
    await wrapper.setProps({ productIds: [11, 13] });
    resolvePreview(preview());
    await flushPromises();

    expect(wrapper.find('[data-testid="bulk-preview"]').exists()).toBe(true);
    expect(wrapper.text()).not.toContain('Изменятся: 1 из 1');
  });

  it('applies exactly the preview token and emits the result', async () => {
    mocks.preview.mockResolvedValue(preview());
    mocks.apply.mockResolvedValue({ updated: 1, product_ids: [11] });
    const wrapper = mountDialog();
    await flushPromises();
    await wrapper.get('[data-testid="bulk-preview"]').trigger('click');
    await flushPromises();
    await wrapper.get('button.btn-mini').trigger('click');
    await flushPromises();

    expect(mocks.apply).toHaveBeenCalledWith('signed-preview');
    expect(mocks.track).toHaveBeenCalledWith('bulk_edit', 'success', expect.any(Number));
    expect(wrapper.emitted('applied')?.[0]).toEqual([{ updated: 1, product_ids: [11] }]);
    expect(wrapper.emitted('close')).toHaveLength(1);
  });

  it('drops a stale preview after a 409 and tells the user to recalculate', async () => {
    mocks.preview.mockResolvedValue(preview());
    mocks.apply.mockRejectedValue({ status: 409, body: { detail: 'conflict' } });
    const wrapper = mountDialog();
    await flushPromises();
    await wrapper.get('[data-testid="bulk-preview"]').trigger('click');
    await flushPromises();
    await wrapper.get('button.btn-mini').trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('Товары изменились после предпросмотра. Рассчитайте изменения заново.');
    expect(wrapper.find('[data-testid="bulk-preview"]').exists()).toBe(true);
  });
});
