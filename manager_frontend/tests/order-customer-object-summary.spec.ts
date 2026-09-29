import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import OrderCustomerObjectSummary from '../src/components/orders/OrderCustomerObjectSummary.vue';

const customer = {
  id: 7,
  type: 'individual',
  name: 'Анна',
  phone: '+375291112233',
  email: 'anna@example.test',
};

const mountSummary = () => mount(OrderCustomerObjectSummary, {
  props: {
    customer,
    address: '',
  },
  global: {
    stubs: {
      AddressSuggestInput: {
        name: 'AddressSuggestInput',
        props: ['modelValue'],
        emits: ['update:modelValue'],
        template: '<input data-testid="object-address-input" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
      },
    },
  },
});

describe('OrderCustomerObjectSummary', () => {
  it('opens customer selection instead of an empty customer editor when no customer is assigned', async () => {
    const wrapper = mount(OrderCustomerObjectSummary, {
      props: { customer: null, address: '' },
    });

    await wrapper.get('button[aria-label="Выбрать клиента"]').trigger('click');

    expect(wrapper.emitted('change-customer')).toHaveLength(1);
    expect(wrapper.find('input[placeholder="Имя или название клиента"]').exists()).toBe(false);
  });

  it('opens the requested editor from the order context', async () => {
    const wrapper = mountSummary();

    await wrapper.setProps({ editTarget: 'object' });

    expect(wrapper.text()).toContain('Выбрать филиал');
  });

  it('updates the order address on every input for an individual customer', async () => {
    const wrapper = mountSummary();

    await wrapper.get('button[aria-label="Редактировать объект"]').trigger('click');
    await wrapper.get('[data-testid="object-address-input"]').setValue('Минск, ул. Ленина, 1');

    expect(wrapper.emitted('update:address')).toContainEqual(['Минск, ул. Ленина, 1']);
    expect(wrapper.text()).not.toContain('Применить');
    expect(wrapper.text()).toContain('Готово');
  });

  it('applies an address-suggestion selection immediately and only saves customer identity explicitly', async () => {
    const wrapper = mountSummary();

    await wrapper.get('button[aria-label="Редактировать объект"]').trigger('click');
    await wrapper.findComponent({ name: 'AddressSuggestInput' }).vm.$emit(
      'update:modelValue',
      'Минск, проспект Победителей, 1',
    );
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted('update:address')).toContainEqual(['Минск, проспект Победителей, 1']);

    await wrapper.get('button[aria-label="Редактировать клиента"]').trigger('click');
    await wrapper.findAll('input').at(0)!.setValue('Анна Иванова');
    expect(wrapper.emitted('save-customer')).toBeUndefined();
    await wrapper.findAll('button').find((button) => button.text() === 'Сохранить')!.trigger('click');
    expect(wrapper.emitted('save-customer')).toContainEqual([{
      name: 'Анна Иванова',
      phone: '+375291112233',
      email: 'anna@example.test',
    }]);
  });
});
