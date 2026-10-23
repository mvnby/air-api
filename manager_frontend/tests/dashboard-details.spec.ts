import { DOMWrapper, enableAutoUnmount, flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ details: vi.fn() }));
vi.mock('../src/services/dashboard-details-api', () => ({ getDashboardDetails: mocks.details }));
import DashboardKpiDetailsDialog from '../src/components/dashboard/DashboardKpiDetailsDialog.vue';
import DashboardKpiCard from '../src/components/dashboard/DashboardKpiCard.vue';
const period = { start: '2026-10-01T00:00:00+03:00', end: '2026-10-24T00:00:00+03:00' };
const result = { metric: 'revenue', unit: 'byn', value: 125.55, total: 51, limit: 50, offset: 0, period, generated_at: '2026-10-23T12:00:00+03:00', items: [{ record_id: 9, entity_id: 17, entity_type: 'order', title: 'Оплата', occurred_at: '2026-10-05T10:00:00+03:00', amount: 125.55 }] };
enableAutoUnmount(afterEach);
beforeEach(() => { mocks.details.mockReset(); mocks.details.mockResolvedValue(result); });
const mountDetails = async (metric: 'revenue' | 'receivables' = 'revenue') => {
  const wrapper = mount(DashboardKpiDetailsDialog, { props: { metric, period }, attachTo: document.body });
  await flushPromises();
  return { wrapper, ui: new DOMWrapper(document.body) };
};
describe('Dashboard KPI details', () => {
  it('opens source records and preserves the displayed period while paginating', async () => {
    const { wrapper, ui } = await mountDetails();
    expect(mocks.details).toHaveBeenCalledWith('revenue', period, 0);
    expect(ui.get('a').attributes('href')).toBe('/manager/orders/17?returnTo=%2Fmanager');
    expect(ui.text()).toContain('125,55');
    mocks.details.mockResolvedValueOnce({ ...result, offset: 50, items: [{ ...result.items[0], record_id: 55, entity_type: 'lead', entity_id: 81 }] });
    await ui.findAll('button').find(button => button.text() === 'Далее')!.trigger('click');
    await flushPromises();
    expect(mocks.details).toHaveBeenLastCalledWith('revenue', period, 50);
    expect(ui.get('a').attributes('href')).toBe('/manager/leads?incomingId=81');
    expect(ui.text()).toContain('51–51 из 51');
  });
  it('labels receivables as a current balance without claiming every payment is overdue', async () => {
    const { ui } = await mountDetails('receivables');
    expect(ui.text()).toContain('Срез на сейчас');
    expect(ui.text()).toContain('Срок оплаты может ещё не наступить.');
  });
  it('shows an actionable retry after failure and closes on Escape', async () => {
    mocks.details.mockRejectedValueOnce(new Error('Загрузка недоступна'));
    const { wrapper, ui } = await mountDetails();
    expect(ui.get('[role="alert"]').text()).toContain('Загрузка недоступна');
    await ui.findAll('button').find(button => button.text() === 'Повторить')!.trigger('click');
    await flushPromises();
    expect(ui.get('a').text()).toContain('Заказ #17');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(wrapper.emitted('close')).toHaveLength(1);
  });
  it('only exposes KPI actions with access to CRM', async () => {
    const props = { metric: 'sales' as const, kpi: { label: 'Продажи', current: 1, previous: null, unit: 'count' as const, trend: 'unavailable' as const } };
    const wrapper = mount(DashboardKpiCard, { props });
    expect(wrapper.find('button').exists()).toBe(false);
    await wrapper.setProps({ actionable: true });
    await wrapper.get('button').trigger('click');
    expect(wrapper.emitted('select')).toEqual([['sales']]);
  });
});
