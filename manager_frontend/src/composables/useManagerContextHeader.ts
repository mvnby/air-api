import { computed, inject, onScopeDispose, provide, shallowRef, watch, type InjectionKey, type Ref, type ShallowRef } from 'vue';

type ContextHeader = {
  target: ShallowRef<HTMLElement | null>;
  workspaceActionsTarget: ShallowRef<HTMLElement | null>;
  register: (compact: () => boolean) => () => void;
  registerWorkspaceChrome: (compact: () => boolean) => () => void;
};
const contextHeaderKey: InjectionKey<ContextHeader> = Symbol('manager-context-header');
export const provideManagerContextHeader = () => {
  const target = shallowRef<HTMLElement | null>(null);
  const workspaceActionsTarget = shallowRef<HTMLElement | null>(null);
  const owners = shallowRef(new Map<symbol, () => boolean>());
  const workspaceOwners = shallowRef(new Map<symbol, () => boolean>());
  const registerWorkspaceChrome = (compact: () => boolean) => {
    const id = Symbol(); workspaceOwners.value = new Map([...workspaceOwners.value, [id, compact]]);
    return () => { const next = new Map(workspaceOwners.value); next.delete(id); workspaceOwners.value = next; };
  };
  provide(contextHeaderKey, { target, workspaceActionsTarget, registerWorkspaceChrome, register: compact => {
    const id = Symbol(); owners.value = new Map([...owners.value, [id, compact]]);
    return () => { const next = new Map(owners.value); next.delete(id); owners.value = next; };
  } });
  return {
    target,
    workspaceActionsTarget,
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

// Shell controls keep their instance and ownership while the order supplies their DOM host.
export const useManagerWorkspaceActions = (target: Ref<HTMLElement | null>, active: () => boolean) => {
  const context = inject(contextHeaderKey, null);
  if (!context) return false;
  let owned: HTMLElement | null = null;
  const release = () => {
    if (owned && context.workspaceActionsTarget.value === owned) context.workspaceActionsTarget.value = null;
    owned = null;
  };
  watch([target, active], ([element, enabled]) => {
    release();
    if (element && enabled) {
      owned = element;
      context.workspaceActionsTarget.value = element;
    }
  }, { immediate: true, flush: 'post' });
  onScopeDispose(release);
  return true;
};
