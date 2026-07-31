import { mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import OrderExecutionPanel from '../src/components/orders/OrderExecutionPanel.vue';

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
