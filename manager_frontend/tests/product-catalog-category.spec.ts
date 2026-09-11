import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProductEditModal from '../src/components/ProductEditModal.vue';
import type { Product } from '../src/api';

const api = vi.hoisted(() => ({
  getAllTags: vi.fn(), listManagerBrands: vi.fn(), getProductSupplierOffers: vi.fn(),
  updateProduct: vi.fn(), createProduct: vi.fn(), duplicateProduct: vi.fn(),
}));
vi.mock('../src/api', () => ({ api }));
vi.mock('../src/composables/useSpecRegistry', () => ({
  useSpecRegistry: () => ({
    loadSpecRegistry: async () => {},
    isHiddenSpecKey: (key: string) => key.startsWith('__'),
    normalizeValueForEdit: (_key: string, value: unknown) => String(value ?? ''),
    serializeSpecValue: (_key: string, value: unknown) => value,
  }),
}));

const categoryTags = [
  { id: 1, slug: 'cat-industrial', title: 'Полупромышленные' },
  { id: 2, slug: 'cat-household', title: 'Бытовые' },
  { id: 3, slug: 'cat-multi', title: 'Мульти-сплит' },
];
const product = (overrides: Partial<Product> = {}): Product => ({
  id: 1431, title: 'TCL Console Inverter', slug: 'tcl-console', price: 2400,
  old_price: 2500, product_kind: 'complete_split_system', is_published: true,
  is_inverter: true, catalog_category: 'cat-industrial', catalog_category_override: null,
  specs: { type: 'сплит-система', indoor_type: 'консольный' },
  tags: [categoryTags[0]!, { id: 4, slug: 'wifi-ready', title: 'Wi-Fi опция' }],
  ...overrides,
});

const mountEditor = async (source = product(), mode: 'edit' | 'duplicate' = 'edit') => {
  const wrapper = mount(ProductEditModal, {
    props: { modelValue: true, product: source, mode, presentation: 'workspace', workspaceSection: 'main' },
    global: { stubs: { ProductSpecificationsEditor: true, ProductSuppliersEditor: true, ProductSeriesSelector: true } },
  });
  await flushPromises();
  return wrapper;
};
type Editor = Awaited<ReturnType<typeof mountEditor>>;
const categoryButton = (wrapper: Editor, label: string) => wrapper.get('[data-testid="product-catalog-category"]')
  .findAll('button').find(button => button.text() === label)!;
const save = (wrapper: Editor) => (wrapper.vm as unknown as { save: () => Promise<boolean> }).save();

describe('Product catalog group editing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getAllTags.mockResolvedValue([
      { id: 1, slug: 'category', title: 'Категория', color: 'primary', allow_multiple: false, tags: categoryTags },
      { id: 2, slug: 'wifi', title: 'Wi-Fi', color: 'info', allow_multiple: false, tags: [{ id: 4, slug: 'wifi-ready', title: 'Wi-Fi опция' }] },
    ]);
    api.listManagerBrands.mockResolvedValue({ items: [] });
    api.getProductSupplierOffers.mockResolvedValue({ items: [] });
    api.updateProduct.mockResolvedValue({ id: 1431 });
    api.duplicateProduct.mockResolvedValue({ id: 2000 });
  });

  it('moves a legacy industrial product through an explicit group without changing its kind or specifications', async () => {
    const wrapper = await mountEditor();
    expect(categoryButton(wrapper, 'Авто').attributes('aria-pressed')).toBe('true');
    expect(wrapper.text()).toContain('Сейчас в каталоге: Полупромышленные');
    await categoryButton(wrapper, 'Бытовые').trigger('click');
    expect(categoryButton(wrapper, 'Бытовые').attributes('aria-pressed')).toBe('true');
    expect(wrapper.emitted('dirty-change')?.at(-1)).toEqual([true]);
    expect(await save(wrapper)).toBe(true);
    expect(api.updateProduct).toHaveBeenCalledWith(1431, expect.objectContaining({
      catalog_category_override: 'cat-household', product_kind: 'complete_split_system',
      price: 2400, old_price: 2500, specs: expect.objectContaining({ indoor_type: 'консольный' }),
      tag_ids: [1, 4],
    }));
    wrapper.unmount();
  });

  it('restores a saved manual choice and explicitly resets it to automatic', async () => {
    const wrapper = await mountEditor(product({ catalog_category: 'cat-household', catalog_category_override: 'cat-household' }));
    expect(categoryButton(wrapper, 'Бытовые').attributes('aria-pressed')).toBe('true');
    await categoryButton(wrapper, 'Авто').trigger('click');
    await save(wrapper);
    expect(api.updateProduct.mock.calls[0]![1]).toHaveProperty('catalog_category_override', null);
    wrapper.unmount();
  });

  it('does not reset group assignment when another field is saved', async () => {
    const wrapper = await mountEditor();
    await wrapper.findAll('input[type="number"]')[0]!.setValue('2600');
    await save(wrapper);
    const payload = api.updateProduct.mock.calls[0]![1];
    expect(payload.price).toBe(2600);
    expect(payload).not.toHaveProperty('catalog_category_override');
    wrapper.unmount();
  });

  it('allows explicit recalculation for a product already in automatic mode', async () => {
    const wrapper = await mountEditor();
    await categoryButton(wrapper, 'Авто').trigger('click');
    expect(wrapper.emitted('dirty-change')?.at(-1)).toEqual([true]);
    await save(wrapper);
    expect(api.updateProduct.mock.calls[0]![1]).toHaveProperty('catalog_category_override', null);
    wrapper.unmount();
  });

  it('carries the explicit group into a duplicated card', async () => {
    const wrapper = await mountEditor(product({ catalog_category_override: 'cat-household' }), 'duplicate');
    await save(wrapper);
    expect(api.duplicateProduct).toHaveBeenCalledWith(1431, expect.objectContaining({ catalog_category_override: 'cat-household' }));
    wrapper.unmount();
  });

  it('retains the chosen group after a save error and retries the same correction', async () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => {});
    api.updateProduct.mockRejectedValueOnce({ body: { detail: {
      message: 'Проверьте группу', field_errors: { catalog_category_override: 'Не удалось сохранить группу' },
    } } });
    const wrapper = await mountEditor();
    await categoryButton(wrapper, 'Бытовые').trigger('click');
    expect(await save(wrapper)).toBe(false);
    expect(wrapper.get('[role="alert"]').text()).toBe('Не удалось сохранить группу');
    expect(categoryButton(wrapper, 'Бытовые').attributes('aria-pressed')).toBe('true');
    expect(wrapper.emitted('success')).toBeUndefined();
    expect(await save(wrapper)).toBe(true);
    expect(api.updateProduct.mock.calls[1]![1]).toHaveProperty('catalog_category_override', 'cat-household');
    wrapper.unmount();
    log.mockRestore();
  });
});
