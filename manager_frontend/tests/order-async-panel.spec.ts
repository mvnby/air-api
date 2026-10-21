import { flushPromises, mount } from '@vue/test-utils';
import { defineComponent, h } from 'vue';
import { describe, expect, it, vi } from 'vitest';
import OrderAsyncPanel from '../src/components/orders/OrderAsyncPanel.vue';
import { reloadManagerLocation } from '../src/services/manager-navigation-history';

vi.mock('../src/services/manager-navigation-history', () => ({ reloadManagerLocation: vi.fn().mockResolvedValue(false) }));

const Editor = defineComponent({ render: () => h('input', { 'aria-label': 'Поле раздела' }) });
const slots = { default: ({ component }: any) => h(component) };

describe('lazy order section', () => {
  it('shows a local import failure and recovers through guarded page refresh', async () => {
    const load = vi.fn().mockRejectedValue(new Error('offline'));
    const wrapper = mount(OrderAsyncPanel, { props: { load, label: 'Документы' }, slots });
    expect(wrapper.get('[role="status"]').text()).toContain('Загружаем');
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить');
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(reloadManagerLocation).toHaveBeenCalledOnce();
    expect(load).toHaveBeenCalledOnce();
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить');
    wrapper.unmount();
  });

  it('keeps an opened form mounted when other panel metadata changes', async () => {
    const load = vi.fn().mockResolvedValue({ default: Editor });
    const wrapper = mount(OrderAsyncPanel, { props: { load, label: 'Документы' }, slots });
    await flushPromises();
    await wrapper.get('input').setValue('Черновик');
    await wrapper.setProps({ label: 'Другой заголовок' });
    expect(wrapper.get('input').element.value).toBe('Черновик');
    expect(load).toHaveBeenCalledOnce();
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
