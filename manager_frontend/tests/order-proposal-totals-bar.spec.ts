import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import OrderProposalTotalsBar from '../src/components/orders/OrderProposalTotalsBar.vue';
import type { ProductLine, ServiceLine } from '../src/components/orders/order-editor-types';

const products: ProductLine[] = [{
  product_id: 101,
  product_query: 'Кондиционер',
  quantity: 2,
  price: 1_000,
  cost: 700,
}];

const services: ServiceLine[] = [
  { service_id: 1, title: 'Монтаж', quantity: 2, price: 500, cost: 300 },
  {
    service_id: 2,
    title: 'Свернутая зафиксированная установка',
    quantity: 1,
    price: 3_000,
    cost: 2_100,
    installation_estimate_revision_id: 55,
    installation_projection_mode: 'collapsed',
    installation_display_lines: [
      { title: 'Установка №1', description: 'Трасса 3 м', quantity: 1, price: 600 },
      { title: 'Установка №2', description: 'Трасса 3 м', quantity: 4, price: 600 },
    ],
  },
];

const normalizedText = (value: string) => value.replace(/\s/g, '');

describe('OrderProposalTotalsBar', () => {
  it('totals line quantity times price and cost, including a collapsed frozen service aggregate', () => {
    const wrapper = mount(OrderProposalTotalsBar, {
      props: { products, services, showCosts: true, actionLabel: 'Далее' },
    });
    const text = normalizedText(wrapper.text());

    expect(text).toContain('6000BYN');
    expect(text).toContain('Себестоимость:4\u00a0100BYN'.replace(/\s/g, ''));
    expect(text).toContain('Прибыль:1\u00a0900BYN'.replace(/\s/g, ''));
    expect(text).toContain('Маржа:31.7%');
    expect(normalizedText(wrapper.get('[data-testid="proposal-grand-total"]').text())).toBe('6000BYN');
  });

  it('hides costs and the primary action in preview while keeping the grand total', () => {
    const wrapper = mount(OrderProposalTotalsBar, {
      props: { products, services, showCosts: true, preview: true, actionLabel: 'Далее' },
    });

    expect(normalizedText(wrapper.get('[data-testid="proposal-grand-total"]').text())).toBe('6000BYN');
    expect(wrapper.find('[data-testid="proposal-cost-metrics"]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('Себестоимость');
    expect(wrapper.find('button').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('Далее');
  });

  it('disables next while busy and emits next only after it becomes available', async () => {
    const wrapper = mount(OrderProposalTotalsBar, {
      props: { products, services, busy: true, actionLabel: 'Продолжить' },
    });
    const next = wrapper.get('button');

    expect((next.element as HTMLButtonElement).disabled).toBe(true);
    await next.trigger('click');
    expect(wrapper.emitted('next')).toBeUndefined();

    await wrapper.setProps({ busy: false });
    await wrapper.get('button').trigger('click');
    expect(wrapper.emitted('next')).toEqual([[]]);
  });

  it('shows zero totals and zero margin for an empty proposal', () => {
    const wrapper = mount(OrderProposalTotalsBar, {
      props: { products: [], services: [], showCosts: true, actionLabel: 'Далее' },
    });
    const text = normalizedText(wrapper.text());

    expect(normalizedText(wrapper.get('[data-testid="proposal-grand-total"]').text())).toBe('0BYN');
    expect(text).toContain('Себестоимость:0BYN');
    expect(text).toContain('Прибыль:0BYN');
    expect(text).toContain('Маржа:0.0%');
  });

  it('keeps the total consistent with the saved price rounded to cents', () => {
    const wrapper = mount(OrderProposalTotalsBar, {
      props: { products: [{ ...products[0]!, quantity: 500, price: 10.234 }], services: [], actionLabel: 'Далее' },
    });
    expect(normalizedText(wrapper.get('[data-testid="proposal-grand-total"]').text())).toBe('5115BYN');
  });
});
