import { computed, onScopeDispose, ref, watch, type Ref } from 'vue';

type Options = {
  enabled: Ref<boolean>;
  ready: Readonly<Ref<boolean>>;
  scope: Readonly<Ref<string>>;
  snapshot: Readonly<Ref<string>>;
  dirty: Readonly<Ref<boolean>>;
  save: () => Promise<boolean>;
  delay?: number;
};

/** One write at a time; a barrier also drains edits made while a write was in flight. */
export const useOrderAutosave = (options: Options) => {
  const saving = ref(false);
  const failed = ref(false);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let pending: Promise<boolean> | null = null;
  let disposed = false;
  let generation = 0;
  let barrierRequested = false;

  const cancelScheduled = () => {
    clearTimeout(timer);
    timer = undefined;
  };

  const flush = async (automatic = false): Promise<boolean> => {
    cancelScheduled();
    if (pending) {
      if (!automatic) barrierRequested = true;
      return pending;
    }
    if (!options.ready.value || disposed) return false;
    barrierRequested = !automatic;
    const currentGeneration = generation;
    saving.value = true;
    failed.value = false;
    // Yield once so pending is installed before save can synchronously change refs.
    pending = Promise.resolve().then(async () => {
      while (options.dirty.value) {
        if (disposed || generation !== currentGeneration || !options.ready.value) return false;
        if (automatic && !barrierRequested && !options.enabled.value) return false;
        const before = options.snapshot.value;
        if (!await options.save()) {
          if (generation === currentGeneration) failed.value = true;
          return false;
        }
        if (generation !== currentGeneration || disposed) return false;
        if (options.dirty.value && before === options.snapshot.value) {
          failed.value = true;
          return false;
        }
      }
      return true;
    }).catch(() => {
      if (generation === currentGeneration) failed.value = true;
      return false;
    }).finally(() => {
      pending = null;
      saving.value = false;
      barrierRequested = false;
      if (!disposed && generation !== currentGeneration && options.enabled.value && options.ready.value && options.dirty.value) {
        timer = setTimeout(() => void flush(true), options.delay ?? 700);
      }
    });
    return pending;
  };

  watch([options.scope, options.ready], () => {
    cancelScheduled();
    generation += 1;
    failed.value = false;
  }, { flush: 'sync' });

  watch([options.snapshot, options.enabled, options.ready], () => {
    cancelScheduled();
    if (disposed || !options.enabled.value || !options.ready.value || !options.dirty.value || pending) return;
    failed.value = false;
    timer = setTimeout(() => void flush(true), options.delay ?? 700);
  }, { flush: 'post' });

  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (!options.ready.value || (!options.dirty.value && !saving.value)) return;
    event.preventDefault();
    event.returnValue = '';
  };
  window.addEventListener('beforeunload', beforeUnload);
  onScopeDispose(() => {
    disposed = true;
    cancelScheduled();
    window.removeEventListener('beforeunload', beforeUnload);
  });

  const statusText = computed(() => saving.value
    ? 'Сохраняем…'
    : failed.value ? 'Не сохранено — повторите'
      : options.dirty.value ? (options.enabled.value ? 'Ожидает сохранения' : 'Есть изменения')
        : 'Сохранено');

  const waitForIdle = async () => { if (pending) await pending; };
  return { saving, failed, flush, waitForIdle, cancelScheduled, statusText };
};
