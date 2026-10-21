import { mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import OrderWorkspaceHeader from '../src/components/orders/OrderWorkspaceHeader.vue';
import type { OrderWorkspaceViewModel } from '../src/components/orders/order-workspace';

const title = 'Обслуживание систем вентиляции и кондиционирования на нескольких объектах заказчика';
const customerName = 'Учреждение «Синтетический заказчик с длинным названием»';
const props = {
  orderId: 22, title, customerName, workflow: 'maintenance' as const,
  viewModel: { stageLabel: 'Ожидание предложения', stageAge: '2 дня', nextAction: { label: 'Подготовить предложение' } } as OrderWorkspaceViewModel,
  total: 100, paid: 0, balance: 100, workspace: true, backLabel: 'К заказам', autosaveEnabled: true,
};
let wrapper: VueWrapper;
afterEach(() => wrapper?.unmount());
const make = () => (wrapper = mount(OrderWorkspaceHeader, { props, attachTo: document.body }));

describe('compact order workspace header', () => {
  it('always shows the order identity, customer and status with complete title text available', async () => {
    make();
    expect(wrapper.text()).toContain('№22');
    expect(wrapper.get('[data-order-header-customer]').text()).toBe(customerName);
    expect(wrapper.get('[aria-label^="Изменить название:"]').attributes('title')).toBe(title);
    expect(wrapper.get('[aria-label^="Изменить название:"]').classes()).toContain('truncate');
    expect(wrapper.text()).toContain('Ожидание предложения');
    await wrapper.get('[aria-label="К заказам"]').trigger('click');
    expect(wrapper.emitted('close')).toHaveLength(1);
    await wrapper.setProps({ customerName: title });
    expect(wrapper.get('[data-order-header-customer]').text()).toBe(title);
  });

  it('edits in the same compact layout and restores keyboard focus on apply and Escape', async () => {
    make();
    const headerClasses = wrapper.get('header').attributes('class');
    await wrapper.get('[aria-label^="Изменить название:"]').trigger('click');
    const input = wrapper.get('[aria-label="Название заказа"]');
    expect(document.activeElement).toBe(input.element);
    expect(wrapper.get('header').attributes('class')).toBe(headerClasses);
    expect(wrapper.get('[data-order-header-customer]').text()).toBe(customerName);
    await input.setValue('Новое название');
    expect(wrapper.emitted('update:title')?.at(-1)).toEqual(['Новое название']);
    await input.trigger('keydown', { key: 'Enter' });
    expect(document.activeElement).toBe(wrapper.get('[aria-label^="Изменить название:"]').element);
    await wrapper.get('[aria-label^="Изменить название:"]').trigger('click');
    await wrapper.get('[aria-label="Название заказа"]').trigger('keydown', { key: 'Escape' });
    expect(document.activeElement).toBe(wrapper.get('[aria-label^="Изменить название:"]').element);
  });

  it('keeps the menu in the compact layout and restores its trigger focus on Escape', async () => {
    make();
    const headerClasses = wrapper.get('header').attributes('class');
    const trigger = wrapper.get('[aria-label="Дополнительные действия"]');
    await trigger.trigger('click');
    expect(wrapper.get('header').attributes('class')).toBe(headerClasses);
    const menu = wrapper.get('[aria-label="Действия с заказом"]');
    expect(menu.element.contains(document.activeElement)).toBe(true);
    await menu.trigger('keydown', { key: 'Escape' });
    expect(wrapper.find('[aria-label="Действия с заказом"]').exists()).toBe(false);
    expect(document.activeElement).toBe(trigger.element);
    expect(trigger.attributes('aria-expanded')).toBe('false');
  });

  it('shows distinct save states and a retry action even when failed edits are no longer dirty', async () => {
    make();
    expect(wrapper.get('[role="status"]').text()).toBe('Сохранено');
    await wrapper.setProps({ dirty: true });
    expect(wrapper.get('[role="status"]').text()).toBe('Есть изменения');
    await wrapper.setProps({ saving: true });
    expect(wrapper.get('[role="status"]').text()).toBe('Сохраняем');
    expect(wrapper.get('[aria-label="Сохраняем изменения"]').attributes('disabled')).toBeDefined();
    await wrapper.setProps({ saving: false, dirty: false, saveFailed: true, saveStatusText: 'Сохранено' });
    expect(wrapper.get('[role="status"]').text()).toBe('Не удалось сохранить');
    await wrapper.get('[aria-label="Повторить сохранение"]').trigger('click');
    expect(wrapper.emitted('save')).toHaveLength(1);
    await wrapper.get('[aria-label="Автосохранение заказа"]').trigger('click');
    expect(wrapper.emitted('toggle-autosave')).toHaveLength(1);
  });

  it('shows customer in the expanded presentation as well', async () => {
    wrapper = mount(OrderWorkspaceHeader, { props: { ...props, workspace: false } });
    expect(wrapper.text()).toContain(customerName);
  });
});
