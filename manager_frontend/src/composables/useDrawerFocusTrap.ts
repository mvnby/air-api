import { onScopeDispose, ref, type Ref } from 'vue';

const focusableSelector = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export const useDrawerFocusTrap = (container: Ref<HTMLElement | null>) => {
  const previousFocus = ref<HTMLElement | null>(null);

  const captureFocus = () => {
    previousFocus.value = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  };
  const focusContainer = () => container.value?.focus();
  const restoreFocus = () => previousFocus.value?.focus?.();
  const trapFocus = (event: KeyboardEvent) => {
    if (event.key !== 'Tab') return;
    const drawer = container.value;
    if (!drawer) return;
    const focusable = Array.from(drawer.querySelectorAll<HTMLElement>(focusableSelector))
      .filter((element) => element.offsetParent !== null);
    if (!focusable.length) {
      event.preventDefault();
      drawer.focus();
      return;
    }
    const first = focusable[0]!;
    const last = focusable[focusable.length - 1]!;
    const current = document.activeElement;
    if (current === drawer) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
      return;
    }
    if (event.shiftKey && current === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && current === last) {
      event.preventDefault();
      first.focus();
    }
  };

  onScopeDispose(restoreFocus);
  return { captureFocus, focusContainer, restoreFocus, trapFocus };
};
