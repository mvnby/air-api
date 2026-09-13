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
    mocks.getManagerCustomers.mockResolvedValue({ items: [] });
    mocks.getLeadsInbox.mockImplementation((scope: string) => Promise.resolve(response(scope === 'active' ? [activeItem] : [archiveItem])));
  });

  afterEach(() => vi.restoreAllMocks());

  it('searches all loaded fields and switches scope directly', async () => {
    const wrapper = mount(LeadInbox);
    await flushPromises();
    expect(wrapper.get('[data-testid="inbox-item"]').text()).toBe('Анна');

    await wrapper.get('input[type="search"]').setValue('example.test');
    expect(wrapper.findAll('[data-testid="inbox-item"]')).toHaveLength(1);
    await wrapper.get('input[type="search"]').setValue('нет совпадений');
    expect(wrapper.text()).toContain('По этому запросу обращений нет');
    await wrapper.get('button[aria-label="Очистить поиск"]').trigger('click');
    await wrapper.findAll('button').find((button) => button.text() === 'Архив')!.trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="inbox-item"]').text()).toBe('Борис');
    wrapper.unmount();
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
