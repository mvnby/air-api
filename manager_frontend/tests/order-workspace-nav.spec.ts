import { shallowMount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import OrderWorkspaceNav from '../src/components/orders/OrderWorkspaceNav.vue';

describe('OrderWorkspaceNav', () => {
  it.each(['sales_installation', 'repair'] as const)('keeps full section names and distinct actions for %s', async (workflow) => {
    const wrapper = shallowMount(OrderWorkspaceNav, {
      props: { active: 'proposal', workflow },
    });
    const sections = ['proposal', 'documents', 'work', 'payments'];
    const labels = ['Предложение', 'Документы', workflow === 'repair' ? 'Ремонт' : 'Работы', 'Оплаты'];

    expect(wrapper.get('nav').attributes('aria-label')).toBe('Рабочая область заказа');
    for (const [index, section] of sections.entries()) {
      const button = wrapper.get(`[data-order-usage="workspace-${section}"]`);
      expect(button.text()).toBe(labels[index]);
      expect(button.attributes('type')).toBe('button');
      expect(button.attributes('aria-current')).toBe(index === 0 ? 'page' : undefined);
      await button.trigger('click');
    }
    expect(wrapper.emitted('select')).toEqual(sections.map(section => [section]));

    await wrapper.setProps({ active: 'payments' });
    expect(wrapper.get('[data-order-usage="workspace-proposal"]').attributes('aria-current')).toBeUndefined();
    expect(wrapper.get('[data-order-usage="workspace-payments"]').attributes('aria-current')).toBe('page');
  });

  it('keeps navigation focused on sections with addition in the proposal footer', async () => {
    const wrapper = shallowMount(OrderWorkspaceNav, {
      props: { active: 'work', workflow: 'repair' },
    });

    expect(wrapper.text()).toContain('Ремонт');
    expect(wrapper.findAll('button')).toHaveLength(4);
    expect(wrapper.find('[data-order-usage="workspace-add-product"]').exists()).toBe(false);

    await wrapper.get('[data-order-usage="workspace-documents"]').trigger('click');
    expect(wrapper.emitted('select')).toEqual([['documents']]);
  });
});
