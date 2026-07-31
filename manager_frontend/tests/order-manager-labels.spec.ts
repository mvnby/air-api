import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import OrderManagerLabels from '../src/components/orders/OrderManagerLabels.vue';

describe('OrderManagerLabels', () => {
  it('adds normalized unique labels and removes them by direct click', async () => {
    const wrapper = mount(OrderManagerLabels, { props: { modelValue: ['Срочно'] } });

    await wrapper.get('[data-testid="add-manager-label"]').trigger('click');
    await wrapper.get('[data-testid="manager-label-draft"]').setValue('  срочно  ');
    await wrapper.get('[data-testid="manager-label-draft"]').trigger('keydown.enter');
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();

    await wrapper.get('[data-testid="add-manager-label"]').trigger('click');
    await wrapper.get('[data-testid="manager-label-draft"]').setValue('  Новый   клиент ');
    await wrapper.get('[data-testid="manager-label-draft"]').trigger('keydown.enter');
    expect(wrapper.emitted('update:modelValue')).toEqual([[['Срочно', 'Новый клиент']]]);

    await wrapper.setProps({ modelValue: ['Срочно', 'Новый клиент'] });
    await wrapper.get('button[aria-label="Удалить метку Срочно"]').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([['Новый клиент']]);
  });
});
