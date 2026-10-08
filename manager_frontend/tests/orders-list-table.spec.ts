import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import type { ManagerOrderListItemResponse } from '../src/client';
import type { OrderRenderItem } from '../src/components/orders/order-utils';
import OrderCardB2B from '../src/components/orders/OrderCardB2B.vue';
import OrderCardB2C from '../src/components/orders/OrderCardB2C.vue';
import OrderCustomerGroupCard from '../src/components/orders/OrderCustomerGroupCard.vue';
import OrderMoney from '../src/components/orders/OrderMoney.vue';
import { formatMoney, type CustomerOrderGroup } from '../src/components/orders/order-utils';
import OrderListRow from '../src/components/orders/OrderListRow.vue';
import OrdersListTable from '../src/components/orders/OrdersListTable.vue';
import OrdersViewToggle from '../src/components/orders/OrdersViewToggle.vue';
import { managerSession } from '../src/services/manager-session';

const order = (overrides: Partial<ManagerOrderListItemResponse> = {}): ManagerOrderListItemResponse => ({
  id: 501,
  status: 'negotiation',
  title: 'Проект кондиционирования офиса',
  created_at: '2026-09-10T10:00:00+03:00',
  next_followup_date: '2026-09-16',
  installation_date: '2026-09-22',
  total_amount: 12500,
  total_cost: 9000,
  margin: 3500,
  is_paid: false,
  balance_due: 7000,
  negotiation_status: 'awaiting_signature',
  needs_attention: false,
  awaiting_measurement: false,
  client_thinking: false,
  ready_for_execution: false,
  customer: {
    id: 10,
    type: 'company',
    name: 'ООО Северный ветер',
    phone: '+375291112233',
    inn: '123456789',
  },
  ...overrides,
});

describe('orders list table', () => {
  afterEach(() => { managerSession.auth.value = null; });
  it('keeps the order ID, one client line, and the exact negotiation substatus visible', () => {
    const wrapper = mount(OrderListRow, { props: { order: order(), segment: 'b2b', selectable: true } });

    expect(wrapper.text()).toContain('#501');
    expect(wrapper.text()).toContain('Переговоры');
    expect(wrapper.text()).toContain('Ожидаем договор');
    expect(wrapper.text()).toContain('Касание: 16.09.2026');
    expect(wrapper.text()).toContain('Работы: 22.09.2026');
    expect(wrapper.text().match(/ООО Северный ветер/g)).toHaveLength(1);
    expect(wrapper.text()).toContain('7 000 BYN');
  });

  it('uses the customer as the primary title once when an order has no title', () => {
    const wrapper = mount(OrderListRow, { props: { order: order({ title: null }), segment: 'b2b' } });

    expect(wrapper.text().match(/ООО Северный ветер/g)).toHaveLength(1);
    expect(wrapper.findAll('p.line-clamp-2')).toHaveLength(1);
    expect(wrapper.get('p.line-clamp-2').attributes('title')).toContain('ООО Северный ветер');
  });

  it('expands a customer group, selects all its orders, and forwards row actions', async () => {
    const first = order();
    const second = order({ id: 502, status: 'execution', execution_status: 'scheduled', balance_due: 0 });
    const items: OrderRenderItem[] = [{
      type: 'group',
      group: {
        id: 'customer-10-501-502',
        customerId: 10,
        customerName: 'ООО Северный ветер',
        originalCustomerName: 'ООО Северный ветер',
        orders: [first, second],
        totalAmount: 12500,
        margin: 3500,
        balanceDue: 7000,
        statusCounts: [{ status: 'negotiation', count: 1 }, { status: 'execution', count: 1 }],
        addresses: [],
        hiddenAddressCount: 0,
        hasOverdue: false,
        needsAttention: false,
      },
    }];
    const wrapper = mount(OrdersListTable, { props: { items, segment: 'b2b' } });

    expect(wrapper.text()).toContain('Сводка по клиенту');
    expect(wrapper.text()).not.toContain('#501');
    await wrapper.find('tbody tr button').trigger('click');
    expect(wrapper.text()).toContain('#501');
    expect(wrapper.text()).toContain('Работы назначены');

    await wrapper.find('input[aria-label="Выбрать группу ООО Северный ветер"]').setValue(true);
    expect(wrapper.emitted('toggleSelectMany')).toEqual([[{ orderIds: [501, 502], selected: true }]]);

    const firstOpen = wrapper.findAll('button').find((button) => button.text() === 'Открыть');
    await firstOpen!.trigger('click');
    expect(wrapper.emitted('open')).toEqual([[501]]);
  });

  it('shows direct named view controls and emits the existing list value', async () => {
    const wrapper = mount(OrdersViewToggle, { props: { modelValue: 'kanban' } });
    const tableButton = wrapper.get('button[aria-label="Таблица"]');

    expect(tableButton.attributes('aria-pressed')).toBe('false');
    await tableButton.trigger('click');
    expect(wrapper.emitted('update:modelValue')).toEqual([['list']]);
  });

  it('sorts contact and margin explicitly while keeping amount non-sortable', async () => {
    const wrapper = mount(OrdersListTable, { props: { items: [{ type: 'order', order: order() }], segment: 'b2b' } });

    expect(wrapper.text()).toContain('Контакт');
    expect(wrapper.text()).toContain('Маржа ↕');
    await wrapper.get('th:nth-child(4) button').trigger('click');
    await wrapper.get('th:nth-child(5) button').trigger('click');

    expect(wrapper.emitted('update:sort')).toEqual([['followup_asc'], ['margin_desc']]);
  });

  it('does not render or sort margin in the read-only demo', () => {
    managerSession.auth.value = { demo_read_only: true } as any;
    const wrapper = mount(OrdersListTable, { props: { items: [{ type: 'order', order: order() }], segment: 'b2b' } });

    expect(wrapper.text()).not.toContain('Маржа');
    expect(wrapper.text()).toContain('12 500 BYN');
  });
});


describe('order list money presentation', () => {
  afterEach(() => { managerSession.auth.value = null; });
  const group = (value: number): CustomerOrderGroup => ({
    id: 'money-group', customerId: 10, customerName: 'Клиент', originalCustomerName: 'Клиент',
    orders: [order()], totalAmount: value, margin: value, balanceDue: value,
    statusCounts: [], addresses: [], hiddenAddressCount: 0, hasOverdue: false, needsAttention: false,
  });
  const callers = (value: number | null) => [
    mount(OrderCardB2B, { props: { order: order({ total_amount: value as number, margin: value, balance_due: 0 }), expanded: true } }),
    mount(OrderCardB2C, { props: { order: order({ total_amount: value as number, margin: value, balance_due: 0 }), expanded: true } }),
    mount(OrderListRow, { props: { order: order({ total_amount: value as number, margin: value, balance_due: 0 }), segment: 'b2b' } }),
  ];
  const allCallers = (value: number) => [...callers(value),
    mount(OrderCustomerGroupCard, { props: { group: group(value), segment: 'b2b', expanded: false, movingOrderIds: [], expandedOrderId: null } }),
    mount(OrdersListTable, { props: { items: [{ type: 'group', group: group(value) }], segment: 'b2b' } }),
  ];
  it.each([0, -12.34, 0.01, 10.001, 123456789.12])('preserves raw amount %s, precision and selectable BYN across all five callers', value => {
    for (const wrapper of allCallers(value)) {
      const money = wrapper.findAllComponents(OrderMoney);
      expect(money.length).toBeGreaterThanOrEqual(2);
      expect(money[0]!.text()).toBe(formatMoney(value));
      expect(money[1]!.text()).toBe(formatMoney(value));
      for (const field of money) {
        expect(field.get('.sr-only').text()).toBe('BYN');
        expect(field.get('svg').attributes('aria-hidden')).toBe('true');
      }
      wrapper.unmount();
    }
  });
  it('shows unknown source total and margin as missing while retaining a computed zero balance', () => {
    for (const wrapper of callers(null)) {
      const money = wrapper.findAllComponents(OrderMoney);
      expect(money[0]!.text()).toBe('—');
      expect(money[1]!.text()).toBe('—');
      expect(money[0]!.attributes('aria-label')).toBe('Нет данных');
      if (money.length === 3) expect(money[2]!.text()).toBe('0 BYN');
      wrapper.unmount();
    }
  });
  for (const [name, component] of [['B2B', OrderCardB2B], ['B2C', OrderCardB2C]] as const) {
    it(`retains payment branches and expansion interactions for ${name}`, async () => {
      const wrapper = mount(component, { props: { order: order({ balance_due: 0.01 }), expanded: false } });
      expect(wrapper.findAllComponents(OrderMoney)).toHaveLength(1);
      expect(wrapper.text()).toContain('Остаток: 0,01 BYN');
      await wrapper.get('article').trigger('click');
      expect(wrapper.emitted('toggleExpanded')).toEqual([[501]]);
      await wrapper.setProps({ expanded: true });
      expect(wrapper.findAllComponents(OrderMoney)).toHaveLength(3);
      await wrapper.setProps({ order: order({ balance_due: -1 }) });
      expect(wrapper.text()).toContain('Оплачено');
      await wrapper.setProps({ order: order({ total_amount: 0, balance_due: 0 }) });
      expect(wrapper.text()).toContain('Без суммы');
      wrapper.unmount();
    });
  }
  it('keeps demo margins hidden in all five callers', () => {
    managerSession.auth.value = { demo_read_only: true } as any;
    for (const wrapper of allCallers(10)) {
      expect(wrapper.text()).not.toContain('Маржа:');
      wrapper.unmount();
    }
  });
});
