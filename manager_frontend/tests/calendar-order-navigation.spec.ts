import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import CalendarDashboard from '../src/views/CalendarDashboard.vue';
import { ManagerOrdersService } from '../src/client';
import * as navigation from '../src/services/order-navigation';
const calendar = { getDate: () => new Date('2026-12-14T12:00:00Z'), view: { type: 'timeGridWeek' } };
vi.mock('@fullcalendar/vue3', () => ({ default: { name: 'FullCalendar', props: ['options'], methods: { getApi: () => calendar }, template: '<div />' } }));
afterEach(() => { vi.restoreAllMocks(); window.history.replaceState({}, '', '/manager/calendar'); });
describe('calendar order page navigation', () => {
  it('opens the shared order page and retains the current calendar date and view', async () => {
    window.history.replaceState({}, '', '/manager/calendar');
    vi.spyOn(ManagerOrdersService, 'listManagerStaleOrderStages').mockResolvedValue({ items: [], total: 0 } as any);
    const open = vi.spyOn(navigation, 'openOrderPage').mockImplementation(() => {});
    const wrapper = mount(CalendarDashboard);
    try {
      await flushPromises();
      const options = wrapper.getComponent({ name: 'FullCalendar' }).props('options');
      options.eventClick({ event: { extendedProps: { type: 'installation', order_id: 477 } } });
      expect(open).toHaveBeenCalledExactlyOnceWith(477);
      expect(window.history.state.orderCalendar).toEqual({ date: '2026-12-14T12:00:00.000Z', view: 'timeGridWeek' });
      expect(wrapper.findComponent({ name: 'OrderEditDrawer' }).exists()).toBe(false);
    } finally { wrapper.unmount(); }
  });
  it('restores the calendar view when returning from an order', async () => {
    window.history.replaceState({ orderCalendar: { date: '2026-12-14T12:00:00.000Z', view: 'timeGridWeek' } }, '', '/manager/calendar');
    vi.spyOn(ManagerOrdersService, 'listManagerStaleOrderStages').mockResolvedValue({ items: [], total: 0 } as any);
    const wrapper = mount(CalendarDashboard);
    try {
      await flushPromises();
      expect(wrapper.getComponent({ name: 'FullCalendar' }).props('options')).toMatchObject({ initialView: 'timeGridWeek', initialDate: '2026-12-14T12:00:00.000Z' });
    } finally { wrapper.unmount(); }
  });
});
