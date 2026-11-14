import { flushPromises, mount } from '@vue/test-utils';
import { defineComponent, h, ref } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MANAGER_MODULE_TIMEOUT_MS } from '../src/services/manager-module-loader';
import { MODULE_DIAGNOSTICS_KEY } from '../src/services/manager-module-recovery';
import OrderAsyncPanel from '../src/components/orders/OrderAsyncPanel.vue';
import { reloadManagerLocation } from '../src/services/manager-navigation-history';

vi.mock('../src/services/manager-navigation-history', () => ({ reloadManagerLocation: vi.fn().mockResolvedValue(false) }));

const Editor = defineComponent({ render: () => h('input', { 'aria-label': 'Поле раздела' }) });
const slots = { default: ({ component }: any) => h(component) };

afterEach(() => { vi.useRealTimers(); });

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

  it('ends a stalled attempt visibly, ignores its late result and preserves explicit ready retry', async () => {
    vi.useFakeTimers();
    sessionStorage.clear();
    let resolve!: (value: { default: typeof Editor }) => void;
    const slow = new Promise<{ default: typeof Editor }>(done => { resolve = done; });
    const load = vi.fn().mockImplementationOnce(() => slow).mockResolvedValue({ default: Editor });
    const panel = ref<{ ready: () => Promise<boolean> }>();
    const wrapper = mount(defineComponent({ render: () => h(OrderAsyncPanel, { ref: panel, load, label: 'Документы' }, slots) }));
    const ready = () => panel.value!.ready();
    const pending = ready();
    await vi.advanceTimersByTimeAsync(MANAGER_MODULE_TIMEOUT_MS - 1);
    expect(wrapper.get('[role="status"]').text()).toContain('Загружаем');
    await vi.advanceTimersByTimeAsync(1);
    expect(await pending).toBe(false);
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить');
    expect(wrapper.get('[aria-busy]').attributes('aria-busy')).toBe('false');
    expect(JSON.parse(sessionStorage.getItem(MODULE_DIAGNOSTICS_KEY)!)).toEqual([
      { module: 'OrderWorkspacePanel', category: 'panel', code: 'timeout', time: expect.any(String) },
    ]);
    resolve({ default: Editor });
    await flushPromises();
    await vi.advanceTimersByTimeAsync(MANAGER_MODULE_TIMEOUT_MS * 3);
    expect(wrapper.find('input').exists()).toBe(false);
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить');
    expect(load).toHaveBeenCalledOnce();
    expect(await ready()).toBe(true);
    expect(wrapper.get('input').exists()).toBe(true);
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
