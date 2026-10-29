import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import OrderDrawerSection from '../src/components/orders/OrderDrawerSection.vue';

describe('OrderDrawerSection', () => {
  it('keeps a dedicated workspace visible even when its previous accordion state was collapsed', () => {
    const wrapper = mount(OrderDrawerSection, {
      props: { title: 'Документы', expanded: false, flat: true },
      slots: { default: '<input data-testid="draft" value="черновик" />' },
    });
    expect(wrapper.get('[aria-label="Документы"]').exists()).toBe(true);
    expect(wrapper.find('button').exists()).toBe(false);
    expect(wrapper.get('[data-testid="draft"]').isVisible()).toBe(true);
  });

  it('keeps the expanded content mounted when collapsed so local editor state survives', async () => {
    const wrapper = mount(OrderDrawerSection, {
      props: { title: 'Предложение', expanded: true },
      slots: { default: '<input data-testid="draft" value="не терять" />' },
    });

    await wrapper.get('button').trigger('click');
    expect(wrapper.get('[data-testid="draft"]').element).toBeInstanceOf(HTMLInputElement);
    expect((wrapper.get('[data-testid="draft"]').element as HTMLInputElement).value).toBe('не терять');
  });
});
