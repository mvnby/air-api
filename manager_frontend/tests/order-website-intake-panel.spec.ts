import { mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import OrderWebsiteIntakePanel from '../src/components/orders/OrderWebsiteIntakePanel.vue';

const order = {
  id: 42,
  status: 'new_lead',
  created_at: '2026-07-31T10:00:00Z',
  total_amount: 3_200,
  total_cost: 2_000,
  margin: 1_200,
  is_paid: false,
  customer: {
    id: 11,
    name: 'Анна',
    phone: '+375291112233',
    email: 'anna@example.test',
  },
  product_lines: [{
    id: 101,
    product_id: 501,
    product_title: 'Кондиционер',
    quantity: 1,
    price: 3_000,
    cost: 2_000,
    line_total: 3_000,
    is_installation_included: true,
    installation_price: 300,
  }],
  service_lines: [{
    id: 102,
    service_title: 'Доставка',
    quantity: 1,
    price: 200,
    cost: 0,
    line_total: 200,
  }],
  needs_attention: false,
  awaiting_measurement: false,
  client_thinking: false,
  ready_for_execution: false,
} as ManagerOrderDetailResponse;

const mountedWrappers: VueWrapper[] = [];

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
});

describe('OrderWebsiteIntakePanel', () => {
  it('renders the immutable website intake summary and delegates copy actions', async () => {
    const wrapper = mount(OrderWebsiteIntakePanel, {
      props: {
        order,
        expanded: true,
        deliveryAddress: 'Минск, пр-т Победителей, 1',
        comment: 'Позвонить перед доставкой',
      },
    });
    mountedWrappers.push(wrapper);

    expect(wrapper.text()).toContain('2 поз.');
    expect(wrapper.text()).toContain('Кондиционер');
    expect(wrapper.text()).toContain('Монтаж включен');
    expect(wrapper.text()).toContain('Доставка');
    expect(wrapper.text()).toContain('Позвонить перед доставкой');

    const copyButtons = wrapper.findAll('button').filter((button) => (
      button.text().includes('Телефон') || button.text().includes('Адрес')
    ));
    await copyButtons[0]?.trigger('click');
    await copyButtons[1]?.trigger('click');

    expect(wrapper.emitted('copy')).toEqual([
      [{ value: '+375291112233', label: 'Телефон' }],
      [{ value: 'Минск, пр-т Победителей, 1', label: 'Адрес' }],
    ]);
  });

  it('keeps the section disclosure controlled by the parent', async () => {
    const wrapper = mount(OrderWebsiteIntakePanel, {
      props: {
        order,
        expanded: false,
        deliveryAddress: '',
        comment: '',
      },
    });
    mountedWrappers.push(wrapper);

    expect(wrapper.text()).not.toContain('Состав заказа');
    await wrapper.get('button[aria-expanded="false"]').trigger('click');
    expect(wrapper.emitted('update:expanded')).toEqual([[true]]);
  });
});
