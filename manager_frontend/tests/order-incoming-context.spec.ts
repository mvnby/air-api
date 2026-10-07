import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import OrderIncomingContext from '../src/components/orders/OrderIncomingContext.vue';

describe('Qualified incoming context', () => {
  it('shows an absolute wish, prior call, linked clarification and retained source after correction', () => {
    const wrapper = mount(OrderIncomingContext, { props: { context: {
      lead_id: 8, lead_version: 2, request_text: 'Исправленный текст', original_text: 'ТО квартиры; завтра 09:00',
      source_timezone: 'Europe/Minsk', source_occurred_at: '2025-12-31T21:01:00Z',
      requested_at: '2026-01-02T09:00:00+03:00', date_precision: 'datetime',
      region_text: 'Билево', call_before_visit: true, clarification_task_id: 11,
      field_sources: { requested_at: 'text', region_text: 'provided' },
    } } });
    expect(wrapper.text()).toContain('2 янв.');
    expect(wrapper.text()).toContain('09:00');
    expect(wrapper.text()).toContain('выезд не подтверждён');
    expect(wrapper.text()).toContain('Созвониться перед выездом');
    expect(wrapper.text()).toContain('Район: Билево');
    expect(wrapper.text()).toContain('Желаемая дата: из исходного текста');
    expect(wrapper.text()).toContain('Район: передано при сохранении');
    expect(wrapper.text()).toContain('ТО квартиры; завтра 09:00');
    expect(wrapper.text()).toContain('Исправленный текст');
    expect(wrapper.get('a[href="/manager/tasks?taskId=11"]').exists()).toBe(true);
    expect(wrapper.get('a[href="/manager/leads?incomingId=8"]').exists()).toBe(true);
    wrapper.unmount();
  });
  it('does not invent a clock time for a date-only wish', () => {
    const wrapper = mount(OrderIncomingContext, { props: { context: {
      lead_id: 8, lead_version: 1, request_text: 'завтра', original_text: 'завтра',
      source_timezone: 'Europe/Minsk', requested_at: '2026-01-02T00:00:00+03:00', date_precision: 'date',
    } } });
    expect(wrapper.text()).not.toContain('00:00');
    wrapper.unmount();
  });
});
