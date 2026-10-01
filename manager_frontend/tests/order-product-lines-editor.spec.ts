import { mount } from '@vue/test-utils';
import { nextTick } from 'vue';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import OrderProductLinesEditor from '../src/components/orders/OrderProductLinesEditor.vue';
import type { ProductLine, ProductOption } from '../src/components/orders/order-editor-types';
import { managerSession } from '../src/services/manager-session';

const line = (overrides: Partial<ProductLine> = {}): ProductLine => ({
  link_id: 41,
  product_id: 501,
  product_query: 'Gree Pular',
  client_description: 'Инвертор; площадь: 35 м²',
  quantity: 2,
  price: 1_500,
  cost: 1_000,
  ...overrides,
});

const option: ProductOption = {
  id: 502,
  title: 'Gree Fairy',
  price: 1_700,
  cost: 1_100,
  product_kind: 'conditioner',
  is_inverter: true,
  power_cooling: 2.5,
  availability_status: 'in_stock',
  vitebsk_qty: 2,
  minsk_qty: 1,
};

const props = (lines: ProductLine[], extra: Record<string, unknown> = {}) => ({
  lines,
  searchInStock: false,
  productOptions: [],
  productLookupById: {},
  productLookupLoading: false,
  activeSuggestionIndex: null,
  supplyActionLoadingLineId: null,
  supplyBadgeForLine: () => null,
  compact: true,
  ...extra,
});

beforeEach(() => {
  managerSession.auth.value = { capabilities: ['platform.manage'] } as any;
});

afterEach(() => {
  managerSession.auth.value = null;
});

describe('OrderProductLinesEditor compact mode', () => {
  it('keeps saved rows collapsed with readable details and no inputs', () => {
    const wrapper = mount(OrderProductLinesEditor, { props: props([line(), line({ link_id: 42 })]) });

    expect(wrapper.findAll('[data-testid="product-line-row"]')).toHaveLength(2);
    expect(wrapper.text()).toContain('Gree Pular');
    expect(wrapper.text()).toContain('Инвертор; площадь: 35 м²');
    expect(wrapper.findAll('[data-testid="product-line-row"] input, [data-testid="product-line-row"] textarea')).toHaveLength(0);
    expect(wrapper.findAll('[data-order-usage="order_product_edit"]')).toHaveLength(2);
    expect(wrapper.findAll('[data-order-usage="order_product_remove"]')).toHaveLength(2);
  });

  it('opens only the chosen row, applies v-model edits, and preserves selection events', async () => {
    const first = line({ product_id: 0, product_query: 'Gr' });
    const second = line({ link_id: 42, product_query: 'Midea' });
    const wrapper = mount(OrderProductLinesEditor, {
      props: props([first, second], { productOptions: [option], activeSuggestionIndex: 0 }),
    });

    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    expect(wrapper.findAll('textarea')).toHaveLength(2);
    expect(wrapper.get('[data-testid="select-product-502"]').exists()).toBe(true);

    const price = wrapper.find('input[type="number"]');
    await price.setValue('1800');
    expect(first.price).toBe(1800);

    await wrapper.get('[data-testid="select-product-502"]').trigger('click');
    expect(wrapper.emitted('select')).toEqual([[{ index: 0, option }]]);
    await wrapper.get('[aria-label="Готово: товар #1"]').trigger('click');
    expect(wrapper.findAll('textarea')).toHaveLength(0);
  });

  it('marks catalog discounts and markups only on collapsed rows with accessible reference details', async () => {
    const discounted = line({ price: 2_480 });
    const wrapper = mount(OrderProductLinesEditor, {
      props: props([discounted], { productLookupById: { 501: { ...option, id: 501, price: 2_690 } } }),
    });
    const discount = wrapper.get('[data-testid="product-price-adjustment"]');

    expect(discount.text()).toBe('↓ Скидка 7,8%');
    expect(discount.attributes('title')?.replace(/\s/g, '')).toBe(
      'Скидка210BYN(7,8%)относительнокаталожнойцены2690BYN',
    );
    expect(discount.attributes('aria-label')).toBe(discount.attributes('title'));

    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    expect(wrapper.find('[data-testid="product-price-adjustment"]').exists()).toBe(false);
    await wrapper.find('input[type="number"]').setValue('2790');
    await wrapper.get('[aria-label="Готово: товар #1"]').trigger('click');
    expect(discounted.price).toBe(2_790);
    expect(wrapper.get('[data-testid="product-price-adjustment"]').text()).toBe('↑ Наценка 3,7%');
    expect(wrapper.get('[data-testid="product-price-adjustment"]').attributes('title')?.replace(/\s/g, ''))
      .toContain('Наценка100BYN(3,7%)относительнокаталожнойцены2690BYN');
  });

  it('omits the price marker for zero prices, matching prices, and missing catalog prices', () => {
    const wrapper = mount(OrderProductLinesEditor, {
      props: props([
        line({ link_id: 1, product_id: 501, price: 0 }),
        line({ link_id: 2, product_id: 501, price: 2_690 }),
        line({ link_id: 3, product_id: 777, price: 2_480 }),
      ], { productLookupById: { 501: { ...option, id: 501, price: 2_690 } } }),
    });

    expect(wrapper.findAll('[data-testid="product-price-adjustment"]')).toHaveLength(0);
  });

  it('does not treat a fallback lookup value as a known catalog price', async () => {
    const unknownCatalogPrice = { ...option, id: 501, price: 2_690, catalog_price_known: false };
    const wrapper = mount(OrderProductLinesEditor, {
      props: props([
        line({ link_id: 1, product_id: 501, price: 2_480 }),
        line({ link_id: 2, product_id: 501, price: 2_690 }),
      ], { productLookupById: { 501: unknownCatalogPrice } }),
    });

    expect(wrapper.findAll('[data-testid="product-price-adjustment"]')).toHaveLength(0);
    await wrapper.setProps({ compact: false });
    expect(wrapper.text()).not.toContain('Цена строки отличается от каталожной');
  });

  it('allocates extra edit rows for long model names and retains the full text', async () => {
    const title = 'MS-12K-ABC Inverter Wi-Fi Climate Control Series Extended Model Name With Optional Enhanced Airflow Settings';
    const wrapper = mount(OrderProductLinesEditor, { props: props([line({ product_query: title })]) });

    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    const nameField = wrapper.findAll('textarea')[0];
    expect((nameField.element as HTMLTextAreaElement).rows).toBeGreaterThanOrEqual(3);
    expect((nameField.element as HTMLTextAreaElement).value).toBe(title);
    expect(nameField.classes()).toContain('min-w-0');
    expect(nameField.classes()).toContain('w-full');
    expect(wrapper.findAll('input[type="number"]').every((input) => input.classes().includes('min-w-0'))).toBe(true);
  });

  it('opens a newly appended empty line and closes when the edited line leaves the array', async () => {
    const original = line();
    const wrapper = mount(OrderProductLinesEditor, { props: props([original]) });

    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    expect(wrapper.findAll('textarea')).toHaveLength(2);

    const emptyLine = line({ link_id: null, product_id: 0, product_query: '', client_description: null });
    await wrapper.setProps({ lines: [original, emptyLine] });
    expect(wrapper.findAll('textarea')).toHaveLength(2);
    expect(wrapper.get('[aria-label="Готово: товар #2"]').exists()).toBe(true);

    await wrapper.setProps({ lines: [line({ link_id: 99, product_query: 'Другой товар' })] });
    await nextTick();
    expect(wrapper.findAll('textarea')).toHaveLength(0);
  });

  it('shows cost only when requested and allowed by demo and capability permissions', async () => {
    const wrapper = mount(OrderProductLinesEditor, { props: props([line()], { showCosts: true }) });
    expect(wrapper.text()).toContain('Себест.');
    expect(wrapper.text()).toContain('1 000');

    await wrapper.setProps({ showCosts: false });
    expect(wrapper.text()).not.toContain('Себест.');

    managerSession.auth.value = { demo_read_only: true, capabilities: [] } as any;
    await wrapper.setProps({ showCosts: true });
    expect(wrapper.text()).not.toContain('Себест.');
    await wrapper.get('[aria-label="Редактировать товар #1"]').trigger('click');
    expect(wrapper.findAll('input[type="number"]')).toHaveLength(2);
    expect(wrapper.text()).not.toContain('В поставку');
    expect(wrapper.text()).not.toContain('Забронировать');
  });
});
