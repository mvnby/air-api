import { shallowMount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import OrderWorkspaceNav from '../src/components/orders/OrderWorkspaceNav.vue';

describe('OrderWorkspaceNav', () => {
  it('labels the work section as repair and routes the product shortcut to the proposal editor', async () => {
    const wrapper = shallowMount(OrderWorkspaceNav, {
      props: { active: 'work', workflow: 'repair' },
    });

    expect(wrapper.text()).toContain('Ремонт');
    await wrapper.get('[data-order-usage="workspace-add-product"]').trigger('click');
    expect(wrapper.emitted('add-product')).toEqual([[]]);

    await wrapper.get('[data-order-usage="workspace-documents"]').trigger('click');
    expect(wrapper.emitted('select')).toEqual([['documents']]);
  });
});
