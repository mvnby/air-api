import { flushPromises, mount } from '@vue/test-utils';
import { defineComponent, h } from 'vue';
import { describe, expect, it, vi } from 'vitest';
import OrderAsyncPanel from '../src/components/orders/OrderAsyncPanel.vue';

const Editor = defineComponent({ render: () => h('input', { 'aria-label': 'Поле раздела' }) });
const slots = { default: ({ component }: any) => h(component) };

describe('lazy order section', () => {
  it('shows a local failure and retries without blocking the page or reloading an opened form', async () => {
    const load = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ default: Editor });
    const wrapper = mount(OrderAsyncPanel, { props: { load, label: 'Документы' }, slots });
    expect(wrapper.get('[role="status"]').text()).toContain('Загружаем');
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить');
    await wrapper.get('button').trigger('click');
    await flushPromises();
    await wrapper.get('input').setValue('Черновик');
    await wrapper.setProps({ label: 'Другой заголовок' });
    expect(wrapper.get('input').element.value).toBe('Черновик');
    expect(load).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });

  it('does not render a disposed order section when its slow import resolves', async () => {
    let resolve!: (value: { default: typeof Editor }) => void;
    const slow = new Promise<{ default: typeof Editor }>(done => { resolve = done; });
    const wrapper = mount(OrderAsyncPanel, { props: { load: () => slow, label: 'Работы' }, slots });
    wrapper.unmount();
    resolve({ default: Editor });
    await flushPromises();
    expect(document.querySelector('[aria-label="Поле раздела"]')).toBeNull();
  });
});
