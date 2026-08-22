import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import DashboardQuickActions from '../src/components/dashboard/DashboardQuickActions.vue';

describe('DashboardQuickActions', () => {
  it('keeps the daily manager routes and emits direct navigation', async () => {
    const wrapper = mount(DashboardQuickActions, { props: { leadsCount: 3 } });

    expect(wrapper.text()).toContain('Входящие');
    expect(wrapper.text()).toContain('Заказы');
    expect(wrapper.text()).toContain('Календарь');
    expect(wrapper.text()).toContain('Каталог');
    expect(wrapper.text()).toContain('Клиенты');

    await wrapper.findAll('button')[0].trigger('click');
    expect(wrapper.emitted('navigate')).toEqual([['/manager/leads']]);
  });

  it('shows the inbox badge only for a positive counter', () => {
    const empty = mount(DashboardQuickActions, { props: { leadsCount: 0 } });
    const active = mount(DashboardQuickActions, { props: { leadsCount: 7 } });

    expect(empty.text()).not.toContain('>0<');
    expect(empty.findAll('.bg-rose-500')).toHaveLength(0);
    expect(active.findAll('.bg-rose-500')).toHaveLength(1);
    expect(active.text()).toContain('7');
  });
});
