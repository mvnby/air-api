import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CustomersView from '../src/views/CustomersView.vue';
import { api } from '../src/api';
import { managerSession } from '../src/services/manager-session';

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
  managerSession.auth.value = null;
  vi.spyOn(api, 'getManagerCustomers').mockResolvedValue(response());
  vi.spyOn(api, 'patchManagerCustomer').mockResolvedValue({ ...firstCustomer, is_favorite: true });
});

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  managerSession.auth.value = null;
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

  it('shows the primary contact and a direct edit link', async () => {
    vi.mocked(api.getManagerCustomers).mockResolvedValueOnce(response([{
      ...firstCustomer,
      primary_contact: { name: 'Анна Иванова', role: 'Закупки', phone: '+375291110000', email: 'anna@example.test' },
    }]));
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.get('.customer-contact-person').text()).toContain('Анна Иванова · Закупки');
    expect(wrapper.find('a[href="tel:+375291110000"]').exists()).toBe(true);
    expect(wrapper.find('a[href="mailto:anna@example.test"]').exists()).toBe(true);
    expect(wrapper.get('.customer-contact-edit').attributes('href')).toBe('/manager/customers/profile?customerId=1&editContact=1');
  });

  it('applies compact type and favorite filters to the server request', async () => {
    const wrapper = mountView();
    await flushPromises();
    await wrapper.get('.customer-type-segments button:nth-child(2)').trigger('click');
    await flushPromises();
    await wrapper.get('.customer-filter-chip').trigger('click');
    await flushPromises();

    expect(api.getManagerCustomers).toHaveBeenLastCalledWith(1, 20, undefined, 'company', false, true, false);
    expect(wrapper.get('.customer-filter-chip').attributes('aria-pressed')).toBe('true');
    expect(wrapper.get('.customers-header').text()).toContain('Новый клиент');
    expect(wrapper.find('.search-box input').exists()).toBe(true);
  });

  it('can include archived customers and marks them in the list', async () => {
    managerSession.auth.value = { tenant_id: 7, staff_user_id: 3, username: 'manager' } as never;
    vi.mocked(api.getManagerCustomers)
      .mockResolvedValueOnce(response())
      .mockResolvedValueOnce(response([{ ...firstCustomer, is_archived: true }]));
    const wrapper = mountView();
    await flushPromises();
    const archiveFilter = wrapper.findAll('.customer-filter-chip').find((button) => button.text() === 'С архивом');
    expect(archiveFilter).toBeTruthy();
    await archiveFilter!.trigger('click');
    await flushPromises();

    expect(api.getManagerCustomers).toHaveBeenLastCalledWith(1, 20, undefined, undefined, false, false, true);
    expect(wrapper.get('.customer-archived-badge').text()).toBe('Архив');
    expect(JSON.parse(sessionStorage.getItem('manager:customers:v2:7:staff-3') || '{}').archived).toBe(true);
  });

  it('keeps saved filters within one manager identity', async () => {
    managerSession.auth.value = { tenant_id: 7, staff_user_id: 3, username: 'manager' } as never;
    sessionStorage.setItem('manager:customers:v2:7:staff-3', JSON.stringify({
      search: 'Анна', type: 'individual', orders: true, favorites: true, page: 2,
    }));
    const wrapper = mountView();
    await flushPromises();
    expect(api.getManagerCustomers).toHaveBeenLastCalledWith(2, 20, 'Анна', 'individual', true, true, false);

    managerSession.auth.value = { tenant_id: 8, staff_user_id: 3, username: 'manager' } as never;
    await flushPromises();
    expect(api.getManagerCustomers).toHaveBeenLastCalledWith(1, 20, undefined, undefined, false, false, false);
    expect(wrapper.get('.search-box input').element.value).toBe('');
  });

  it('opens the new intake dialog from the main action', async () => {
    const wrapper = mountView();
    await flushPromises();
    await wrapper.get('[data-testid="create-customer"]').trigger('click');
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('Реквизиты из письма или сообщения');
  });
});
