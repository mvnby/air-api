import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import OrderExecutionPanel from '../src/components/orders/OrderExecutionPanel.vue';
import OrderCardActionsMenu from '../src/components/orders/OrderCardActionsMenu.vue';
import DealExecutionTab from '../src/components/orders/DealExecutionTab.vue';
import { ManagerMailService } from '../src/client';


const mountedWrappers: VueWrapper[] = [];
const baseProps = {
  workflowType: 'sales_installation' as const,
  expanded: true,
  executionStatus: 'needs_schedule',
  executionWithoutPayment: false,
  executionWithoutPaymentReason: '',
  autoCloseOnPayment: false,
};

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
});

describe('OrderExecutionPanel', () => {
  it('uses a select for installation orders and emits the selected stage', async () => {
    const wrapper = mount(OrderExecutionPanel, { props: baseProps });
    mountedWrappers.push(wrapper);

    await wrapper.get('[data-testid="execution-status"]').setValue('scheduled');

    expect(wrapper.emitted('update:executionStatus')).toEqual([['scheduled']]);
  });

  it('uses direct status buttons for repair work and controls debt exceptions', async () => {
    const wrapper = mount(OrderExecutionPanel, {
      props: { ...baseProps, workflowType: 'repair' },
    });
    mountedWrappers.push(wrapper);

    await wrapper.get('[data-testid="execution-status-work_done"]').trigger('click');
    await wrapper.get('[data-testid="execution-without-payment"]').setValue(true);
    await wrapper.setProps({ executionWithoutPayment: true });
    await wrapper.get('[data-testid="execution-without-payment-reason"]').setValue('Оплата по факту');
    await wrapper.get('[data-testid="auto-close-on-payment"]').setValue(true);

    expect(wrapper.emitted('update:executionStatus')).toEqual([['work_done']]);
    expect(wrapper.emitted('update:executionWithoutPayment')).toEqual([[true]]);
    expect(wrapper.emitted('update:executionWithoutPaymentReason')).toEqual([['Оплата по факту']]);
    expect(wrapper.emitted('update:autoCloseOnPayment')).toEqual([[true]]);
  });
});


vi.mock('../src/client', () => ({
  ManagerOrdersService: {},
  ManagerMailService: { listManagerBankReceipts: vi.fn().mockResolvedValue({ items: [] }) },
}));
const order = { id: 42, status: 'execution', balance_due: 500, work_stages: [], customer: { inn: '190000001' } } as any;

describe('order payment money callers', () => {
  it.each([0, -0.25, 10.12, 1234567.89, null, undefined, NaN, 'unknown'])('renders execution values %s without inventing zero', async (amount) => {
    const w = mount(DealExecutionTab, { props: { order: { ...order, balance_due: amount, payments: ['BYN', 'USD', 'EUR', 'GBP'].map((currency, id) => ({ id, currency, amount, date: '2026-10-08', type: 'postpayment' })) } } });
    await flushPromises();
    if (typeof amount === 'number' && Number.isFinite(amount)) {
      expect(w.text()).toContain(`${amount.toFixed(2)}\u00a0USD`);
      expect(w.text()).toContain(`${amount.toFixed(2)}\u00a0EUR`);
      expect(w.text()).toContain(`${amount.toFixed(2)}\u00a0GBP`);
      expect(w.findAll('svg[viewBox="0 0 360.67 446.4"]').length).toBeGreaterThanOrEqual(2);
    } else {
      expect(w.findAll('[aria-label="Нет данных"]')).toHaveLength(5);
      expect(w.text()).not.toContain('0.00');
    }
    const close = w.findAll('button').find(b => b.text().includes('Завершить сделку'))!;
    expect(close.attributes('disabled') !== undefined).toBe((amount || 0) > 0);
    w.unmount();
  });
  it('shows receipt money without changing receipt lookup', async () => {
    vi.mocked(ManagerMailService.listManagerBankReceipts).mockResolvedValueOnce({ items: [{ id: 9, amount: 10.12, status: 'requires_review' }] } as any);
    const w = mount(DealExecutionTab, { props: { order } });
    await flushPromises();
    expect(w.text()).toContain('10,12 BYN');
    w.unmount();
  });
  it.each([[true, 500], [false, 500], [true, 0], [true, -1]])('preserves close-debt gate %s/%s and its payload', async (allowCloseDebt, balance_due) => {
    const w = mount(OrderCardActionsMenu, { props: { order: { ...order, balance_due }, allowCloseDebt } });
    await w.get('[aria-label="Действия с заказом"]').trigger('click');
    const action = w.findAll('button').find(b => b.text().includes('Закрыть долг'));
    expect(Boolean(action)).toBe(allowCloseDebt && balance_due > 0);
    if (action) {
      expect(action.text()).toContain('500 BYN');
      expect(action.find('svg').exists()).toBe(true);
      await action.trigger('click');
      expect(w.emitted('closeDebt')).toEqual([[{ orderId: 42 }]]);
      expect(w.findAll('button')).toHaveLength(1);
    }
    w.unmount();
  });
});
