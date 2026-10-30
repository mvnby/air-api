import { computed, onMounted, onScopeDispose, ref, watch, type Ref } from 'vue';

const KEYBOARD_HEIGHT_DIFFERENCE_PX = 120;
const editable = 'input:not([type="checkbox"]):not([type="radio"]), textarea, [contenteditable="true"]';

/** Keep geometry stable from keyboard opening until its viewport actually restores. */
export function useOrderKeyboardViewport(workspace: Ref<HTMLElement | null>, scope?: () => unknown) {
  const maxHeight = ref<string>();
  const keyboardOpen = ref(false);
  const lineKeyboardOpen = ref(false);
  const viewportHeight = ref(0);
  let frame = 0;
  let observer: ResizeObserver | null = null;

  const reset = () => {
    cancelAnimationFrame(frame);
    frame = 0;
    keyboardOpen.value = false;
    lineKeyboardOpen.value = false;
    maxHeight.value = undefined;
  };
  const revealFocusedField = () => {
    frame = 0;
    const viewport = window.visualViewport;
    const root = workspace.value;
    const field = document.activeElement;
    if (!keyboardOpen.value || !viewport || !(field instanceof HTMLElement)
      || !root?.contains(field) || !field.matches(editable)) return;
    const scroll = field.closest<HTMLElement>('[data-order-scroll]');
    if (!scroll) return;
    const area = scroll.getBoundingClientRect();
    const actions = field.closest('.order-line-form')?.parentElement
      ?.querySelector<HTMLElement>('[data-line-editor-actions]')?.getBoundingClientRect();
    const top = Math.max(area.top, viewport.offsetTop) + 8;
    const bottom = Math.min(area.bottom, viewport.offsetTop + viewport.height,
      actions && actions.bottom > top && actions.top < area.bottom ? actions.top : area.bottom) - 8;
    if (bottom <= top) return;
    const box = field.getBoundingClientRect();
    const delta = box.top < top || box.height > bottom - top
      ? box.top - top : box.bottom > bottom ? box.bottom - bottom : 0;
    if (Math.abs(delta) > 1) scroll.scrollTop += delta;
  };
  const scheduleReveal = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(revealFocusedField);
  };
  const update = () => {
    const viewport = window.visualViewport;
    const root = workspace.value;
    if (!viewport || !root || viewport.scale !== 1 || viewport.height <= 0
      || window.innerHeight - viewport.height <= KEYBOARD_HEIGHT_DIFFERENCE_PX) {
      reset();
      return;
    }
    const field = document.activeElement;
    const editing = field instanceof HTMLElement && root.contains(field) && field.matches(editable);
    // A button/BODY focusout does not mean the OS has finished dismissing the
    // keyboard. Releasing here moves a touched action before its click arrives.
    if (editing) {
      keyboardOpen.value = true;
      if (field.closest('.order-line-form')) lineKeyboardOpen.value = true;
    }
    if (!keyboardOpen.value) return;
    viewportHeight.value = viewport.height;
    maxHeight.value = `${Math.max(0, viewport.height + viewport.offsetTop - root.getBoundingClientRect().top)}px`;
    scheduleReveal();
  };

  watch(workspace, (root, previous) => {
    previous?.removeEventListener('input', update);
    reset();
    root?.addEventListener('input', update);
    observer?.disconnect();
    if (root && typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(scheduleReveal);
      observer.observe(root);
      const scroll = root.querySelector('[data-order-scroll]');
      if (scroll) observer.observe(scroll);
    }
  }, { immediate: true, flush: 'post' });
  if (scope) watch(scope, reset, { flush: 'sync' });
  onMounted(() => {
    window.visualViewport?.addEventListener('resize', update);
    window.visualViewport?.addEventListener('scroll', update);
    window.addEventListener('resize', update);
    document.addEventListener('focusin', update);
    document.addEventListener('focusout', update);
  });
  onScopeDispose(() => {
    reset();
    observer?.disconnect();
    window.visualViewport?.removeEventListener('resize', update);
    window.visualViewport?.removeEventListener('scroll', update);
    window.removeEventListener('resize', update);
    document.removeEventListener('focusin', update);
    document.removeEventListener('focusout', update);
    workspace.value?.removeEventListener('input', update);
  });
  return {
    keyboardOpen,
    lineKeyboardOpen,
    keyboardStyle: computed(() => ({
      maxHeight: maxHeight.value,
      '--order-line-suggestions-height': lineKeyboardOpen.value ? `${Math.min(240, Math.max(88, viewportHeight.value * 0.4))}px` : undefined,
      '--order-line-field-max-height': lineKeyboardOpen.value ? `${Math.max(64, viewportHeight.value * 0.35)}px` : undefined,
    })),
  };
}
