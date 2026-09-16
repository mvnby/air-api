import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  options: vi.fn(),
  create: vi.fn(),
  save: vi.fn(),
  preview: vi.fn(),
}));
vi.mock('../src/client', async () => {
  const actual = await vi.importActual<typeof import('../src/client')>('../src/client');
  return { ...actual, ManagerProductCollectionsService: {
    listManagerProductCollections: mocks.list,
    getManagerProductCollectionRuleOptions: mocks.options,
    createManagerProductCollection: mocks.create,
    saveManagerProductCollectionWorkspace: mocks.save,
    previewManagerProductCollection: mocks.preview,
  } };
});
import ProductCollectionsView from '../src/views/ProductCollectionsView.vue';
import ProductCollectionEditor from '../src/components/product-collections/ProductCollectionEditor.vue';

const collection = {
  id: 41, slug: 'master-choice', internal_name: 'Выбор мастера для дома', public_title: 'Выбор мастера',
  tenant_id: 1, storefront_id: 1, created_at: '2026-09-16T10:00:00Z', updated_at: '2026-09-16T10:00:00Z',
  status: 'published' as const, items: [{ id: 1, product_id: 5, position: 0, is_pinned: true, product_title: 'TCL FreshIN TAC-12CHSD/FBI, полный комплект', product_slug: 'tcl-freshin', product_kind: 'complete_split_system' as const, is_published: true, price: 1890 }],
  placements: [
    { id: 7, surface_key: 'home', slot_key: 'featured_products', position: 0, is_enabled: true, display_mode: 'grid' as const, grid_columns: 4 },
    { id: 8, surface_key: 'catalog', slot_key: 'before_products', position: 0, is_enabled: true, display_mode: 'carousel' as const },
  ],
};

const deferred = <T>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

const previewResult = (title: string, displayMode: 'grid' | 'carousel' = 'grid') => ({
  collection_id: 41,
  collection_slug: 'master-choice',
  below_min_items: false,
  display_mode: displayMode,
  items: [{
    position: 0,
    selection_source: 'manual' as const,
    product: { id: title.length, title, price: 2000, main_image: null },
  }],
});

describe('product collections workspace navigation', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/manager/product-collections?collectionId=41');
    mocks.list.mockResolvedValue({ items: [collection] });
    mocks.options.mockResolvedValue({ brands: [], series: [], features: [] });
    mocks.create.mockResolvedValue({ ...collection, id: 52, status: 'draft' });
    mocks.save.mockResolvedValue(collection);
    mocks.preview.mockResolvedValue(previewResult('Сохранённый товар'));
  });
  afterEach(() => { vi.clearAllMocks(); window.history.replaceState({}, '', '/manager/product-collections'); });

  it('opens the collection from its URL and keeps the full product title readable', async () => {
    const wrapper = mount(ProductCollectionsView);
    await flushPromises();
    expect(wrapper.get('[data-testid="product-collection-editor"]').text()).toContain('TCL FreshIN TAC-12CHSD/FBI, полный комплект');
    expect(window.location.search).toContain('collectionId=41');
    wrapper.unmount();
  });

  it('offers a separate, read-only placement overview', async () => {
    window.history.replaceState({}, '', '/manager/product-collections');
    const wrapper = mount(ProductCollectionsView);
    await flushPromises();
    await wrapper.get('button:nth-of-type(2)').trigger('click');
    expect(wrapper.text()).toContain('home / featured_products');
    expect(wrapper.text()).toContain('Выбор мастера для дома');
    wrapper.unmount();
  });

  it('retains the created draft id when the first workspace save fails and retries atomically', async () => {
    const draft = { ...collection, id: 52, slug: 'new-draft', status: 'draft' as const, items: [], placements: [] };
    window.history.replaceState({}, '', '/manager/product-collections');
    mocks.list.mockResolvedValueOnce({ items: [] }).mockResolvedValue({ items: [draft] });
    mocks.create.mockResolvedValue(draft);
    mocks.save.mockRejectedValueOnce(new Error('workspace failed')).mockResolvedValueOnce(draft);
    const wrapper = mount(ProductCollectionsView);
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text().includes('Создать'))!.trigger('click');
    await wrapper.find('button.save-button').trigger('click');
    await flushPromises();

    expect(mocks.create).toHaveBeenCalledOnce();
    expect(mocks.save).toHaveBeenNthCalledWith(1, 52, expect.any(Object));
    expect(wrapper.text()).toContain('workspace failed');

    await wrapper.find('button.save-button').trigger('click');
    await flushPromises();
    expect(mocks.create).toHaveBeenCalledOnce();
    expect(mocks.save).toHaveBeenNthCalledWith(2, 52, expect.any(Object));
    wrapper.unmount();
  });

  it('sends collection settings, items, and placements in one workspace payload', async () => {
    const wrapper = mount(ProductCollectionsView);
    await flushPromises();
    const editor = wrapper.getComponent(ProductCollectionEditor);
    Object.assign(editor.props('form'), {
      public_title: 'Обновлённый заголовок',
      mode: 'hybrid',
      min_items: 2,
      max_items: 9,
      fallback_collection_id: 77,
      sort_mode: 'price_asc',
    });
    editor.vm.$emit('update:items', [{ ...collection.items[0], is_pinned: false, editorial_note: 'Новая заметка' }]);
    editor.vm.$emit('update:placements', [{
      surface_key: 'catalog', slot_key: 'after_products', position: 3, is_enabled: true,
      display_mode: 'tiles', grid_columns: 3, item_limit: 5, rotation_mode: 'none',
    }]);
    await wrapper.vm.$nextTick();
    await wrapper.find('button.save-button').trigger('click');
    await flushPromises();

    expect(mocks.save).toHaveBeenCalledWith(41, {
      collection: expect.objectContaining({
        public_title: 'Обновлённый заголовок', mode: 'hybrid', min_items: 2,
        max_items: 9, fallback_collection_id: 77, sort_mode: 'price_asc',
      }),
      items: [{ product_id: 5, is_pinned: false, editorial_note: 'Новая заметка' }],
      placements: [expect.objectContaining({
        surface_key: 'catalog', slot_key: 'after_products', position: 3,
        display_mode: 'tiles', grid_columns: 3, item_limit: 5,
      })],
    });
    wrapper.unmount();
  });

  it('ignores a stale preview response after another placement was selected', async () => {
    const first = deferred<any>();
    const second = deferred<any>();
    mocks.preview.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const wrapper = mount(ProductCollectionsView);
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text() === 'Предпросмотр')!.trigger('click');
    await wrapper.get('[data-testid="collection-preview"] select').setValue('1');
    second.resolve(previewResult('Новый результат', 'carousel'));
    await flushPromises();
    first.resolve(previewResult('Устаревший результат'));
    await flushPromises();

    expect(wrapper.get('[data-testid="collection-preview"]').text()).toContain('Новый результат');
    expect(wrapper.get('[data-testid="collection-preview"]').text()).not.toContain('Устаревший результат');
    wrapper.unmount();
  });

  it('does not start a second atomic save while the first request is pending', async () => {
    const pending = deferred<any>();
    mocks.save.mockReturnValue(pending.promise);
    const wrapper = mount(ProductCollectionsView);
    await flushPromises();
    const saveButton = wrapper.get('button.save-button');
    await saveButton.trigger('click');
    await saveButton.trigger('click');

    expect(mocks.save).toHaveBeenCalledOnce();
    expect(saveButton.attributes('disabled')).toBeDefined();
    pending.resolve(collection);
    await flushPromises();
    wrapper.unmount();
  });
});
