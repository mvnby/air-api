import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  createManagerOrder: vi.fn(),
  getLeadsInbox: vi.fn(),
  getLeadsCounter: vi.fn(),
  getManagerCustomers: vi.fn(),
}));

vi.mock('../src/api', () => ({
  api: {
    createManagerOrder: mocks.createManagerOrder,
    getLeadsInbox: mocks.getLeadsInbox,
    getLeadsCounter: mocks.getLeadsCounter,
    getManagerCustomers: mocks.getManagerCustomers,
    patchManagerOrder: vi.fn(),
  },
}));
vi.mock('../src/composables/useBelarusPhoneMask', () => ({
  useBelarusPhoneMask: (_input: unknown, model: { value: string }) => ({ unmaskedValue: model }),
}));
vi.mock('../src/composables/useB2BLookup', () => ({
  useB2BLookup: () => ({ lookupCompany: vi.fn(), isEgrLoading: { value: false } }),
}));
vi.mock('../src/components/leads/LeadInboxCard.vue', () => ({
  default: { name: 'LeadInboxCard', props: ['item'], template: '<article data-testid="inbox-item">{{ item.customer_name }}</article>' },
}));
vi.mock('../src/components/leads/LeadQualifyModal.vue', () => ({ default: { template: '<div />' } }));
vi.mock('../src/components/leads/EmailLeadImportPanel.vue', () => ({ default: { template: '<div />' } }));
vi.mock('../src/components/ui/AddressSuggestInput.vue', () => ({ default: { template: '<div />' } }));

import LeadInbox from '../src/views/LeadInbox.vue';
import { managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';

const response = (items: Array<Record<string, unknown>>) => ({
  items,
  total: items.length,
  meta: { page: 1, pages: 1, total: items.length },
  source_counts: items.reduce<Record<string, number>>((counts, item) => {
    const source = String(item.source || 'other');
    counts[source] = (counts[source] || 0) + 1;
    return counts;
  }, {}),
});
const activeItem = { id: 1, source: 'site', status: 'new_lead', is_new: true, customer_name: 'Анна', phone: '+375291112233', email: 'anna@example.test', comment: 'Нужен монтаж', created_at: '2026-09-01T10:00:00Z' };
const archiveItem = { id: 2, source: 'email', status: 'closed', is_new: false, customer_name: 'Борис', customer_inn: '123456789', comment: 'Закрыто', created_at: '2026-09-01T10:00:00Z' };

describe('LeadInbox usability', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    managerSession.auth.value = null;
    managerStorefrontSelection.selectedSlug.value = null;
    mocks.getLeadsCounter.mockResolvedValue({ pending_count: 1, unread_count: 1, count: 1 });
    mocks.getManagerCustomers.mockResolvedValue({ items: [] });
    mocks.getLeadsInbox.mockImplementation((scope: string) => Promise.resolve(response(scope === 'active' ? [activeItem] : [archiveItem])));
  });

  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it('searches on the server and switches scope directly', async () => {
    mocks.getLeadsInbox.mockImplementation((scope: string, _page: number, _limit: number, search?: string) => Promise.resolve(
      response(search ? (search === 'example.test' ? [activeItem] : []) : scope === 'active' ? [activeItem] : [archiveItem]),
    ));
    const wrapper = mount(LeadInbox);
    await flushPromises();
    expect(wrapper.get('[data-testid="inbox-item"]').text()).toBe('Анна');

    expect(wrapper.find('input[type="search"]').exists()).toBe(false);
    await wrapper.get('button[aria-label="Поиск по входящим обращениям"]').trigger('click');
    await wrapper.get('input[type="search"]').setValue('example.test');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenCalledWith('active', 1, 50, 'example.test', undefined, false, 'deadline');
    expect(wrapper.findAll('[data-testid="inbox-item"]')).toHaveLength(1);
    await wrapper.get('input[type="search"]').setValue('нет совпадений');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    expect(wrapper.text()).toContain('По этому запросу обращений нет');
    await wrapper.get('button[aria-label="Очистить поиск"]').trigger('click');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    await wrapper.get('button[aria-label="Архив"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="inbox-item"]').text()).toBe('Борис');
    wrapper.unmount();
  });

  it('requests only one page and restores source, scope and page for the same account and storefront', async () => {
    managerSession.auth.value = { tenant_id: 11, staff_user_id: 7, username: 'manager' } as never;
    managerStorefrontSelection.selectedSlug.value = 'main';
    mocks.getLeadsInbox.mockImplementation((_scope: string, page: number) => Promise.resolve({
      items: page === 1 ? [activeItem] : [archiveItem], total: 61,
      meta: { page, pages: 2, total: 61 },
      source_counts: { belzakupki: 61 },
    }));
    const first = mount(LeadInbox);
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenCalledTimes(1);
    await first.findAll('.channels button').find(button => button.get('.channel-label').text() === 'Тендеры')!.trigger('click');
    await flushPromises();
    await first.findAll('button').find(button => button.text() === 'Далее')!.trigger('click');
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 2, 50, undefined, 'belzakupki', false, 'deadline');
    first.unmount();

    const returned = mount(LeadInbox);
    await flushPromises();
    expect(returned.findAll('.channels button').find(button => button.get('.channel-label').text() === 'Тендеры')!.attributes('aria-pressed')).toBe('true');
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 2, 50, undefined, 'belzakupki', false, 'deadline');
    returned.unmount();

    managerStorefrontSelection.selectedSlug.value = 'other';
    const other = mount(LeadInbox);
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 1, 50, undefined, undefined, false, 'deadline');
    other.unmount();
  });

  it('retries errors and moves back when the requested page became empty', async () => {
    mocks.getLeadsInbox.mockRejectedValueOnce(new Error('network'));
    const wrapper = mount(LeadInbox);
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить');
    await wrapper.get('[role="alert"] button').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="inbox-item"]').text()).toBe('Анна');
    wrapper.unmount();

    managerSession.auth.value = { tenant_id: 11, staff_user_id: 7, username: 'manager' } as never;
    managerStorefrontSelection.selectedSlug.value = 'main';
    window.sessionStorage.setItem('mvn_manager_storefront_v1:11:staff-7:main:lead-inbox', JSON.stringify({ scope: 'active', source: '', search: '', page: 2 }));
    mocks.getLeadsInbox.mockImplementation((_scope: string, page: number) => Promise.resolve(page === 2
      ? { items: [], total: 1, meta: { page: 2, pages: 1, total: 1 } }
      : response([activeItem])));
    const restored = mount(LeadInbox);
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenCalledWith('active', 2, 50, undefined, undefined, false, 'deadline');
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 1, 50, undefined, undefined, false, 'deadline');
    expect(restored.get('[data-testid="inbox-item"]').text()).toBe('Анна');
    restored.unmount();
  });

  it('does not apply an older response after scope changes', async () => {
    let resolveActive: ((value: ReturnType<typeof response>) => void) | undefined;
    mocks.getLeadsInbox.mockImplementation((scope: string) => scope === 'active'
      ? new Promise((resolve) => { resolveActive = resolve; })
      : Promise.resolve(response([archiveItem])));
    const wrapper = mount(LeadInbox);
    await wrapper.get('button[aria-label="Архив"]').trigger('click');
    await flushPromises();
    resolveActive?.(response([activeItem]));
    await flushPromises();
    expect(wrapper.get('[data-testid="inbox-item"]').text()).toBe('Борис');
    wrapper.unmount();
  });

  it('ignores an older search response after a newer query', async () => {
    let resolveOld: ((value: ReturnType<typeof response>) => void) | undefined;
    mocks.getLeadsInbox.mockImplementation((_scope: string, _page: number, _limit: number, search?: string) => {
      if (search === 'old') return new Promise(resolve => { resolveOld = resolve; });
      return Promise.resolve(response(search === 'new' ? [archiveItem] : [activeItem]));
    });
    const wrapper = mount(LeadInbox);
    await flushPromises();
    await wrapper.get('button[aria-label="Поиск по входящим обращениям"]').trigger('click');
    await wrapper.get('input[type="search"]').setValue('old');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    await wrapper.get('input[type="search"]').setValue('new');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    resolveOld?.(response([activeItem]));
    await flushPromises();
    expect(wrapper.get('[data-testid="inbox-item"]').text()).toBe('Борис');
    wrapper.unmount();
  });

  it('uses server counts across pages and keeps an empty selected source available', async () => {
    mocks.getLeadsInbox.mockResolvedValue({ ...response([activeItem]), source_counts: { site: 53, email: 2 } });
    const wrapper = mount(LeadInbox);
    await flushPromises();
    const channels = () => wrapper.findAll('.channels button');
    expect(channels().map(button => button.get('.channel-label').text())).toEqual(['Все', 'Сайт', 'Почта']);
    expect(channels().map(button => button.get('.channel-count').text())).toEqual(['55', '53', '2']);

    mocks.getLeadsInbox.mockResolvedValue({ ...response([]), source_counts: { email: 2 } });
    await channels()[1]!.trigger('click');
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 1, 50, undefined, 'site', false, 'deadline');
    expect(channels()[1]!.attributes('aria-pressed')).toBe('true');
    expect(channels()[1]!.get('.channel-count').text()).toBe('0');
    await channels()[0]!.trigger('click');
    await flushPromises();
    expect(channels().map(button => button.get('.channel-label').text())).toEqual(['Все', 'Почта']);
    wrapper.unmount();
  });

  it('restores a visible search and clears its filter when collapsed with Escape', async () => {
    managerSession.auth.value = { tenant_id: 11, staff_user_id: 7, username: 'manager' } as never;
    managerStorefrontSelection.selectedSlug.value = 'main';
    window.sessionStorage.setItem('mvn_manager_storefront_v1:11:staff-7:main:lead-inbox', JSON.stringify({ search: 'Анна' }));
    const wrapper = mount(LeadInbox, { attachTo: document.body });
    await flushPromises();
    expect(wrapper.get('input[type="search"]').element.value).toBe('Анна');
    const toggle = wrapper.get('button[aria-label="Поиск по входящим обращениям"]');
    expect(toggle.attributes('aria-expanded')).toBe('true');
    await wrapper.get('input[type="search"]').trigger('keydown', { key: 'Escape' });
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    expect(wrapper.find('input[type="search"]').exists()).toBe(false);
    expect(toggle.attributes('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(toggle.element);
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 1, 50, undefined, undefined, false, 'deadline');
    await toggle.trigger('click');
    expect(document.activeElement).toBe(wrapper.get('input[type="search"]').element);
    wrapper.unmount();
  });

  it('refreshes unread source badges without closing the opened card', async () => {
    const wrapper = mount(LeadInbox);
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text() === 'Непросмотренные')!.trigger('click');
    await flushPromises();
    const card = wrapper.findComponent({ name: 'LeadInboxCard' });
    card.vm.$emit('updated', { ...activeItem, is_read: true, is_new: false });
    await flushPromises();
    expect(wrapper.get('.channels .channel-count').text()).toBe('0');
    expect(wrapper.findComponent({ name: 'LeadInboxCard' }).vm).toBe(card.vm);
    card.vm.$emit('updated', { ...activeItem, is_read: false, is_new: true });
    await flushPromises();
    expect(wrapper.get('.channels .channel-count').text()).toBe('1');
    wrapper.unmount();
  });

  it('opens an existing negotiation returned by order creation', async () => {
    mocks.createManagerOrder.mockResolvedValue({ id: 73, status: 'negotiation' });
    const pushState = vi.spyOn(window.history, 'pushState');
    const wrapper = mount(LeadInbox);
    await flushPromises();
    await wrapper.findAll('button').find((button) => button.text().includes('Создать обращение'))!.trigger('click');
    await wrapper.get('textarea').setValue('Нужна консультация');
    await wrapper.findAll('button').filter((button) => button.text().includes('Создать обращение'))[1].trigger('click');
    await flushPromises();
    expect(pushState).toHaveBeenCalledWith({}, '', '/manager/orders/kanban?orderId=73');
    expect(wrapper.text()).toContain('уже в переговорах');
    wrapper.unmount();
  });
  it('does not let an older personal counter overwrite the newest read decision', async () => {
    let resolveOld: ((value: { pending_count: number; unread_count: number; count: number }) => void) | undefined;
    mocks.getLeadsCounter.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }));
    const wrapper = mount(LeadInbox);
    await flushPromises();
    const card = wrapper.findComponent({ name: 'LeadInboxCard' });
    card.vm.$emit('updated', { ...activeItem, is_read: true, is_new: false });
    card.vm.$emit('updated', { ...activeItem, is_read: false, is_new: true });
    await flushPromises();
    expect(wrapper.get('.inbox-header p').text()).toContain('Непросмотрено: 1');
    resolveOld?.({ pending_count: 1, unread_count: 0, count: 0 });
    await flushPromises();
    expect(wrapper.get('.inbox-header p').text()).toContain('Непросмотрено: 1');
    wrapper.unmount();
  });

});
