import { defineComponent, h, nextTick, ref } from 'vue';
import { mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useOrderKeyboardViewport } from '../src/composables/useOrderKeyboardViewport';

let wrapper: VueWrapper;
let viewport: EventTarget & { height: number; offsetTop: number; scale: number };
let state: ReturnType<typeof useOrderKeyboardViewport>;
const show = ref(true), owner = ref<number | null>(1);
const observers: Array<{ callback: ResizeObserverCallback; disconnect: ReturnType<typeof vi.fn> }> = [];
const rect = (top: number, bottom: number) => ({ top, bottom, height: bottom - top } as DOMRect);
const settle = async () => { await nextTick(); await vi.advanceTimersByTimeAsync(20); };
const resize = async (height: number, offsetTop = 0, scale = 1) => {
  Object.assign(viewport, { height, offsetTop, scale });
  viewport.dispatchEvent(new Event('resize')); await settle();
};
const start = async () => {
  wrapper = mount(defineComponent({ setup() {
    const root = ref<HTMLElement | null>(null);
    state = useOrderKeyboardViewport(root, () => owner.value);
    return () => show.value ? h('aside', { ref:root }, [
      h('input', { 'aria-label':'Order title' }),
      h('div', { 'data-order-scroll':'' }, [h('div', [
        h('div', { class:'order-line-form' }, [h('textarea', { 'aria-label':'Line title' }), h('input', { type:'number', 'aria-label':'Quantity' })]),
        h('div', { 'data-line-editor-actions':'' }, [h('button', 'Cancel'), h('button', 'Add')]),
      ])]),
    ]) : null;
  } }), { attachTo:document.body });
  await nextTick();
};
const line = () => wrapper.get<HTMLTextAreaElement>('[aria-label="Line title"]').element;
beforeEach(() => {
  show.value = true; owner.value = 1; observers.length = 0;
  vi.useFakeTimers();
  vi.stubGlobal('innerHeight', 844);
  viewport = Object.assign(new EventTarget(), { height:844, offsetTop:0, scale:1 });
  vi.stubGlobal('visualViewport', viewport);
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(() => cb(0), 16));
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
  vi.stubGlobal('ResizeObserver', class {
    disconnect = vi.fn();
    constructor(callback: ResizeObserverCallback) { observers.push({ callback, disconnect:this.disconnect }); }
    observe() {}
  });
});
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('order keyboard viewport lifecycle', () => {
  it('retains line dimensions through field→button→BODY until the actual viewport restores', async () => {
    await start(); line().focus(); await resize(500);
    expect(state.keyboardOpen.value).toBe(true); expect(state.lineKeyboardOpen.value).toBe(true);
    const style = { ...state.keyboardStyle.value };
    wrapper.get('button').element.focus(); await settle();
    expect(state.keyboardStyle.value).toEqual(style);
    expect(state.lineKeyboardOpen.value).toBe(true);
    (document.activeElement as HTMLElement).blur(); await settle();
    expect(state.keyboardStyle.value).toEqual(style);
    await resize(844);
    expect(state.keyboardOpen.value).toBe(false); expect(state.lineKeyboardOpen.value).toBe(false);
    expect(state.keyboardStyle.value.maxHeight).toBeUndefined();
  });

  it('constrains ordinary title editing without treating it as a line session', async () => {
    await start(); wrapper.get<HTMLInputElement>('[aria-label="Order title"]').element.focus();
    await resize(500);
    expect(state.keyboardOpen.value).toBe(true); expect(state.lineKeyboardOpen.value).toBe(false);
    expect(state.keyboardStyle.value.maxHeight).toBe('500px');
    expect(state.keyboardStyle.value['--order-line-field-max-height']).toBeUndefined();
  });

  it('ignores reduced viewport without an editable session and clears on scale/real resize', async () => {
    await start(); await resize(500); expect(state.keyboardOpen.value).toBe(false);
    line().focus(); await settle(); expect(state.keyboardOpen.value).toBe(true);
    await resize(500, 0, 1.5); expect(state.keyboardOpen.value).toBe(false);
    await resize(844); expect(state.lineKeyboardOpen.value).toBe(false);
    await resize(500); expect(state.keyboardOpen.value).toBe(true);
    await resize(0); expect(state.keyboardOpen.value).toBe(false);
  });

  it('releases the session on order change, close, and detached workspace', async () => {
    await start(); line().focus(); await resize(500);
    owner.value = 2; await settle(); expect(state.keyboardOpen.value).toBe(false);
    line().blur(); line().focus(); await settle(); expect(state.lineKeyboardOpen.value).toBe(true);
    owner.value = null; await settle(); expect(state.keyboardOpen.value).toBe(false);
    show.value = false; await settle();
    expect(observers[0].disconnect).toHaveBeenCalled();
    await resize(360, 80); expect(state.keyboardOpen.value).toBe(false);
  });

  it.each([0, 80])('reveals the field above line actions inside visualViewport offset %i', async offset => {
    await start(); vi.stubGlobal('innerHeight', 684);
    const scroll = wrapper.get<HTMLElement>('[data-order-scroll]').element;
    const field = wrapper.get<HTMLInputElement>('[aria-label="Quantity"]').element;
    vi.spyOn(scroll, 'getBoundingClientRect').mockReturnValue(rect(63, 360 + offset));
    vi.spyOn(wrapper.get('[data-line-editor-actions]').element, 'getBoundingClientRect').mockReturnValue(rect(287 + offset, 348 + offset));
    vi.spyOn(field, 'getBoundingClientRect').mockImplementation(() => rect(330 + offset - scroll.scrollTop, 375 + offset - scroll.scrollTop));
    field.focus(); await resize(360, offset);
    expect(field.getBoundingClientRect().bottom).toBeLessThanOrEqual(279 + offset);
    expect(field.getBoundingClientRect().top).toBeGreaterThanOrEqual(Math.max(63, offset) + 8);
    expect(state.keyboardStyle.value.maxHeight).toBe(`${360 + offset}px`);
    // Panning above the visible top must also be corrected, not just the bottom.
    scroll.scrollTop = 300; viewport.dispatchEvent(new Event('scroll')); await settle();
    expect(field.getBoundingClientRect().top).toBeGreaterThanOrEqual(Math.max(63, offset) + 8);
  });

  it('owns input and resize observation for a workspace created after mount', async () => {
    show.value = false; await start(); show.value = true; await settle();
    const root = wrapper.get('aside').element;
    const remove = vi.spyOn(root, 'removeEventListener');
    const scroll = wrapper.get<HTMLElement>('[data-order-scroll]').element;
    let fieldTop = 200;
    vi.spyOn(scroll, 'getBoundingClientRect').mockReturnValue(rect(63, 500));
    vi.spyOn(wrapper.get('[data-line-editor-actions]').element, 'getBoundingClientRect').mockReturnValue(rect(427, 488));
    vi.spyOn(line(), 'getBoundingClientRect').mockImplementation(() => rect(fieldTop - scroll.scrollTop, fieldTop + 64 - scroll.scrollTop));
    line().focus(); await resize(500);
    fieldTop = 600; await wrapper.get('textarea').trigger('input'); await settle();
    expect(line().getBoundingClientRect().bottom).toBeLessThanOrEqual(419);
    fieldTop = 700; observers[0].callback([], {} as ResizeObserver); await settle();
    expect(line().getBoundingClientRect().bottom).toBeLessThanOrEqual(419);
    show.value = false; await settle();
    expect(remove).toHaveBeenCalledWith('input', expect.any(Function));
    expect(state.keyboardOpen.value).toBe(false);
  });
});
