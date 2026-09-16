import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import ProductCollectionEditor from '../src/components/product-collections/ProductCollectionEditor.vue';
import { emptyCollectionForm } from '../src/components/product-collections/product-collection-workspace';

const item = (overrides = {}) => ({
  id: 11,
  product_id: 5,
  position: 0,
  is_pinned: true,
  editorial_note: 'Показывать первым',
  product_title: 'Очень длинное полное название исходного товара без сокращения',
  product_slug: 'old-product',
  product_kind: 'complete_split_system' as const,
  is_published: true,
  price: 1800,
  main_image: null,
  ...overrides,
});

const active = {
  id: 41,
  slug: 'master-choice',
  internal_name: 'Выбор мастера',
  public_title: 'Выбор мастера',
  status: 'published' as const,
  tenant_id: 1,
  storefront_id: 1,
  created_at: '',
  updated_at: '',
  placements: [
    { id: 1, surface_key: 'home', slot_key: 'after_featured', position: 0, is_enabled: true, display_mode: 'grid' as const, grid_columns: 4 },
    { id: 2, surface_key: 'catalog', slot_key: 'before_products', position: 0, is_enabled: true, display_mode: 'carousel' as const },
  ],
};

const mountEditor = (overrides = {}) => mount(ProductCollectionEditor, {
  props: {
    active,
    form: emptyCollectionForm(),
    items: [item()],
    placements: active.placements,
    collections: [active],
    ruleOptions: { brands: [], series: [], features: [] },
    preview: null,
    previewSaved: true,
    canManagePlatform: true,
    searchResults: [{
      id: 8,
      title: 'Новый товар с полным названием',
      slug: 'new-product',
      product_kind: 'complete_split_system' as const,
      is_published: true,
      price: 2100,
      main_image: null,
    }],
    ...overrides,
  },
});

describe('product collection editor', () => {
  it('keeps formation controls on Products and preserves row metadata when replacing a product', async () => {
    const source = item();
    const wrapper = mountEditor({ items: [source] });
    expect(wrapper.get('[data-testid="collection-rules"]').text()).toContain('Как формируется подборка');

    await wrapper.findAll('button').find(button => button.text().includes('Заменить товар'))!.trigger('click');
    expect(wrapper.get('[data-testid="replacement-notice"]').text()).toContain(source.product_title);
    await wrapper.get('[data-testid="search-product"]').trigger('click');

    const rows = wrapper.emitted('update:items')!.at(-1)![0] as any[];
    expect(rows[0]).toMatchObject({
      id: 11,
      product_id: 8,
      position: 0,
      is_pinned: true,
      editorial_note: 'Показывать первым',
      product_title: 'Новый товар с полным названием',
    });
    expect(source).toMatchObject({ product_id: 5, product_title: 'Очень длинное полное название исходного товара без сокращения' });
  });

  it('loads the saved placement selected in the direct preview panel', async () => {
    const wrapper = mountEditor();
    await wrapper.findAll('button').find(button => button.text() === 'Предпросмотр')!.trigger('click');
    expect(wrapper.emitted('preview')?.[0]).toEqual(['home', 'after_featured']);
    expect(wrapper.get('[data-testid="collection-preview"]').text()).toContain('Главная · После основных подборок');

    await wrapper.get('[data-testid="collection-preview"] select').setValue('1');
    expect(wrapper.emitted('preview')?.[1]).toEqual(['catalog', 'before_products']);
  });

  it('does not allow replacement with a product already present in the collection', async () => {
    const existing = item({ id: 12, product_id: 8, position: 1, product_title: 'Уже в подборке' });
    const wrapper = mountEditor({ items: [item(), existing] });
    await wrapper.findAll('button').find(button => button.text().includes('Заменить товар'))!.trigger('click');
    await wrapper.get('[data-testid="search-product"]').trigger('click');
    expect(wrapper.emitted('update:items')).toBeUndefined();
  });

  it('disables editing controls while the atomic save is pending', () => {
    const wrapper = mountEditor({ saving: true });
    expect(wrapper.get('fieldset.contents').attributes('disabled')).toBeDefined();
    expect(wrapper.get('button.save-button').attributes('disabled')).toBeDefined();
  });

  it('shows collection and placement publication limits independently', async () => {
    const wrapper = mountEditor({
      active: {
        ...active,
        status: 'archived',
        starts_at: '2999-01-01T00:00:00Z',
        placements: [{
          ...active.placements[0],
          starts_at: '2020-01-01T00:00:00Z',
          ends_at: '2021-01-01T00:00:00Z',
        }],
      },
      preview: {
        collection_id: 41,
        collection_slug: 'master-choice',
        below_min_items: false,
        items: [],
      },
    });
    await wrapper.findAll('button').find(button => button.text() === 'Предпросмотр')!.trigger('click');
    const text = wrapper.get('[data-testid="collection-preview"]').text();
    expect(text).toContain('находится в архиве');
    expect(text).toContain('Показ подборки начнётся');
    expect(text).toContain('Показ в выбранном месте по сохранённому расписанию уже завершён');
  });
});
