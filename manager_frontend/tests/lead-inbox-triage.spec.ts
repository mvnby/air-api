import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { InboxItem } from '../src/services/lead-inbox';
const mocks = vi.hoisted(() => ({ detail: vi.fn(), read: vi.fn(), archive: vi.fn(), archiveNonRequest: vi.fn(), notifyInboxChanged: vi.fn() }));
vi.mock('../src/services/lead-inbox', () => ({ leadInboxApi: mocks, notifyInboxChanged: mocks.notifyInboxChanged }));
vi.mock('../src/components/leads/LeadInboxDetails.vue', () => ({ default: {
  props: ['item', 'history'], emits: ['mark-unread', 'not-request'],
  template: '<section data-testid="details"><p>{{ item.comment }}</p><button @click="$emit(\'mark-unread\')">Пометить непросмотренным</button><button @click="$emit(\'not-request\')">Это не новая заявка</button></section>',
} }));
import LeadInboxCard from '../src/components/leads/LeadInboxCard.vue';
const lead: InboxItem = { id: 7, entity_kind: 'lead', status: 'new', is_new: true, is_read: false, customer_name: 'Анна', title: 'Монтаж двух кондиционеров', comment: 'Установка в Витебске', location: 'Витебск', quantity: 2, created_at: '2026-10-02T10:00:00Z', source: 'site' };
beforeEach(() => {
  vi.clearAllMocks();
  mocks.detail.mockResolvedValue({ ...lead, history: [] });
  mocks.read.mockImplementation(async (_id, isRead) => ({ ...lead, is_read: isRead, is_new: !isRead }));
  mocks.archiveNonRequest.mockResolvedValue({ ...lead, archive: { outcome: 'spam' } });
  mocks.archive.mockResolvedValue({ ...lead, archive: { outcome: 'refusal', reason: 'other' } });
});
describe('Incoming decisions and personal read state', () => {
  it('shows the subject first, factual quantity and location without marking a visible card read', () => {
    const wrapper = mount(LeadInboxCard, { props: { item: lead } });
    expect(wrapper.get('h2').text()).toBe('Монтаж двух кондиционеров');
    expect(wrapper.get('.customer').text()).toBe('Анна');
    expect(wrapper.get('.facts').text()).toContain('2 ед.');
    expect(wrapper.get('.facts').text()).toContain('Витебск');
    expect(wrapper.find('.budget').exists()).toBe(false);
    expect(mocks.read).not.toHaveBeenCalled();
    expect(mocks.detail).not.toHaveBeenCalled();
    wrapper.unmount();
  });
  it('marks only explicitly opened details read and can mark them unread again', async () => {
    const wrapper = mount(LeadInboxCard, { props: { item: lead } });
    await wrapper.get('button.title').trigger('click'); await flushPromises();
    expect(mocks.detail).toHaveBeenCalledWith(7, 'lead');
    expect(mocks.read).toHaveBeenCalledWith(7, true, 'lead');
    expect(wrapper.emitted('updated')?.[0]).toEqual([expect.objectContaining({ is_read: true })]);
    await wrapper.setProps({ item: { ...lead, is_read: true, is_new: false } });
    await wrapper.get('[data-testid="details"] button').trigger('click'); await flushPromises();
    expect(mocks.read).toHaveBeenLastCalledWith(7, false, 'lead');
    expect(wrapper.find('[data-testid="details"]').exists()).toBe(false);
    expect(mocks.notifyInboxChanged).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });
  it('does not mark unread a failed detail fetch and allows retry', async () => {
    mocks.detail.mockRejectedValueOnce(new Error('Подробности недоступны'));
    const wrapper = mount(LeadInboxCard, { props: { item: lead } });
    await wrapper.get('button.title').trigger('click'); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Подробности недоступны');
    expect(mocks.read).not.toHaveBeenCalled();
    await wrapper.get('[role="alert"] button').trigger('click'); await flushPromises();
    expect(mocks.read).toHaveBeenCalledWith(7, true, 'lead');
    wrapper.unmount();
  });
  it('requires a reason and a note for other before archiving a raw lead', async () => {
    const wrapper = mount(LeadInboxCard, { props: { item: lead } });
    await wrapper.findAll('button').find(button => button.text() === 'Не брать')!.trigger('click');
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined();
    await wrapper.findAll('.reason-options button').find(button => button.text() === 'Другое')!.trigger('click');
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined();
    await wrapper.get('textarea').setValue('Клиент отозвал запрос');
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(mocks.archive).toHaveBeenCalledWith(7, 'other', 'Клиент отозвал запрос', 'lead');
    expect(wrapper.emitted('archived')?.[0]).toEqual([lead]);
    wrapper.unmount();
  });
  it('keeps refusal errors inline and supports an archive restore without qualifying', async () => {
    mocks.archive.mockRejectedValueOnce(new Error('Отказ не сохранён'));
    const wrapper = mount(LeadInboxCard, { props: { item: lead } });
    await wrapper.findAll('button').find(button => button.text() === 'Не брать')!.trigger('click');
    await wrapper.findAll('.reason-options button')[0]!.trigger('click');
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Отказ не сохранён');
    expect(wrapper.emitted('archived')).toBeUndefined();
    wrapper.unmount();
    const archive = mount(LeadInboxCard, { props: { item: { ...lead, archive: { outcome: 'refusal', reason: 'region' } }, isArchive: true } });
    expect(archive.text()).toContain('Не наш регион');
    await archive.findAll('button').find(button => button.text() === 'Вернуть в работу')!.trigger('click');
    expect(archive.emitted('restore')?.[0]?.[0]).toEqual(expect.objectContaining({ entity_kind: 'lead', id: 7 }));
    expect(archive.emitted('qualify')).toBeUndefined();
    archive.unmount();
  });
  it('shows factual tender archive timing and references an existing encounter without assuming a decision', () => {
    const wrapper = mount(LeadInboxCard, { props: { item: { ...lead, entity_kind: 'order', source: 'belzakupki', auto_archive_at: '2026-10-04T09:00:00Z', related_requests: [{ order_id: 90, title: 'Та же закупка', url: 'https://example.test/tender', outcome: null }] } } });
    expect(wrapper.text()).toContain('В архив автоматически:');
    expect(wrapper.text()).toContain('12:00');
    expect(wrapper.text()).toContain('Эта закупка уже встречалась');
    expect(wrapper.get('a').attributes('href')).toBe('/manager/orders/kanban?orderId=90');
    expect(wrapper.text()).not.toContain('Не берём');
    wrapper.unmount();
  });

  it.each([['spam', 'Спам / ошибочное распознавание'], ['duplicate', 'Дубликат']] as const)('archives %s as its own outcome without inventing a refusal reason', async (outcome, label) => {
    const wrapper = mount(LeadInboxCard, { props: { item: lead } });
    await wrapper.get('button.title').trigger('click'); await flushPromises();
    await wrapper.findAll('[data-testid="details"] button').find(button => button.text() === 'Это не новая заявка')!.trigger('click');
    expect(wrapper.text()).toContain('Почему это не новая заявка?');
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined();
    await wrapper.findAll('.reason-options button').find(button => button.text() === label)!.trigger('click');
    expect(wrapper.get('textarea').attributes('required')).toBeUndefined();
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(mocks.archiveNonRequest).toHaveBeenCalledWith(7, outcome, undefined, 'lead');
    expect(mocks.archive).not.toHaveBeenCalled();
    expect(wrapper.emitted('archived')?.[0]).toEqual([lead]);
    wrapper.unmount();
  });

});
