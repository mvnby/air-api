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
