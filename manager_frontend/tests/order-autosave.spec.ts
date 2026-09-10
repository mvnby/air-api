import { computed, effectScope, nextTick, ref, type EffectScope } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useOrderAutosave } from '../src/composables/useOrderAutosave';

type Deferred = {
  promise: Promise<boolean>;
  resolve: (value: boolean) => void;
};

const deferred = (): Deferred => {
  let resolve!: (value: boolean) => void;
  const promise = new Promise<boolean>((done) => { resolve = done; });
  return { promise, resolve };
};

let scope: EffectScope;

const createAutosave = (save: () => Promise<boolean>, delay = 700) => {
  const snapshot = ref('saved');
  const saved = ref('saved');
  const ready = ref(true);
  const enabled = ref(true);
  const activeScope = ref('42:17');
  scope = effectScope();
  const autosave = scope.run(() => useOrderAutosave({
    enabled,
    ready,
    scope: activeScope,
    snapshot,
    dirty: computed(() => snapshot.value !== saved.value),
    save,
    delay,
  }))!;
  return { autosave, activeScope, enabled, ready, saved, snapshot };
};

afterEach(() => {
  scope?.stop();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('useOrderAutosave', () => {
  it('debounces rapid input into one save', async () => {
    vi.useFakeTimers();
    let saved!: ReturnType<typeof ref<string>>;
    let snapshot!: ReturnType<typeof ref<string>>;
    const save = vi.fn(async () => {
      saved.value = snapshot.value;
      return true;
    });
    const state = createAutosave(save);
    ({ saved, snapshot } = state);

    snapshot.value = 'первый ввод';
    await nextTick();
    snapshot.value = 'второй ввод';
    await nextTick();
    snapshot.value = 'последний ввод';
    await nextTick();
    await vi.advanceTimersByTimeAsync(699);

    expect(save).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);

    expect(save).toHaveBeenCalledOnce();
    expect(saved.value).toBe('последний ввод');
    expect(state.autosave.statusText.value).toBe('Сохранено');
  });

  it('serially drains edits made while a save is awaiting the API', async () => {
    vi.useFakeTimers();
    const calls: Array<{ completion: Deferred; snapshot: string }> = [];
    let saved!: ReturnType<typeof ref<string>>;
    let snapshot!: ReturnType<typeof ref<string>>;
    const save = vi.fn(() => {
      const completion = deferred();
      const submitted = snapshot.value;
      calls.push({ completion, snapshot: submitted });
      return completion.promise.then((result) => {
        if (result) saved.value = submitted;
        return result;
      });
    });
    const state = createAutosave(save);
    ({ saved, snapshot } = state);

    snapshot.value = 'первая правка';
    await nextTick();
    await vi.advanceTimersByTimeAsync(700);
    const drained = state.autosave.flush();
    expect(save).toHaveBeenCalledOnce();

    snapshot.value = 'правка во время запроса';
    await nextTick();
    calls[0].completion.resolve(true);
    await Promise.resolve();
    await Promise.resolve();

    expect(save).toHaveBeenCalledTimes(2);
    expect(calls[1].snapshot).toBe('правка во время запроса');
    calls[1].completion.resolve(true);

    await expect(drained).resolves.toBe(true);
    expect(saved.value).toBe('правка во время запроса');
  });

  it('keeps dirty state after a failed save without scheduling a busy loop', async () => {
    vi.useFakeTimers();
    const save = vi.fn().mockResolvedValue(false);
    const state = createAutosave(save);

    state.snapshot.value = 'несохранённая правка';
    await nextTick();
    await vi.advanceTimersByTimeAsync(700);
    await Promise.resolve();

    expect(save).toHaveBeenCalledOnce();
    expect(state.autosave.failed.value).toBe(true);
    expect(state.snapshot.value).not.toBe(state.saved.value);

    await vi.runAllTimersAsync();

    expect(save).toHaveBeenCalledOnce();
    expect(state.autosave.statusText.value).toBe('Не сохранено — повторите');
  });

  it('finishes only the in-flight write when autosave is switched off', async () => {
    vi.useFakeTimers();
    const response = deferred();
    const save = vi.fn(async () => {
      const submitted = state.snapshot.value;
      await response.promise;
      state.saved.value = submitted;
      return true;
    });
    const state = createAutosave(save);
    state.snapshot.value = 'отправлено';
    await nextTick();
    await vi.advanceTimersByTimeAsync(700);
    state.enabled.value = false;
    state.snapshot.value = 'ручная правка';
    response.resolve(true);
    await state.autosave.waitForIdle();
    await vi.advanceTimersByTimeAsync(1000);
    expect(save).toHaveBeenCalledOnce();
    expect(state.saved.value).toBe('отправлено');
    expect(state.snapshot.value).toBe('ручная правка');
    expect(state.autosave.failed.value).toBe(false);
  });
});
