import { nextTick, onScopeDispose, ref, watch, type Ref } from 'vue';
import { confirmDialog } from '../services/ui-feedback';

type Options = {
  pending: Readonly<Ref<boolean>>;
  active: Readonly<Ref<boolean>>;
  scope: Readonly<Ref<string>>;
  blocked: Readonly<Ref<boolean>>;
  apply: (current: () => boolean) => Promise<boolean>;
  focus: (current: () => boolean) => Promise<void>;
  save: () => Promise<boolean>;
};

// A line editor owns a working copy. Leaving it must never silently publish or
// omit that copy from the proposal the manager is about to use.
export const useOrderPendingLines = (options: Options) => {
  const busy = ref(false);
  let disposed = false;
  let controller: AbortController | null = null;
  let awaitingSaveScope: string | null = null;
  const invalidate = () => { controller?.abort(); awaitingSaveScope = null; };
  watch([options.scope, options.active], invalidate, { flush: 'sync' });
  onScopeDispose(() => { disposed = true; invalidate(); });

  const finish = async (ask = true): Promise<boolean> => {
    if (busy.value || disposed || !options.active.value) return false;
    const hasPendingInput = options.pending.value;
    if (!hasPendingInput && awaitingSaveScope !== options.scope.value) return true;
    if (options.blocked.value) return false;
    const scope = options.scope.value;
    const request = new AbortController();
    controller = request;
    busy.value = true;
    const current = () => !disposed && !request.signal.aborted && options.active.value
      && options.scope.value === scope && !options.blocked.value;
    try {
      if (hasPendingInput && ask) {
        const proceed = await confirmDialog({
          title: 'Применить введённые позиции?',
          description: 'Введённые товары, услуги или их изменения ещё не входят в предложение. Примените и сохраните их перед переходом или продолжите заполнение.',
          confirmText: 'Применить и сохранить',
          cancelText: 'Продолжить ввод',
          signal: request.signal,
        });
        if (!current()) return false;
        if (!proceed) { await options.focus(current); return false; }
      }
      if (!current()) return false;
      if (hasPendingInput && !await options.apply(current)) {
        if (current()) await options.focus(current);
        return false;
      }
      // Applying clears the editors, but a failed save must keep the same
      // navigation barrier until these committed values reach the server.
      awaitingSaveScope = scope;
      await nextTick();
      if (!current() || !await options.save()) return false;
      if (!current()) return false;
      awaitingSaveScope = null;
      return true;
    } finally {
      if (controller === request) controller = null;
      busy.value = false;
    }
  };

  return { busy, finish };
};
