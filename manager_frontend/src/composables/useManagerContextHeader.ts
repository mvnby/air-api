import { computed, inject, onScopeDispose, provide, shallowRef, type InjectionKey, type ShallowRef } from 'vue';

type ContextHeader = { target: ShallowRef<HTMLElement | null>; register: (compact: () => boolean) => () => void; registerWorkspaceChrome: (compact: () => boolean) => () => void };
const contextHeaderKey: InjectionKey<ContextHeader> = Symbol('manager-context-header');
export const provideManagerContextHeader = () => {
  const target = shallowRef<HTMLElement | null>(null);
  const owners = shallowRef(new Map<symbol, () => boolean>());
  const workspaceOwners = shallowRef(new Map<symbol, () => boolean>());
  const registerWorkspaceChrome = (compact: () => boolean) => {
    const id = Symbol(); workspaceOwners.value = new Map([...workspaceOwners.value, [id, compact]]);
    return () => { const next = new Map(workspaceOwners.value); next.delete(id); workspaceOwners.value = next; };
  };
  provide(contextHeaderKey, { target, registerWorkspaceChrome, register: compact => {
    const id = Symbol(); owners.value = new Map([...owners.value, [id, compact]]);
    return () => { const next = new Map(owners.value); next.delete(id); owners.value = next; };
  } });
  return {
    target,
    workspaceChromeCompact: computed(() => workspaceOwners.value.size > 0 && [...workspaceOwners.value.values()].every(value => value())),
    active: computed(() => owners.value.size > 0),
    compact: computed(() => owners.value.size > 0 && [...owners.value.values()].every(value => value())),
  };
};
export const useManagerContextHeader = (compact: () => boolean = () => false) => {
  const context = inject(contextHeaderKey, null);
  if (context) onScopeDispose(context.register(compact));
  return context;
};

// Workspace scroll owns shell chrome without registering a teleported page toolbar.
export const useManagerWorkspaceChrome = (compact: () => boolean) => {
  const context = inject(contextHeaderKey, null);
  if (context) onScopeDispose(context.registerWorkspaceChrome(compact));
};
