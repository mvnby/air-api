import { computed, inject, onScopeDispose, provide, shallowRef, type InjectionKey, type ShallowRef } from 'vue';

type ContextHeader = { target: ShallowRef<HTMLElement | null>; register: () => () => void };
const contextHeaderKey: InjectionKey<ContextHeader> = Symbol('manager-context-header');
export const provideManagerContextHeader = () => {
  const target = shallowRef<HTMLElement | null>(null);
  const owners = shallowRef(new Set<symbol>());
  provide(contextHeaderKey, { target, register: () => {
    const id = Symbol(); owners.value = new Set([...owners.value, id]);
    return () => { const next = new Set(owners.value); next.delete(id); owners.value = next; };
  } });
  return { target, active: computed(() => owners.value.size > 0) };
};
export const useManagerContextHeader = () => {
  const context = inject(contextHeaderKey, null);
  if (context) onScopeDispose(context.register());
  return context;
};
