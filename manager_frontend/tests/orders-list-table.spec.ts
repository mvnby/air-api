import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import type { ManagerOrderListItemResponse } from '../src/client';
import type { OrderRenderItem } from '../src/components/orders/order-utils';
import OrderListRow from '../src/components/orders/OrderListRow.vue';
import OrdersListTable from '../src/components/orders/OrdersListTable.vue';
import OrdersViewToggle from '../src/components/orders/OrdersViewToggle.vue';

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
});
