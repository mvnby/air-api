import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import CustomerSearchSelect from '../src/components/customers/CustomerSearchSelect.vue';

const getManagerCustomers = vi.hoisted(() => vi.fn());
vi.mock('../src/api', () => ({ api: { getManagerCustomers } }));

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('CustomerSearchSelect', () => {
  it('selects and clears an optional customer', async () => {
    vi.useFakeTimers();
    getManagerCustomers.mockResolvedValue({ items: [{ id: 17, name: 'Анна Иванова', phone: '+375291112233' }] });
    const wrapper = mount(CustomerSearchSelect);

    await wrapper.get('[data-testid="customer-search"]').setValue('Анна');
    await vi.advanceTimersByTimeAsync(450);
    await flushPromises();
    await wrapper.get('[data-testid="select-customer-17"]').trigger('click');

    expect(wrapper.text()).toContain('Анна Иванова');
    expect(wrapper.get('[data-testid="clear-selected-customer"]').exists()).toBe(true);
    await wrapper.get('[data-testid="clear-selected-customer"]').trigger('click');
    expect(wrapper.get('[data-testid="customer-search"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it('clears stale results immediately and ignores an older response during the debounce', async () => {
    vi.useFakeTimers();
    let rejectOlderSearch: ((error: Error) => void) | undefined;
    getManagerCustomers
      .mockResolvedValueOnce({ items: [{ id: 11, name: 'Старый клиент' }] })
      .mockImplementationOnce(() => new Promise((_, reject) => { rejectOlderSearch = reject; }));
    const wrapper = mount(CustomerSearchSelect);

    await wrapper.get('[data-testid="customer-search"]').setValue('Старый');
    await vi.advanceTimersByTimeAsync(450);
    await flushPromises();
    expect(wrapper.get('[data-testid="select-customer-11"]').exists()).toBe(true);

    await wrapper.get('[data-testid="customer-search"]').setValue('Новый');
    expect(wrapper.find('[data-testid="select-customer-11"]').exists()).toBe(false);

    await vi.advanceTimersByTimeAsync(450);
    await flushPromises();
    await wrapper.get('[data-testid="customer-search"]').setValue('Свежий');
    rejectOlderSearch?.(new Error('offline'));
    await flushPromises();

    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="select-customer-11"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('clears loading and ignores a failed request after selection is cleared', async () => {
    vi.useFakeTimers();
    let rejectSearch: ((error: Error) => void) | undefined;
    getManagerCustomers.mockImplementationOnce(() => new Promise((_, reject) => { rejectSearch = reject; }));
    const wrapper = mount(CustomerSearchSelect);

    await wrapper.get('[data-testid="customer-search"]').setValue('Анна');
    await vi.advanceTimersByTimeAsync(450);
    expect(wrapper.text()).toContain('refresh');
    await wrapper.get('[data-testid="customer-search"]').setValue('');
    await flushPromises();
    rejectSearch?.(new Error('offline'));
    await flushPromises();

    expect(wrapper.text()).not.toContain('refresh');
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    wrapper.unmount();
  });
});
