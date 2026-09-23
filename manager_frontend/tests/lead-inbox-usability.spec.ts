import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  createManagerOrder: vi.fn(),
  getLeadsInbox: vi.fn(),
  getManagerCustomers: vi.fn(),
}));

vi.mock('../src/api', () => ({
  api: {
    createManagerOrder: mocks.createManagerOrder,
    getLeadsInbox: mocks.getLeadsInbox,
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
});
const activeItem = { id: 1, status: 'new_lead', is_new: true, customer_name: 'Анна', phone: '+375291112233', email: 'anna@example.test', comment: 'Нужен монтаж', created_at: '2026-09-01T10:00:00Z' };
const archiveItem = { id: 2, status: 'closed', is_new: false, customer_name: 'Борис', customer_inn: '123456789', comment: 'Закрыто', created_at: '2026-09-01T10:00:00Z' };

describe('LeadInbox usability', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    managerSession.auth.value = null;
    managerStorefrontSelection.selectedSlug.value = null;
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

    await wrapper.get('input[type="search"]').setValue('example.test');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenCalledWith('active', 1, 50, 'example.test', undefined);
    expect(wrapper.findAll('[data-testid="inbox-item"]')).toHaveLength(1);
    await wrapper.get('input[type="search"]').setValue('нет совпадений');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    expect(wrapper.text()).toContain('По этому запросу обращений нет');
    await wrapper.get('button[aria-label="Очистить поиск"]').trigger('click');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    await wrapper.findAll('button').find((button) => button.text() === 'Архив')!.trigger('click');
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
    }));
    const first = mount(LeadInbox);
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenCalledTimes(1);
    await first.get('select[aria-label="Источник входящих"]').setValue('belzakupki');
    await flushPromises();
    await first.findAll('button').find(button => button.text() === 'Далее')!.trigger('click');
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 2, 50, undefined, 'belzakupki');
    first.unmount();

    const returned = mount(LeadInbox);
    await flushPromises();
    expect(returned.get('select[aria-label="Источник входящих"]').element).toHaveProperty('value', 'belzakupki');
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 2, 50, undefined, 'belzakupki');
    returned.unmount();

    managerStorefrontSelection.selectedSlug.value = 'other';
    const other = mount(LeadInbox);
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 1, 50, undefined, undefined);
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
    expect(mocks.getLeadsInbox).toHaveBeenCalledWith('active', 2, 50, undefined, undefined);
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 1, 50, undefined, undefined);
    expect(restored.get('[data-testid="inbox-item"]').text()).toBe('Анна');
    restored.unmount();
  });

  it('does not apply an older response after scope changes', async () => {
    let resolveActive: ((value: ReturnType<typeof response>) => void) | undefined;
    mocks.getLeadsInbox.mockImplementation((scope: string) => scope === 'active'
      ? new Promise((resolve) => { resolveActive = resolve; })
      : Promise.resolve(response([archiveItem])));
    const wrapper = mount(LeadInbox);
    await wrapper.findAll('button').find((button) => button.text() === 'Архив')!.trigger('click');
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
});
