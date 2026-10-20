import { onScopeDispose, watch } from 'vue';

const properties = ['overflow-x', 'overflow-y'] as const;
type ScrollLock = { users: number; previous: { property: string; value: string; priority: string }[] };
const locks = new Map<HTMLElement, ScrollLock>();

export const useDocumentScrollLock = (open: () => boolean) => {
  let release: (() => void) | undefined;
  watch(open, isOpen => {
    release?.();
    release = undefined;
    if (!isOpen || typeof document === 'undefined') return;

    // Lock the viewport root; child dialogs keep ownership of their body locks.
    const root = document.documentElement;
    let lock = locks.get(root);
    if (!lock) {
      lock = { users: 0, previous: properties.map(property => ({
        property, value: root.style.getPropertyValue(property), priority: root.style.getPropertyPriority(property),
      })) };
      locks.set(root, lock);
      properties.forEach(property => root.style.setProperty(property, 'hidden'));
    }
    const acquired = lock;
    acquired.users += 1;
    release = () => {
      acquired.users -= 1;
      if (acquired.users) return;
      acquired.previous.forEach(({ property, value, priority }) => {
        if (value) root.style.setProperty(property, value, priority);
        else root.style.removeProperty(property);
      });
      locks.delete(root);
    };
  }, { immediate: true, flush: 'sync' });
  onScopeDispose(() => release?.());
};
