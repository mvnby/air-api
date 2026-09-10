import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import OrderDrawerSection from '../src/components/orders/OrderDrawerSection.vue';

describe('OrderDrawerSection', () => {
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
