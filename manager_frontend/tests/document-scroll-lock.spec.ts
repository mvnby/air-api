import { effectScope, ref, type EffectScope } from 'vue';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { useDocumentScrollLock } from '../src/composables/useDocumentScrollLock';

const scopes: EffectScope[] = [];
const start = (initial = false) => {
  const open = ref(initial);
  const scope = effectScope();
  scopes.push(scope);
  scope.run(() => useDocumentScrollLock(() => open.value));
  return { open, scope };
};
let originalRoot: string;
let originalBody: string;
beforeEach(() => {
  originalRoot = document.documentElement.style.cssText;
  originalBody = document.body.style.cssText;
});
afterEach(() => {
  scopes.splice(0).forEach(scope => scope.stop());
  document.documentElement.style.cssText = originalRoot;
  document.body.style.cssText = originalBody;
});

describe('document scroll lock', () => {
  it('leaves a closed drawer alone and restores both axes and priorities after closing', () => {
    const root = document.documentElement;
    root.style.setProperty('overflow-x', 'clip', 'important');
    root.style.setProperty('overflow-y', 'scroll');
    const { open } = start();
    expect(root.style.overflowX).toBe('clip');
    open.value = true;
    expect(root.style.overflowX).toBe('hidden');
    expect(root.style.overflowY).toBe('hidden');
    open.value = false;
    expect(root.style.overflowX).toBe('clip');
    expect(root.style.getPropertyPriority('overflow-x')).toBe('important');
    expect(root.style.overflowY).toBe('scroll');
  });

  it('releases an initially open drawer on disposal without touching child dialog body styles', () => {
    document.body.style.overflow = 'auto';
    const { scope } = start(true);
    expect(document.documentElement.style.overflowX).toBe('hidden');
    expect(document.documentElement.style.overflowY).toBe('hidden');
    expect(document.body.style.overflow).toBe('auto');
    document.body.style.overflow = 'hidden';
    scope.stop();
    expect(document.documentElement.style.overflow).toBe('');
    expect(document.body.style.overflow).toBe('hidden');
  });

  it('keeps the root locked until the last drawer closes, including after reopening', () => {
    document.documentElement.style.overflow = 'auto';
    const first = start(true);
    const second = start(true);
    first.open.value = false;
    expect(document.documentElement.style.overflowX).toBe('hidden');
    expect(document.documentElement.style.overflowY).toBe('hidden');
    first.open.value = true;
    second.scope.stop();
    expect(document.documentElement.style.overflowX).toBe('hidden');
    expect(document.documentElement.style.overflowY).toBe('hidden');
    first.open.value = false;
    expect(document.documentElement.style.overflow).toBe('auto');
  });
});
