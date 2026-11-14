import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { defineComponent, h, onScopeDispose, ref } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineManagerAsyncComponent, MANAGER_MODULE_TIMEOUT_MS } from '../src/services/manager-async-component';
import { managerModuleReloadKey, MODULE_DIAGNOSTICS_KEY, MODULE_DIAGNOSTICS_LIMIT, recordModuleFailure } from '../src/services/manager-module-recovery';
import { registerUnsavedNavigationGuard } from '../src/services/unsaved-navigation-guard';
import { navigateManager, startManagerNavigation } from '../src/services/manager-navigation-history';
import ManagerModuleRecoveryHost from '../src/components/manager/ManagerModuleRecoveryHost.vue';

let wrapper: VueWrapper | undefined;
let unregister: (() => void) | undefined;
let stopNavigation: (() => void) | undefined;
const reload = vi.fn();
const diagnostics = () => JSON.parse(sessionStorage.getItem(MODULE_DIAGNOSTICS_KEY) || '[]');
const options = () => ({ global: { provide: { [managerModuleReloadKey as symbol]: reload }, config: { errorHandler: vi.fn() } } });
const preloadFailure = () => {
  const event = new Event('vite:preloadError', { cancelable: true });
  Object.assign(event, { payload: new Error('https://secret.test/order/781?token=secret&customer=private') });
  window.dispatchEvent(event);
  return event;
};

beforeEach(() => {
  reload.mockClear();
  sessionStorage.clear();
  window.history.replaceState({}, '', '/manager/orders/781?token=secret&customer=private');
});
afterEach(() => {
  wrapper?.unmount(); wrapper = undefined;
  unregister?.(); unregister = undefined;
  stopNavigation?.(); stopNavigation = undefined;
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('Manager module loading and safe recovery', () => {
  it('keeps imports lazy, shows loading immediately, then renders the loaded view', async () => {
    let resolve!: (value: ReturnType<typeof defineComponent>) => void;
    const loader = vi.fn(() => new Promise<ReturnType<typeof defineComponent>>(accept => { resolve = accept; }));
    const Route = defineManagerAsyncComponent('OrdersKanbanView', loader);
    expect(loader).not.toHaveBeenCalled();
    wrapper = mount(defineComponent({ render: () => h('main', [h(Route)]) }), options());
    expect(wrapper.get('[role="status"]').text()).toBe('Загружаем раздел…');
    await flushPromises();
    resolve(defineComponent({ render: () => h('p', 'Заказы') }));
    await flushPromises();
    expect(wrapper.text()).toBe('Заказы');
    expect(diagnostics()).toEqual([]);
  });

  it('shows a rejected import and keeps other menu navigation usable without automatic retries', async () => {
    const loader = vi.fn().mockRejectedValue(new Error('https://secret.test/module.js?token=private'));
    const Route = defineManagerAsyncComponent('OrdersKanbanView', loader);
    const path = ref(window.location.pathname);
    stopNavigation = startManagerNavigation(() => { path.value = window.location.pathname; }, () => window.location.pathname);
    wrapper = mount(defineComponent({ render: () => h('main', [
      h('nav', [h('button', { onClick: () => navigateManager('/manager/products') }, 'Каталог')]),
      path.value.includes('/orders') ? h(Route) : h('p', { 'data-testid': 'other-route' }, 'Каталог открыт'),
    ]) }), options());
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить раздел');
    expect(wrapper.text()).toContain('Обновить страницу');
    expect(loader).toHaveBeenCalledOnce();
    expect(reload).not.toHaveBeenCalled();
    expect(diagnostics()[0]).toMatchObject({ module: 'OrdersKanbanView', category: 'route', code: 'import-failed' });
    expect(JSON.stringify(diagnostics())).not.toMatch(/secret|private|token|781|https/);
    await wrapper.get('nav button').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="other-route"]').text()).toBe('Каталог открыт');
    expect(loader).toHaveBeenCalledOnce();
  });

  it('ends a stalled load after a finite timeout and ignores late completion without reload loops', async () => {
    vi.useFakeTimers();
    let resolve!: (value: ReturnType<typeof defineComponent>) => void;
    const loader = vi.fn(() => new Promise<ReturnType<typeof defineComponent>>(accept => { resolve = accept; }));
    const Route = defineManagerAsyncComponent('ProductsView', loader);
    wrapper = mount(defineComponent({ render: () => h('main', [h(Route)]) }), options());
    await flushPromises();
    await vi.advanceTimersByTimeAsync(MANAGER_MODULE_TIMEOUT_MS - 1);
    expect(wrapper.text()).toContain('Загружаем раздел');
    await vi.advanceTimersByTimeAsync(1);
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить раздел');
    expect(diagnostics()[0].code).toBe('timeout');
    resolve(defineComponent({ render: () => h('p', 'Поздний ответ') }));
    await flushPromises();
    await vi.advanceTimersByTimeAsync(MANAGER_MODULE_TIMEOUT_MS * 3);
    expect(wrapper.text()).not.toContain('Поздний ответ');
    expect(reload).not.toHaveBeenCalled();
    expect(loader).toHaveBeenCalledOnce();
  });

  it('keeps editor state and guard mounted after a nested preload failure; reload requires approval', async () => {
    let allow = false;
    const guard = vi.fn(() => allow);
    const disposed = vi.fn();
    const Editor = defineComponent({ setup() {
      const draft = ref('Несохранённый текст');
      const unregisterEditor = registerUnsavedNavigationGuard(guard);
      onScopeDispose(() => { unregisterEditor(); disposed(); });
      return () => h('input', { value: draft.value, onInput: (event: Event) => { draft.value = (event.target as HTMLInputElement).value; } });
    } });
    wrapper = mount(defineComponent({ render: () => h('main', [h(ManagerModuleRecoveryHost), h(Editor)]) }), options());
    const event = preloadFailure();
    await flushPromises();
    expect(event.defaultPrevented).toBe(false);
    expect(wrapper.get('input').element.value).toBe('Несохранённый текст');
    expect(disposed).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(guard).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain('Обновление отменено');
    expect(wrapper.get('input').element.value).toBe('Несохранённый текст');
    expect(disposed).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
    allow = true;
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(reload).toHaveBeenCalledOnce();
    expect(guard).toHaveBeenCalledTimes(2);
    await wrapper.get('button').trigger('click');
    expect(reload).toHaveBeenCalledOnce();
    expect(JSON.stringify(diagnostics())).not.toMatch(/secret|private|token|781|https/);
    wrapper.unmount(); wrapper = undefined;
    const count = diagnostics().length;
    preloadFailure();
    expect(diagnostics()).toHaveLength(count);
  });

  it('shows panel import failures without replacing the surrounding editor', async () => {
    const Panel = defineManagerAsyncComponent('CustomerDocumentsPanel', () => Promise.reject(new Error('404')), 'panel');
    wrapper = mount(defineComponent({ render: () => h('div', [h('input', { value: 'Черновик' }), h(Panel)]) }), options());
    await flushPromises();
    expect(wrapper.get('input').element.value).toBe('Черновик');
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить раздел');
    expect(diagnostics()[0]).toMatchObject({ module: 'CustomerDocumentsPanel', category: 'panel', code: 'import-failed' });
  });

  it('handles a synchronous loader failure and a failed save barrier without automatic reload', async () => {
    const Route = defineManagerAsyncComponent('ProductsView', () => { throw new Error('private'); });
    wrapper = mount(defineComponent({ render: () => h('main', [h(Route)]) }), options());
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить раздел');
    unregister = registerUnsavedNavigationGuard(() => { throw new Error('private save error'); });
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(reload).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('Не удалось обновить страницу');
    expect(wrapper.get('button').attributes('disabled')).toBeUndefined();
  });

  it('caps diagnostics and strips unexpected existing fields without logging exception payloads', () => {
    const time = new Date().toISOString();
    sessionStorage.setItem(MODULE_DIAGNOSTICS_KEY, JSON.stringify([
      { module: 'OrdersKanbanView', category: 'route', code: 'timeout', time, token: 'private' },
      { module: 'Order-781-secret', category: 'route', code: 'timeout', time },
    ]));
    recordModuleFailure('ProductsView', 'route', 'timeout');
    expect(diagnostics()).toHaveLength(2);
    expect(diagnostics()[0]).toEqual({ module: 'OrdersKanbanView', category: 'route', code: 'timeout', time });
    for (let index = 0; index < MODULE_DIAGNOSTICS_LIMIT + 5; index++) recordModuleFailure('ProductsView', 'route', 'timeout');
    expect(diagnostics()).toHaveLength(MODULE_DIAGNOSTICS_LIMIT);
    expect(Object.keys(diagnostics()[0]).sort()).toEqual(['category', 'code', 'module', 'time']);
    sessionStorage.setItem(MODULE_DIAGNOSTICS_KEY, '{malformed');
    recordModuleFailure('ProductsView', 'route', 'timeout');
    expect(diagnostics()).toHaveLength(1);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('unavailable'); });
    expect(() => recordModuleFailure('ProductsView', 'route', 'timeout')).not.toThrow();
  });
});
