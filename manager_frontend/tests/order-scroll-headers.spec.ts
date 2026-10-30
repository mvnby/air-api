import { defineComponent, h, nextTick, ref } from 'vue';
import { mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import KitlaneShell from '../src/components/kitlane/KitlaneShell.vue';
import OrderWorkspaceHeader from '../src/components/orders/OrderWorkspaceHeader.vue';
import { useManagerWorkspaceChrome } from '../src/composables/useManagerContextHeader';
import { focusInvalidLineEditor } from '../src/components/orders/order-line-drafts';
import { useSmartStickyHeader } from '../src/composables/useSmartStickyHeader';

let wrapper: VueWrapper;
const visible = ref(true);
let state: ReturnType<typeof useSmartStickyHeader>;
const Page = defineComponent({ setup() {
  const scroll = ref<HTMLElement | null>(null);
  state = useSmartStickyHeader(scroll, { retainCompactWhenContentFits: true });
  useManagerWorkspaceChrome(() => state.compact.value);
  return () => h('section', [h(OrderWorkspaceHeader, {
    workspace: true, compact: state.compact.value, orderId: 595, title: 'Тестовый заказ', workflow: 'maintenance',
    viewModel: { stageLabel: 'Предложение', stageAge: '', nextAction: { label: 'Продолжить' } } as any,
    total: 0, paid: 0, balance: 0, backLabel: 'К заказам',
  }), h('nav', { tabindex: 0 }, 'Документы'), h('div', { ref: scroll, 'data-order-scroll': '' })]);
} });
const start = async () => {
  visible.value = true;
  wrapper = mount(defineComponent({ setup: () => () => h(KitlaneShell, {
    workspace: true, name: 'Тест', contextKey: 'test', collapsed: true, mobileOpen: false, theme: 'light',
  }, { default: () => visible.value ? h(Page) : h('div', 'Главная'), account: () => h('button', { 'aria-expanded': false }, 'Профиль') }) }), { attachTo: document.body });
  await nextTick();
};
const settle = async () => { await vi.advanceTimersByTimeAsync(400); await nextTick(); };
const scroll = async (top: number) => {
  const scroller = wrapper.get('[data-order-scroll]');
  (scroller.element as HTMLElement).scrollTop = top;
  await scroller.trigger('scroll'); await vi.advanceTimersByTimeAsync(20);
};
const shellCollapsed = () => wrapper.get('.kitlane-topbar').classes().includes('is-scroll-collapsed');
const orderCollapsed = () => wrapper.getComponent(OrderWorkspaceHeader).attributes('data-scroll-collapsed') === 'true';
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(() => cb(0), 16));
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
});
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('order scroll owns the full shell header stack', () => {
  it('uses inner workspace scroll, keeps tabs and resets both headers at top', async () => {
    await start();
    window.dispatchEvent(new Event('scroll')); await settle();
    expect(shellCollapsed()).toBe(false); expect(orderCollapsed()).toBe(false);
    await scroll(240); await settle();
    expect(shellCollapsed()).toBe(true); expect(orderCollapsed()).toBe(true);
    expect(wrapper.get('nav').isVisible()).toBe(true);
    await scroll(0); await settle();
    expect(shellCollapsed()).toBe(false); expect(orderCollapsed()).toBe(false);
  });
  it('does not hide focused order controls or an open order menu', async () => {
    await start();
    const back = wrapper.get('[aria-label="К заказам"]'); (back.element as HTMLElement).focus();
    await scroll(240); await settle(); expect(orderCollapsed()).toBe(false);
    (back.element as HTMLElement).blur(); await nextTick(); expect(orderCollapsed()).toBe(true);
    state.reset(); await settle();
    await wrapper.get('[aria-label="Дополнительные действия"]').trigger('click');
    (document.activeElement as HTMLElement)?.blur();
    await scroll(400); await settle(); expect(orderCollapsed()).toBe(false);
    expect(wrapper.get('[aria-label="Действия с заказом"]').exists()).toBe(true);
    await wrapper.get('[aria-label="Действия с заказом"]').trigger('keydown', { key: 'Escape' });
    expect(orderCollapsed()).toBe(false);
    expect(document.activeElement).toBe(wrapper.get('[aria-label="Дополнительные действия"]').element);
  });
  it('protects shell focus and an open account menu independently, cleaning ownership on navigation', async () => {
    await start(); const account = wrapper.get('.kitlane-topbar button[aria-expanded]');
    (account.element as HTMLElement).focus();
    await scroll(240); await settle(); expect(shellCollapsed()).toBe(false);
    account.element.setAttribute('aria-expanded', 'true'); (account.element as HTMLElement).blur();
    await nextTick(); expect(shellCollapsed()).toBe(false);
    account.element.setAttribute('aria-expanded', 'false'); await nextTick(); await nextTick();
    expect(shellCollapsed()).toBe(true);
    visible.value = false; await nextTick(); expect(shellCollapsed()).toBe(false);
    visible.value = true; await nextTick(); await nextTick(); expect(shellCollapsed()).toBe(false);
  });
  it('stays collapsed after content clamps to zero and reveals on upward intent during resize', async () => {
    await start(); const element = wrapper.get('[data-order-scroll]').element;
    Object.defineProperties(element, { scrollHeight: { configurable: true, value: 500 }, clientHeight: { configurable: true, value: 600 } });
    await scroll(90); await scroll(0); await settle();
    expect(shellCollapsed()).toBe(true); expect(orderCollapsed()).toBe(true);
    await wrapper.get('[data-order-scroll]').trigger('wheel', { deltaY: -50 }); await settle();
    expect(shellCollapsed()).toBe(false); expect(orderCollapsed()).toBe(false);
    await scroll(180);
    await wrapper.get('[data-order-scroll]').trigger('wheel', { deltaY: -50 }); await settle();
    expect(shellCollapsed()).toBe(false); expect(orderCollapsed()).toBe(false);
  });
  it('reveals on an upward touch gesture when resizing consumed all overflow', async () => {
    await start(); const scroller = wrapper.get('[data-order-scroll]');
    Object.defineProperties(scroller.element, { scrollHeight: { value: 500 }, clientHeight: { value: 600 } });
    await scroll(100); await scroll(0); await settle();
    await scroller.trigger('touchstart', { touches: [{ clientY: 100 }] });
    await scroller.trigger('touchmove', { touches: [{ clientY: 150 }] }); await settle();
    expect(shellCollapsed()).toBe(false); expect(orderCollapsed()).toBe(false);
  });
  it('cancels pending layout work when reset', async () => {
    await start(); await scroll(200); state.reset();
    await scroll(380); // Browser anchoring while the expanded viewport becomes smaller.
    await settle(); expect(state.compact.value).toBe(false);
    await scroll(390); await settle(); expect(state.compact.value).toBe(false);
  });
});


describe('focused validation during full header expansion', () => {
  it('keeps an invalid field above sticky actions while the workspace resizes, then releases observation', async () => {
    let resize!: ResizeObserverCallback;
    const disconnect = vi.fn();
    vi.stubGlobal('ResizeObserver', class { constructor(callback: ResizeObserverCallback) { resize = callback; } observe() {} disconnect = disconnect; });
    const container = document.createElement('div'); container.dataset.orderScroll = '';
    container.innerHTML = '<div><input aria-invalid="true"><div data-line-editor-actions></div></div>';
    document.body.append(container);
    const row = container.firstElementChild as HTMLElement, field = row.querySelector('input')!;
    let shift = 0;
    const rect = (top: number, bottom: number) => ({ top, bottom, height: bottom - top } as DOMRect);
    vi.spyOn(container, 'getBoundingClientRect').mockImplementation(() => rect(100 + shift, 500));
    vi.spyOn(field, 'getBoundingClientRect').mockImplementation(() => rect(420 + shift - container.scrollTop, 460 + shift - container.scrollTop));
    vi.spyOn(row.lastElementChild!, 'getBoundingClientRect').mockReturnValue(rect(450, 500));
    container.scrollTo = vi.fn((options: ScrollToOptions) => { container.scrollTop = options.top || 0; }) as any;
    await focusInvalidLineEditor(row);
    shift = 140; resize([], {} as ResizeObserver);
    expect(document.activeElement).toBe(field);
    expect(field.getBoundingClientRect().bottom).toBeLessThanOrEqual(438);
    await vi.advanceTimersByTimeAsync(500);
    expect(disconnect).toHaveBeenCalledOnce();
    container.remove();
  });
});
