import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import OrderCardB2B from '../src/components/orders/OrderCardB2B.vue';
import OrderCardB2C from '../src/components/orders/OrderCardB2C.vue';
import OrderListRow from '../src/components/orders/OrderListRow.vue';
import OrderResponsibleBadge from '../src/components/orders/OrderResponsibleBadge.vue';
const person = { staff_user_id: 7, display_name: 'Мария Иванова', avatar_url: '/api/manager/staff/7/avatar?tenant_id=2&v=photo', is_active: true };
const order = { id: 11, title: 'Кондиционер в офис', status: 'negotiation', created_at: '2026-10-16', total_amount: 100, margin: 10, responsible_person: person, responsible_version: 3, customer: { id: 1, name: 'Офис', type: 'company' } } as any;
describe('order responsible presentation', () => {
  it.each([OrderCardB2B, OrderCardB2C])('shows the same human identity and opens the order exactly once on a person tap', async component => {
    const wrapper = mount(component, { props: { order, expanded: false } });
    const badge = wrapper.getComponent(OrderResponsibleBadge);
    expect(badge.text()).toContain('Мария Иванова'); expect(badge.attributes('title')).toBe('Ответственный: Мария Иванова'); expect(badge.attributes('aria-label')).toContain('Мария Иванова');
    expect(badge.get('img').attributes('src')).toBe(person.avatar_url);
    await badge.trigger('click'); expect(wrapper.emitted('open')).toEqual([[11]]); expect(wrapper.emitted('toggleExpanded')).toBeUndefined(); expect(wrapper.emitted('dragStart')).toBeUndefined(); wrapper.unmount();
  });
  it('keeps the responsible visible in the table row and recovers initials from a missing private image', async () => {
    const wrapper = mount(OrderListRow, { props: { order, segment: 'b2b' } });
    const badge = wrapper.getComponent(OrderResponsibleBadge); await badge.get('img').trigger('error'); expect(badge.text()).toContain('МИ'); expect(badge.text()).toContain('Мария Иванова'); await badge.trigger('click'); expect(wrapper.emitted('open')).toEqual([[11]]); wrapper.unmount();
  });
  it('labels an inactive responsible and distinguishes an unassigned order', async () => {
    const wrapper = mount(OrderResponsibleBadge, { props: { person: { ...person, is_active: false } } }); expect(wrapper.attributes('title')).toContain('больше не работает');
    await wrapper.setProps({ person: null }); expect(wrapper.text()).toContain('Не назначен'); expect(wrapper.attributes('aria-label')).toBe('Ответственный не назначен'); wrapper.unmount();
  });
});
