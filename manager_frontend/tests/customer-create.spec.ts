import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/api';
import CreateCustomerModal from '../src/components/customers/CreateCustomerModal.vue';
import CustomersView from '../src/views/CustomersView.vue';

const wrappers: VueWrapper[] = [];

const createdCustomer = {
  id: 42,
  name: 'Новый клиент',
  phone: null,
  email: null,
  type: 'individual',
  inn: null,
  full_legal_name: null,
  legal_address: null,
  iban: null,
  bic: null,
  bank_name: null,
  created_at: '2026-08-31T16:00:00Z',
  order_count: 0,
};

const mountModal = () => {
  const wrapper = mount(CreateCustomerModal, {
    global: {
      stubs: { teleport: true, transition: false },
    },
  });
  wrappers.push(wrapper);
  return wrapper;
};

beforeEach(() => {
  vi.spyOn(api, 'createManagerCustomer').mockResolvedValue(createdCustomer);
  vi.spyOn(api, 'getManagerCustomers').mockResolvedValue({
    items: [],
    meta: { page: 1, limit: 20, total: 0, pages: 1 },
  });
  sessionStorage.clear();
});

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.restoreAllMocks();
});

describe('CreateCustomerModal', () => {
  it('creates a sparse customer and returns the new profile', async () => {
    const wrapper = mountModal();

    await wrapper.get('[data-testid="customer-name"]').setValue('  Новый клиент  ');
    await wrapper.get('[data-testid="submit-customer"]').trigger('click');
    await flushPromises();

    expect(api.createManagerCustomer).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Новый клиент',
      type: 'individual',
      phone: '',
      email: '',
      signing_mode: 'self',
    }));
    expect(wrapper.emitted('created')?.[0]).toEqual([createdCustomer]);
  });

  it('offers the existing profile when the API detects a duplicate', async () => {
    vi.mocked(api.createManagerCustomer).mockRejectedValueOnce({
      status: 409,
      body: {
        detail: {
          error_code: 'customer_already_exists',
          message: 'Клиент «Новый клиент» уже существует и совпадает по телефону',
          field_errors: {
            duplicate_customer_id: '17',
            duplicate_fields: 'phone',
          },
        },
      },
    });
    const wrapper = mountModal();

    await wrapper.get('[data-testid="customer-name"]').setValue('Новый клиент');
    await wrapper.get('[data-testid="submit-customer"]').trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('Клиент «Новый клиент» уже существует');
    const openExisting = wrapper.findAll('button')
      .find((button) => button.text().includes('Открыть существующего клиента'));
    expect(openExisting).toBeTruthy();
    await openExisting!.trigger('click');
    expect(wrapper.emitted('openExisting')?.[0]).toEqual([17]);
  });
});

describe('CustomersView', () => {
  it('opens customer creation directly from the customers page', async () => {
    const wrapper = mount(CustomersView, {
      global: {
        stubs: {
          teleport: true,
          transition: false,
          CreateOrderModal: true,
        },
      },
    });
    wrappers.push(wrapper);
    await flushPromises();

    expect(wrapper.find('[data-testid="create-customer-modal"]').exists()).toBe(false);
    await wrapper.get('[data-testid="create-customer"]').trigger('click');
    expect(wrapper.get('[data-testid="create-customer-modal"]').exists()).toBe(true);
  });
});
