import { computed, onScopeDispose, ref, watch, type Ref } from 'vue';
import { getApiErrorMessage } from '../utils/api-errors';
import { moneyConflict } from '../services/worker-money';
export const useMoneyCommand = (options: { scope: Readonly<Ref<string>>; allowed: () => boolean; beforeAction?: () => Promise<boolean>; onSuccess: () => Promise<void>; onBusy?: (value: boolean) => void }) => {
  const draft = ref<{ label: string; send: () => PromiseLike<unknown> } | null>(null), busy = ref(false), error = ref(''), stale = ref(false);
  let generation = 0;
  const pending = computed(() => busy.value || draft.value !== null);
  const reset = () => { draft.value = null; error.value = ''; stale.value = false; };
  const begin = (label: string, send: () => PromiseLike<unknown>) => { if (!pending.value && options.allowed()) { error.value = ''; stale.value = false; draft.value = { label, send }; } };
  const submit = async () => {
    if (!draft.value || busy.value || stale.value || !options.allowed()) return;
    const request = generation, operation = draft.value.send; busy.value = true; error.value = '';
    try {
      if (options.beforeAction && !await options.beforeAction()) return;
      if (request !== generation || !options.allowed()) return;
      await operation(); if (request !== generation) return;
      reset(); await options.onSuccess();
    } catch (cause) { if (request === generation) { stale.value = moneyConflict(cause); error.value = stale.value ? 'Данные изменились. Обновите и проверьте операцию.' : `${getApiErrorMessage(cause)}. Повторное подтверждение проверит эту же операцию.`; } }
    finally { if (request === generation) busy.value = false; }
  };
  watch(pending, value => options.onBusy?.(value), { flush: 'sync' });
  watch(options.scope, () => { ++generation; reset(); busy.value = false; }, { flush: 'sync' });
  onScopeDispose(() => { ++generation; options.onBusy?.(false); });
  return { draft, busy, pending, error, stale, begin, submit, reset };
};
