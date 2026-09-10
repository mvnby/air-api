import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import OrderCustomerContext from '../src/components/orders/OrderCustomerContext.vue';

const suggestAddress = vi.hoisted(() => vi.fn());

const apiMock = vi.hoisted(() => ({
  createManagerCustomerBranch: vi.fn(),
  getManagerCustomerBranches: vi.fn(),
  getManagerCustomers: vi.fn(),
  patchManagerCustomer: vi.fn(),
  patchManagerOrder: vi.fn(),
}));

vi.mock('../src/api', () => ({ api: apiMock }));
vi.mock('../src/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/client')>()),
  ManagerSettingsService: { suggestAddress },
}));

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

const companyOrder = {
  ...order,
  customer: {
    id: 12,
    type: 'company',
    name: 'ООО Альфа',
    full_legal_name: 'ООО «Альфа»',
    phone: '+375291112233',
    email: 'office@example.test',
  },
} as ManagerOrderDetailResponse;

const mountCompanyContext = () => {
  const wrapper = mount(OrderCustomerContext, {
    props: {
      order: companyOrder,
      deliveryAddress: '',
      customerBranchId: null,
      comment: '',
      expanded: true,
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
  suggestAddress.mockResolvedValue({ items: [] });
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

  it('offers company-name address suggestions only after an explicit request and selection', async () => {
    suggestAddress.mockResolvedValue({
      items: [{ value: 'Минск, проспект Победителей, 1', title: 'Минск, проспект Победителей, 1' }],
    });
    const wrapper = mountCompanyContext();
    await flushPromises();

    expect(suggestAddress).not.toHaveBeenCalled();
    expect(wrapper.get('[data-testid="suggest-company-address"]').text()).toContain('Подобрать адрес');

    await wrapper.get('[data-testid="suggest-company-address"]').trigger('click');
    await flushPromises();

    expect(suggestAddress).toHaveBeenCalledWith('ООО «Альфа»');
    expect(wrapper.emitted('update:deliveryAddress')).toBeUndefined();
    await wrapper.get('[data-testid="company-address-candidate-Минск, проспект Победителей, 1"]').trigger('click');
    expect(wrapper.emitted('update:deliveryAddress')).toContainEqual(['Минск, проспект Победителей, 1']);
  });

  it('does not offer company-name suggestions to an individual customer', async () => {
    const wrapper = mountContext();
    await flushPromises();

    expect(wrapper.find('[data-testid="suggest-company-address"]').exists()).toBe(false);
  });

  it('does not overwrite a branch selected while a refreshed branch list is loading', async () => {
    const wrapper = mountContext();
    await flushPromises();
    await wrapper.setProps({ customerBranchId: 32 });
    const updatesBeforeRefresh = wrapper.emitted('update:customerBranchId')?.length || 0;

    let resolveBranches: ((value: { items: typeof branches }) => void) | undefined;
    apiMock.getManagerCustomerBranches.mockImplementationOnce(() => new Promise((resolve) => {
      resolveBranches = resolve;
    }));
    await wrapper.setProps({
      order: { ...order, customer_branch: branches[0] },
    });

    resolveBranches?.({ items: branches });
    await flushPromises();

    expect(wrapper.props('customerBranchId')).toBe(32);
    expect(wrapper.emitted('update:customerBranchId')?.slice(updatesBeforeRefresh) || []).toEqual([]);
  });
});
