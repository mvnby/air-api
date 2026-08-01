import { mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import OrderPlanningPanel from '../src/components/orders/OrderPlanningPanel.vue';

const installers = [
  { id: 7, name: 'Иван', is_active: true },
  { id: 8, name: 'Архивный мастер', is_active: false },
];

const mountedWrappers: VueWrapper[] = [];

const baseProps = {
  workflowType: 'sales_installation' as const,
  executorOptions: installers,
  customerBranchId: null,
  newBranchAddress: '',
  measurementRequired: false,
  assessmentDate: '',
  negotiationStatus: 'awaiting_offer',
  autoExecutionOnPayment: false,
  detailsExpanded: true,
  measurerId: null,
  measurementResult: '',
  installationDate: '',
  installerId: null,
};

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
});

describe('OrderPlanningPanel', () => {
  it('keeps planning state controlled and asks the parent to enable a measurement', async () => {
    const wrapper = mount(OrderPlanningPanel, { props: baseProps });
    mountedWrappers.push(wrapper);

    expect(wrapper.text()).toContain('Замер не требуется');
    await wrapper.get('[data-testid="enable-measurement"]').trigger('click');

    expect(wrapper.emitted('update:measurementRequired')).toEqual([[true]]);
  });

  it('uses repair terminology and emits negotiation and executor changes', async () => {
    const wrapper = mount(OrderPlanningPanel, {
      props: {
        ...baseProps,
        workflowType: 'repair',
        measurementRequired: true,
        assessmentDate: '2026-08-01T10:00',
        customerBranchId: 5,
      },
    });
    mountedWrappers.push(wrapper);

    expect(wrapper.text()).toContain('Диагностика и выезд');
    expect(wrapper.text()).toContain('Дата диагностики / ремонта');
    expect(wrapper.text()).toContain('выбран филиал');

    await wrapper.get('[data-testid="negotiation-status"]').setValue('awaiting_visit');
    await wrapper.get('[data-testid="measurer"]').setValue('7');
    await wrapper.get('[data-testid="installer"]').setValue('8');

    expect(wrapper.emitted('update:negotiationStatus')).toEqual([['awaiting_visit']]);
    expect(wrapper.emitted('update:measurerId')).toEqual([[7]]);
    expect(wrapper.emitted('update:installerId')).toEqual([[8]]);
  });

  it('surfaces both scheduling validation errors in the extracted section', () => {
    const wrapper = mount(OrderPlanningPanel, {
      props: {
        ...baseProps,
        measurementRequired: true,
        measurementError: 'Дата замера обязательна',
        installationError: 'Монтаж раньше замера',
      },
    });
    mountedWrappers.push(wrapper);

    expect(wrapper.text()).toContain('Дата замера обязательна');
    expect(wrapper.text()).toContain('Монтаж раньше замера');
  });
});
