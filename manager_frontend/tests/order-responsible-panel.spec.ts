import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderResponsiblePanel from '../src/components/orders/OrderResponsiblePanel.vue';
import { orderResponsibilityApi } from '../src/services/order-responsibility';
const person = { staff_user_id: 7, display_name: 'Мария', avatar_url: null, is_active: true };
const order = { id: 11, responsible_person: { ...person, staff_user_id: 9, display_name: 'Бывший сотрудник', is_active: false }, responsible_version: 3 } as any;
beforeEach(() => vi.restoreAllMocks());
describe('responsible picker', () => {
  it('loads every eligible page, preserves the old inactive name and offers no inactive new candidate', async () => {
    const candidates = vi.spyOn(orderResponsibilityApi, 'candidates').mockResolvedValueOnce({ items: [person], total: 3, page: 1, limit: 1 }).mockResolvedValueOnce({ items: [{ ...person, staff_user_id: 8, display_name: 'Андрей' }, { ...person, staff_user_id: 10, display_name: 'Архивный', is_active: false }], total: 3, page: 2, limit: 2 });
    const assign = vi.fn().mockResolvedValue(true), wrapper = mount(OrderResponsiblePanel, { props: { order, canAssign: true, busy: false, assign } });
    await wrapper.get('button').trigger('click'); await flushPromises(); expect(candidates.mock.calls).toEqual([[1], [2]]); expect(wrapper.text()).toContain('Бывший сотрудник'); expect(wrapper.get('option[value="9"]').attributes('disabled')).toBeDefined(); expect(wrapper.find('option[value="10"]').exists()).toBe(false);
    await wrapper.get('select').setValue('8');
    await wrapper.setProps({ order: { ...order, title: 'Отдельная правка заказа' } });
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('8');
    await wrapper.get('form').trigger('submit'); await flushPromises(); expect(assign).toHaveBeenCalledWith(8); wrapper.unmount();
  });
  it('allows explicitly clearing while retaining a conflict message and refreshed current choice', async () => {
    vi.spyOn(orderResponsibilityApi, 'candidates').mockResolvedValue({ items: [person], total: 1, page: 1, limit: 100 }); const assign = vi.fn().mockResolvedValue(false);
    const wrapper = mount(OrderResponsiblePanel, { props: { order: { ...order, responsible_person: person }, canAssign: true, busy: false, assign } }); await wrapper.get('button').trigger('click'); await flushPromises(); await wrapper.get('select').setValue(''); await wrapper.get('form').trigger('submit'); await flushPromises(); expect(assign).toHaveBeenCalledWith(null);
    await wrapper.setProps({ order: { ...order, responsible_person: null, responsible_version: 4 }, error: 'Ответственный уже изменён' }); expect((wrapper.get('select').element as HTMLSelectElement).value).toBe(''); expect(wrapper.get('[role="alert"]').text()).toContain('уже изменён'); wrapper.unmount();
  });
  it('does not request candidates in a read-only or unavailable account', async () => {
    const candidates = vi.spyOn(orderResponsibilityApi, 'candidates'); const wrapper = mount(OrderResponsiblePanel, { props: { order, canAssign: false, busy: false, assign: vi.fn() } }); expect(wrapper.get('button').attributes('disabled')).toBeDefined(); await wrapper.get('button').trigger('click'); expect(candidates).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('Назначение недоступно'); wrapper.unmount();
  });
});
