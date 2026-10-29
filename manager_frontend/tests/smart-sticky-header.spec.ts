import { defineComponent, h, nextTick, ref } from 'vue';
import { mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSmartStickyHeader } from '../src/composables/useSmartStickyHeader';

let wrapper: VueWrapper;
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => window.setTimeout(() => callback(0), 16));
  vi.stubGlobal('cancelAnimationFrame', (id: number) => window.clearTimeout(id));
});
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.unstubAllGlobals(); });

const fixture = async () => {
  let state!: ReturnType<typeof useSmartStickyHeader>;
  wrapper = mount(defineComponent({ setup() {
    const container = ref<HTMLElement | null>(null);
    state = useSmartStickyHeader(container);
    return () => h('div', { ref: container });
  } }));
  await nextTick();
  const scroll = async (top: number) => {
    (wrapper.element as HTMLElement).scrollTop = top;
    await wrapper.trigger('scroll');
    await vi.advanceTimersByTimeAsync(20);
  };
  const settle = async () => { await vi.advanceTimersByTimeAsync(400); await nextTick(); };
  return { state, scroll, settle };
};

describe('smart header scroll and layout compensation', () => {
  it('reveals controls when the manager returns to the real top during compaction', async () => {
    const f = await fixture();
    await f.scroll(160); expect(f.state.compact.value).toBe(true);
    await f.scroll(70); // The larger viewport clamps scrollTop after collapsing.
    await f.scroll(0); // User scroll arrives before the resize has settled.
    await f.settle();
    expect(f.state.compact.value).toBe(false);
    await f.scroll(10); await f.scroll(0); await f.settle();
    expect(f.state.compact.value).toBe(false);
  });

  it('preserves compaction across layout correction and tiny upward jitter', async () => {
    const f = await fixture();
    await f.scroll(160); await f.scroll(62); await f.settle();
    expect(f.state.compact.value).toBe(true);
    await f.scroll(54); expect(f.state.compact.value).toBe(true);
    await f.scroll(20); expect(f.state.compact.value).toBe(false);
  });

  it('returns from a compensated position to the real top after compaction has settled', async () => {
    const f = await fixture();
    await f.scroll(160); await f.scroll(62); await f.settle();
    await f.scroll(0); expect(f.state.compact.value).toBe(false);
    await f.settle(); expect(f.state.compact.value).toBe(false);
  });
});
