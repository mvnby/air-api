import { nextTick, onBeforeUnmount, type Ref, watch } from 'vue';

type DialogA11yOptions = {
  open: Readonly<Ref<boolean>>;
  dialogRef: Ref<HTMLElement | null>;
  initialFocusRef?: Ref<HTMLElement | null>;
  close: () => void;
};

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const focusableElements = (dialog: HTMLElement) => (
  [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)]
    .filter((element) => element.getClientRects().length > 0 && element.getAttribute('aria-hidden') !== 'true')
);

export const useDialogA11y = ({ open, dialogRef, initialFocusRef, close }: DialogA11yOptions) => {
  let previousFocus: HTMLElement | null = null;
  let listening = false;

  const restoreFocus = () => {
    if (previousFocus?.isConnected) previousFocus.focus();
    previousFocus = null;
  };

  const onKeydown = (event: KeyboardEvent) => {
    if (!open.value) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== 'Tab') return;

    const dialog = dialogRef.value;
    if (!dialog) return;
    const focusable = focusableElements(dialog);
    if (!focusable.length) {
      event.preventDefault();
      dialog.focus();
      return;
    }

    const first = focusable[0]!;
    const last = focusable[focusable.length - 1]!;
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !dialog.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const setListening = (value: boolean) => {
    if (value === listening) return;
    listening = value;
    if (value) document.addEventListener('keydown', onKeydown, true);
    else document.removeEventListener('keydown', onKeydown, true);
  };

  watch(open, async (isOpen) => {
    if (!isOpen) {
      setListening(false);
      restoreFocus();
      return;
    }
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setListening(true);
    await nextTick();
    const dialog = dialogRef.value;
    (initialFocusRef?.value || (dialog ? focusableElements(dialog)[0] : null) || dialog)?.focus();
  }, { immediate: true });

  onBeforeUnmount(() => {
    setListening(false);
    restoreFocus();
  });
};
