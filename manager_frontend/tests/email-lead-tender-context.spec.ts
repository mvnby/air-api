import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { InboxItem } from '../src/services/lead-inbox';
const mocks = vi.hoisted(() => ({ tender: vi.fn() }));
vi.mock('../src/services/lead-inbox', () => ({ leadInboxApi: mocks }));
import EmailLeadTenderContext from '../src/components/leads/EmailLeadTenderContext.vue';
const item: InboxItem = { id: 20, status: 'new_lead', is_new: true, source: 'email', source_kind: 'customer_request', created_at: '2026-10-03T10:00:00Z' };
beforeEach(() => {
  vi.clearAllMocks();
  mocks.tender.mockResolvedValue({ ...item, source_kind: 'tender', history: [] });
});
describe('Confirmed email tender context', () => {
  it('does not classify an email or infer a deadline automatically; the direct toggle starts without a trusted date', async () => {
    const wrapper = mount(EmailLeadTenderContext, { props: { item } });
    expect(mocks.tender).not.toHaveBeenCalled();
    expect(wrapper.find('input').exists()).toBe(false);
    await wrapper.get('button').trigger('click'); await flushPromises();
    expect(mocks.tender).toHaveBeenCalledWith(20, { is_tender: true, deadline_at: null, source_url: null });
    expect(wrapper.emitted('updated')?.[0]).toEqual([expect.objectContaining({ source_kind: 'tender' }), []]);
    wrapper.unmount();
  });
  it('saves a manager-confirmed deadline in Minsk time only after explicit submission', async () => {
    const wrapper = mount(EmailLeadTenderContext, { props: { item: { ...item, source_kind: 'tender' } } });
    await wrapper.get('input[type="datetime-local"]').setValue('2026-10-05T14:30');
    await wrapper.get('input[type="url"]').setValue('https://example.test/tender/20');
    expect(mocks.tender).not.toHaveBeenCalled();
    expect(wrapper.get('button[type="submit"]').text()).toBe('Подтвердить срок подачи');
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(mocks.tender).toHaveBeenCalledWith(20, { is_tender: true, deadline_at: '2026-10-05T11:30:00.000Z', source_url: 'https://example.test/tender/20' });
    wrapper.unmount();
  });
  it('leaves a missing date unknown and directly clears manual context when changed to a regular request', async () => {
    const wrapper = mount(EmailLeadTenderContext, { props: { item: { ...item, source_kind: 'tender', deadline_at: '2026-10-05T11:30:00Z', tender: { url: 'https://example.test/tender/20' } } } });
    expect(wrapper.get('input[type="datetime-local"]').element).toHaveProperty('value', '2026-10-05T14:30');
    await wrapper.get('input[type="datetime-local"]').setValue('');
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(mocks.tender).toHaveBeenLastCalledWith(20, { is_tender: true, deadline_at: null, source_url: 'https://example.test/tender/20' });
    await wrapper.get('button.classification-toggle').trigger('click'); await flushPromises();
    expect(mocks.tender).toHaveBeenLastCalledWith(20, { is_tender: false, deadline_at: null, source_url: null });
    wrapper.unmount();
  });
  it('keeps server validation failure inline and never emits a fabricated saved result', async () => {
    mocks.tender.mockRejectedValueOnce(new Error('Срок подачи не подтверждён'));
    const wrapper = mount(EmailLeadTenderContext, { props: { item } });
    await wrapper.get('button').trigger('click'); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Срок подачи не подтверждён');
    expect(wrapper.emitted('updated')).toBeUndefined();
    wrapper.unmount();
  });
});
