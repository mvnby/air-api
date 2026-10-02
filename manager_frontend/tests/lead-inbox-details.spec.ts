import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import type { InboxItem } from '../src/services/lead-inbox';
vi.mock('../src/components/service-attachments/OrderAttachmentsPanel.vue', () => ({ default: { template: '<div />' } }));
vi.mock('../src/components/leads/EmailOriginals.vue', () => ({ default: { template: '<div data-testid="originals" />' } }));
vi.mock('../src/components/leads/EmailContractReviewLauncher.vue', () => ({ default: { template: '<div data-testid="contract-review" />' } }));
vi.mock('../src/components/leads/EmailLeadOrderLink.vue', () => ({ default: { template: '<div data-testid="email-link" />' } }));
vi.mock('../src/components/orders/CommercialTermsPanel.vue', () => ({ default: { props: ['emailSource'], template: '<div data-testid="commercial-terms" :data-email="emailSource" />' } }));
import LeadInboxDetails from '../src/components/leads/LeadInboxDetails.vue';
const item: InboxItem = { id: 10, status: 'new_lead', is_new: true, source: 'email', created_at: '2026-10-02T10:00:00Z', comment: 'Описание, составленное при обработке' };
describe('Incoming source context', () => {
  it('labels processed descriptions honestly and gives originals and optional checks in email context', () => {
    const wrapper = mount(LeadInboxDetails, { props: { item, history: [] } });
    expect(wrapper.text()).toContain('Описание обращения');
    expect(wrapper.text()).not.toContain('Исходный запрос');
    expect(wrapper.find('[data-testid="originals"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="contract-review"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="email-link"]').exists()).toBe(true);
    expect(wrapper.get('[data-testid="commercial-terms"]').attributes('data-email')).toBe('true');
    wrapper.unmount();
  });
  it('shows exact original text and its truncation explicitly', () => {
    const wrapper = mount(LeadInboxDetails, { props: { item: { ...item, original_text: 'Исходное письмо заказчика', original_text_truncated: true }, history: [] } });
    expect(wrapper.text()).toContain('Исходный запрос');
    expect(wrapper.text()).toContain('Исходное письмо заказчика');
    expect(wrapper.text()).not.toContain(item.comment);
    expect(wrapper.text()).toContain('Показана часть исходного текста');
    wrapper.unmount();
  });
  it('keeps order-only panels out of raw site leads and uses Minsk time for history', () => {
    const wrapper = mount(LeadInboxDetails, { props: { item: { ...item, entity_kind: 'lead', source: 'site' }, history: [{ id: 1, kind: 'no_answer', created_at: '2026-10-02T10:00:00Z', actor: 'Вадим' }] } });
    expect(wrapper.find('[data-testid="commercial-terms"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="contract-review"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="email-link"]').exists()).toBe(false);
    expect(wrapper.text()).toContain('13:00');
    wrapper.unmount();
  });
  it('records an optional followup in Minsk time and preserves omission when no fields are entered', async () => {
    const wrapper = mount(LeadInboxDetails, { props: { item: { ...item, entity_kind: 'lead', source: 'site' }, history: [] } });
    await wrapper.get('form.contact-attempt').trigger('submit');
    expect(wrapper.emitted('no-answer')?.[0]).toEqual([expect.objectContaining({ note: undefined, nextFollowupAt: undefined })]);
    await wrapper.get('input[type="datetime-local"]').setValue('2026-10-03T16:00');
    await wrapper.get('input[type="text"]').setValue('  Перезвонить после встречи  ');
    await wrapper.get('form.contact-attempt').trigger('submit');
    expect(wrapper.emitted('no-answer')?.[1]).toEqual([expect.objectContaining({ note: 'Перезвонить после встречи', nextFollowupAt: '2026-10-03T13:00:00.000Z' })]);
    wrapper.unmount();
  });

});
