import { afterEach, describe, expect, it, vi } from 'vitest';
import { canNavigateAway, isApprovedUnloadEvent, registerUnsavedNavigationGuard, runGuardedNavigation, runGuardedUnload } from '../src/services/unsaved-navigation-guard';

describe('unsaved navigation guard', () => {
  let unregister: (() => void) | undefined;
  afterEach(() => unregister?.());

  it('blocks navigation until the active editor permits it', async () => {
    unregister = registerUnsavedNavigationGuard(() => false);
    expect(await canNavigateAway()).toBe(false);
    unregister();
    unregister = registerUnsavedNavigationGuard(async () => true);
    expect(await canNavigateAway()).toBe(true);
  });

  it('protects the order page while a nested editor is open and after it closes', async () => {
    const page = vi.fn(async () => false);
    const nested = vi.fn(async () => true);
    unregister = registerUnsavedNavigationGuard(page);
    const closeNested = registerUnsavedNavigationGuard(nested);
    try {
      expect(await canNavigateAway()).toBe(false);
      expect(nested).toHaveBeenCalledOnce();
      expect(page).toHaveBeenCalledOnce();
      closeNested();
      expect(await canNavigateAway()).toBe(false);
      expect(page).toHaveBeenCalledTimes(2);
    } finally { closeNested(); }
  });

  it('keeps the accepted location when navigation is rejected', async () => {
    const accept = vi.fn();
    const reject = vi.fn();
    unregister = registerUnsavedNavigationGuard(() => false);

    expect(await runGuardedNavigation(accept, reject)).toBe(false);
    expect(accept).not.toHaveBeenCalled();
    expect(reject).toHaveBeenCalledOnce();
  });

  it('marks only the first unload event after the guards approve', async () => {
    unregister = registerUnsavedNavigationGuard(() => true);
    const approved = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent;
    const later = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent;
    expect(await runGuardedUnload(() => { window.dispatchEvent(approved); })).toBe(true);
    expect(isApprovedUnloadEvent(approved)).toBe(true);
    window.dispatchEvent(later);
    expect(isApprovedUnloadEvent(later)).toBe(false);
  });

  it('makes approval available before the marker listener runs and shares it only within that event', async () => {
    unregister = registerUnsavedNavigationGuard(() => true);
    const approved = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent;
    const later = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent;
    expect(await runGuardedUnload(() => {
      // Simulate the native Window ordering: an older editor handler checks before the late capture listener.
      expect(isApprovedUnloadEvent(approved)).toBe(true);
      expect(isApprovedUnloadEvent(approved)).toBe(true);
      window.dispatchEvent(approved);
    })).toBe(true);
    expect(isApprovedUnloadEvent(later)).toBe(false);
  });

  it('does not consume the approved unload on another event type', async () => {
    const unrelated = new Event('click') as BeforeUnloadEvent;
    const approved = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent;
    expect(await runGuardedUnload(() => {
      expect(isApprovedUnloadEvent(unrelated)).toBe(false);
      expect(isApprovedUnloadEvent(approved)).toBe(true);
      window.dispatchEvent(approved);
    })).toBe(true);
  });

  it('does not approve any unload after a canceled guard', async () => {
    unregister = registerUnsavedNavigationGuard(() => false);
    const unload = vi.fn();
    expect(await runGuardedUnload(unload)).toBe(false);
    expect(unload).not.toHaveBeenCalled();
    const later = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent;
    window.dispatchEvent(later);
    expect(isApprovedUnloadEvent(later)).toBe(false);
  });

  it('cleans the one-event listener if starting the unload throws', async () => {
    const failure = new Error('Reload failed');
    await expect(runGuardedUnload(() => { throw failure; })).rejects.toBe(failure);
    const later = new Event('beforeunload', { cancelable: true }) as BeforeUnloadEvent;
    window.dispatchEvent(later);
    expect(isApprovedUnloadEvent(later)).toBe(false);
    expect(await runGuardedNavigation(vi.fn())).toBe(true);
  });

  it('does not open a second guard while the first decision is pending', async () => {
    let decide!: (value: boolean) => void;
    const guard = vi.fn(() => new Promise<boolean>(resolve => { decide = resolve; }));
    unregister = registerUnsavedNavigationGuard(guard);
    const first = runGuardedNavigation(vi.fn());
    const restore = vi.fn();

    expect(await runGuardedNavigation(vi.fn(), restore)).toBe(false);
    expect(guard).toHaveBeenCalledOnce();
    expect(restore).toHaveBeenCalledOnce();
    decide(true);
    expect(await first).toBe(true);
  });
});
