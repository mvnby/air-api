import { computed, inject, onScopeDispose, provide, shallowRef, type InjectionKey, type ShallowRef } from 'vue';

type ContextHeader = { target: ShallowRef<HTMLElement | null>; register: (compact: () => boolean) => () => void };
const contextHeaderKey: InjectionKey<ContextHeader> = Symbol('manager-context-header');
export const provideManagerContextHeader = () => {
  const target = shallowRef<HTMLElement | null>(null);
  const owners = shallowRef(new Map<symbol, () => boolean>());
  provide(contextHeaderKey, { target, register: compact => {
    const id = Symbol(); owners.value = new Map([...owners.value, [id, compact]]);
    return () => { const next = new Map(owners.value); next.delete(id); owners.value = next; };
  } });
  return {
    target,
    active: computed(() => owners.value.size > 0),
    compact: computed(() => owners.value.size > 0 && [...owners.value.values()].every(value => value())),
  };
};
export const useManagerContextHeader = (compact: () => boolean = () => false) => {
  const context = inject(contextHeaderKey, null);
  if (context) onScopeDispose(context.register(compact));
  return context;
};
