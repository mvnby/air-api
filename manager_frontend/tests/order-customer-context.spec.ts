import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import OrderCustomerContext from '../src/components/orders/OrderCustomerContext.vue';

const apiMock = vi.hoisted(() => ({
  createManagerCustomerBranch: vi.fn(),
  getManagerCustomerBranches: vi.fn(),
  getManagerCustomers: vi.fn(),
  patchManagerCustomer: vi.fn(),
  patchManagerOrder: vi.fn(),
}));

vi.mock('../src/api', () => ({ api: apiMock }));

const order = {
  id: 42,
  status: 'new_lead',
  created_at: '2026-07-31T10:00:00Z',
  total_amount: 0,
  total_cost: 0,
  margin: 0,
  is_paid: false,
  customer: {
    id: 11,
    type: 'individual',
    name: 'Анна',
    phone: '+375291112233',
    email: 'anna@example.test',
  },
  customer_branch: null,
  product_lines: [],
  service_lines: [],
  needs_attention: false,
  awaiting_measurement: false,
  client_thinking: false,
  ready_for_execution: false,
} as ManagerOrderDetailResponse;

const branches = [
  {
    id: 31,
    customer_id: 11,
    name: 'Склад',
    delivery_address: 'Минск, ул. Складская, 1',
    is_default: true,
  },
  {
    id: 32,
    customer_id: 11,
    name: 'Офис',
    delivery_address: 'Минск, ул. Офисная, 2',
    is_default: false,
  },
];

const mountedWrappers: VueWrapper[] = [];

const mountContext = () => {
  const wrapper = mount(OrderCustomerContext, {
    props: {
      order,
      deliveryAddress: '',
      customerBranchId: null,
      comment: '',
      expanded: false,
      newBranchAddress: '',
    },
  });
  mountedWrappers.push(wrapper);
  return wrapper;
};

beforeEach(() => {
  apiMock.getManagerCustomerBranches.mockResolvedValue({ items: branches });
  apiMock.getManagerCustomers.mockResolvedValue({
    items: [{ id: 22, name: 'Новый клиент', phone: '+375291234567' }],
  });
  apiMock.patchManagerOrder.mockResolvedValue({
    ...order,
    customer: { id: 22, name: 'Новый клиент', phone: '+375291234567' },
  });
});

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('OrderCustomerContext', () => {
  it('loads branches and keeps branch selection coupled to the object address', async () => {
    const wrapper = mountContext();
    await flushPromises();

    expect(apiMock.getManagerCustomerBranches).toHaveBeenCalledWith(11);
    await wrapper.get('button[aria-label="Редактировать объект"]').trigger('click');
    await wrapper.findAll('button').find((button) => button.text().includes('Выбрать филиал'))?.trigger('click');
    await wrapper.get('[data-testid="customer-branch"]').setValue('32');

    expect(wrapper.emitted('update:customerBranchId')).toContainEqual([32]);
    expect(wrapper.emitted('update:deliveryAddress')).toContainEqual(['Минск, ул. Офисная, 2']);
  });

  it('searches and reassigns the customer through the order API', async () => {
    vi.useFakeTimers();
    const wrapper = mountContext();
    await flushPromises();

    await wrapper.get('button[aria-label="Редактировать клиента"]').trigger('click');
    await wrapper.findAll('button').find((button) => button.text().includes('Сменить клиента'))?.trigger('click');
    await wrapper.get('[data-testid="customer-search"]').setValue('Новый');
    await vi.advanceTimersByTimeAsync(450);
    await flushPromises();
    await wrapper.get('[data-testid="assign-customer-22"]').trigger('click');
    await flushPromises();

    expect(apiMock.getManagerCustomers).toHaveBeenCalledWith(1, 10, 'Новый');
    expect(apiMock.patchManagerOrder).toHaveBeenCalledWith(42, { customer_id: 22 });
    expect(wrapper.emitted('updated')?.[0]?.[0]).toEqual(expect.objectContaining({
      customer: expect.objectContaining({ id: 22 }),
    }));
    expect(wrapper.emitted('reload')).toEqual([[42]]);
  });
});
