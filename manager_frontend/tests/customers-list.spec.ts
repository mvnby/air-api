import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CustomersView from '../src/views/CustomersView.vue';
import { api } from '../src/api';

const firstCustomer = {
  id: 1,
  name: 'ООО Короткое имя',
  full_legal_name: 'Общество с ограниченной ответственностью «Полное юридическое наименование клиента»',
  phone: '+375291234567',
  email: 'team@example.test',
  inn: '123456789',
  type: 'company',
  order_count: 2,
  is_favorite: false,
  created_at: '2026-09-01T00:00:00Z',
};

const response = (items = [firstCustomer]) => ({
  items,
  meta: { page: 1, limit: 20, total: items.length, pages: 1 },
});

const wrappers: VueWrapper[] = [];

const mountView = () => {
  const wrapper = mount(CustomersView, {
    global: {
      stubs: { teleport: true, transition: false, CreateOrderModal: true },
    },
  });
  wrappers.push(wrapper);
  return wrapper;
};

beforeEach(() => {
  vi.useFakeTimers();
  sessionStorage.clear();
  vi.spyOn(api, 'getManagerCustomers').mockResolvedValue(response());
  vi.spyOn(api, 'patchManagerCustomer').mockResolvedValue({ ...firstCustomer, is_favorite: true });
});

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('CustomersView list', () => {
  it('renders one readable legal name as a profile link and keeps direct actions', async () => {
    const wrapper = mountView();
    await flushPromises();

    const profileLink = wrapper.get('.customer-name-link');
    expect(profileLink.text()).toBe(firstCustomer.name);
    expect(profileLink.attributes('title')).toBe(firstCustomer.full_legal_name);
    expect(profileLink.attributes('href')).toBe('/manager/customers/profile?customerId=1');
    expect(wrapper.get('td[data-label="УНП"]').text()).toBe('123456789');
    expect(wrapper.findAll('th').map((cell) => cell.text())).toContain('УНП');
    expect(wrapper.get('a[href="tel:+375291234567"]').text()).toContain('+375291234567');

    await wrapper.get('.favorite-btn').trigger('click');
    expect(api.patchManagerCustomer).toHaveBeenCalledWith(1, { is_favorite: true });
    await wrapper.get('.open-btn').trigger('click');
    expect(wrapper.findComponent({ name: 'CreateOrderModal' }).exists()).toBe(true);
  });

  it('debounces search input and ignores an obsolete response', async () => {
    let resolveInitial: ((value: ReturnType<typeof response>) => void) | undefined;
    let resolveSearch: ((value: ReturnType<typeof response>) => void) | undefined;
    vi.mocked(api.getManagerCustomers)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveInitial = resolve; }) as never)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveSearch = resolve; }) as never);
    const wrapper = mountView();
    const input = wrapper.get('input[aria-label^="Поиск клиентов"]');

    await input.setValue('Новый');
    resolveInitial?.(response());
    await flushPromises();
    expect(wrapper.text()).not.toContain(firstCustomer.full_legal_name);
    await vi.advanceTimersByTimeAsync(299);
    expect(api.getManagerCustomers).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(api.getManagerCustomers).toHaveBeenCalledTimes(2);

    resolveSearch?.(response([{ ...firstCustomer, id: 2, name: 'Новый клиент', full_legal_name: null }]));
    await flushPromises();
    resolveInitial?.(response());
    await flushPromises();

    expect(wrapper.text()).toContain('Новый клиент');
    expect(wrapper.text()).not.toContain('Полное юридическое наименование клиента');
  });

  it('shows a retryable error instead of an empty result', async () => {
    vi.mocked(api.getManagerCustomers)
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(response());
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain('Список не загрузился');
    const retry = wrapper.findAll('button').find((button) => button.text() === 'Повторить');
    expect(retry).toBeTruthy();
    await retry!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain(firstCustomer.name);
  });
});
