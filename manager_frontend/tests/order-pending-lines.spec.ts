import { effectScope, nextTick, ref } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useOrderPendingLines } from '../src/composables/useOrderPendingLines';
import { confirmDialog } from '../src/services/ui-feedback';

vi.mock('../src/services/ui-feedback', () => ({ confirmDialog: vi.fn() }));
const scopes: ReturnType<typeof effectScope>[] = [];
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
};
const fixture = () => {
  const pending = ref(true), active = ref(true), blocked = ref(false), scope = ref('customer:order:proposal');
  const apply = vi.fn().mockResolvedValue(true), save = vi.fn().mockResolvedValue(true), focus = vi.fn().mockResolvedValue(undefined);
  const effect = effectScope(); scopes.push(effect);
  const guard = effect.run(() => useOrderPendingLines({ pending, active, blocked, scope, apply, save, focus }))!;
  return { guard, pending, active, blocked, scope, apply, save, focus, effect };
};
afterEach(() => { scopes.splice(0).forEach(scope => scope.stop()); vi.resetAllMocks(); });

describe('pending proposal line navigation', () => {
  it('explains that the working copy is excluded and keeps it intact when returning to input', async () => {
    vi.mocked(confirmDialog).mockResolvedValue(false);
    const f = fixture();
    expect(await f.guard.finish()).toBe(false);
    expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({
      description: expect.stringContaining('ещё не входят в предложение'), cancelText: 'Продолжить ввод',
    }));
    expect(f.focus).toHaveBeenCalledOnce(); expect(f.apply).not.toHaveBeenCalled(); expect(f.save).not.toHaveBeenCalled();
  });

  it('only leaves after explicit acceptance, validation and successful durable saving', async () => {
    vi.mocked(confirmDialog).mockResolvedValue(true);
    const f = fixture(), saved = deferred<boolean>(); f.save.mockReturnValue(saved.promise);
    const result = f.guard.finish(); await vi.waitFor(() => expect(f.save).toHaveBeenCalledOnce());
    expect(f.guard.busy.value).toBe(true); expect(await f.guard.finish()).toBe(false);
    expect(f.apply).toHaveBeenCalledOnce(); saved.resolve(true);
    expect(await result).toBe(true); expect(f.guard.busy.value).toBe(false);
  });

  it('explicit Save applies the working copy without an extra confirmation', async () => {
    const f = fixture(); expect(await f.guard.finish(false)).toBe(true);
    expect(confirmDialog).not.toHaveBeenCalled(); expect(f.apply).toHaveBeenCalledOnce(); expect(f.save).toHaveBeenCalledOnce();
  });

  it('returns to the invalid row without saving any partial set of lines', async () => {
    const f = fixture(); f.apply.mockResolvedValue(false);
    expect(await f.guard.finish(false)).toBe(false);
    expect(f.focus).toHaveBeenCalledOnce(); expect(f.save).not.toHaveBeenCalled();
  });

  it('blocks leaving when saving fails, while allowing retry', async () => {
    const f = fixture(); f.save.mockResolvedValueOnce(false);
    f.apply.mockImplementation(async () => { f.pending.value = false; return true; });
    expect(await f.guard.finish(false)).toBe(false);
    expect(f.pending.value).toBe(false);
    expect(await f.guard.finish()).toBe(true);
    expect(f.apply).toHaveBeenCalledOnce(); expect(f.save).toHaveBeenCalledTimes(2);
    expect(confirmDialog).not.toHaveBeenCalled();
  });

  it.each(['scope', 'active', 'dispose'] as const)('ignores a stale confirmation after %s changes', async change => {
    const confirmed = deferred<boolean>(); vi.mocked(confirmDialog).mockReturnValue(confirmed.promise);
    const f = fixture(), result = f.guard.finish();
    if (change === 'scope') f.scope.value = 'other:order:proposal';
    if (change === 'active') f.active.value = false;
    if (change === 'dispose') f.effect.stop();
    confirmed.resolve(true); expect(await result).toBe(false);
    expect(f.apply).not.toHaveBeenCalled(); expect(f.save).not.toHaveBeenCalled(); expect(f.focus).not.toHaveBeenCalled();
  });

  it('does not save or navigate if the context changes while loading its line editor', async () => {
    const f = fixture(), loaded = deferred<boolean>();
    f.apply.mockImplementation(async current => { await loaded.promise; return current(); });
    const result = f.guard.finish(false); await nextTick(); f.scope.value = 'another-order'; loaded.resolve(true);
    expect(await result).toBe(false); expect(f.save).not.toHaveBeenCalled();
  });

  it('keeps read-only and conflict views navigable when no line is being changed', async () => {
    const f = fixture(); f.pending.value = false; f.blocked.value = true;
    expect(await f.guard.finish()).toBe(true); expect(confirmDialog).not.toHaveBeenCalled(); expect(f.apply).not.toHaveBeenCalled();
  });
});
