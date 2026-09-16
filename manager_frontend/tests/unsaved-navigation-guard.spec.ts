import { afterEach, describe, expect, it, vi } from 'vitest';
import { canNavigateAway, registerUnsavedNavigationGuard, runGuardedNavigation } from '../src/services/unsaved-navigation-guard';

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

  it('keeps the accepted location when navigation is rejected', async () => {
    const accept = vi.fn();
    const reject = vi.fn();
    unregister = registerUnsavedNavigationGuard(() => false);

    expect(await runGuardedNavigation(accept, reject)).toBe(false);
    expect(accept).not.toHaveBeenCalled();
    expect(reject).toHaveBeenCalledOnce();
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
