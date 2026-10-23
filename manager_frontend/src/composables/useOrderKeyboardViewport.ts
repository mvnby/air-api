import { computed, onMounted, onScopeDispose, ref, type Ref } from 'vue';

/** Keep the existing workspace and its single footer above an overlay keyboard. */
export function useOrderKeyboardViewport(workspace: Ref<HTMLElement | null>) {
  const maxHeight = ref<string>();
  const keyboardOpen = ref(false);
  let frame = 0;
  const update = () => {
    const viewport = window.visualViewport;
    const root = workspace.value;
    const field = document.activeElement;
    const editing = field instanceof HTMLElement && root?.contains(field)
      && field.matches('input, textarea, [contenteditable="true"]');
    keyboardOpen.value = Boolean(viewport && editing && viewport.scale === 1
      && window.innerHeight - viewport.height > 120);
    maxHeight.value = keyboardOpen.value && viewport && root
      ? `${Math.max(0, viewport.height + viewport.offsetTop - root.getBoundingClientRect().top)}px` : undefined;
    cancelAnimationFrame(frame);
    if (keyboardOpen.value && field instanceof HTMLElement) frame = requestAnimationFrame(() => {
      const scroll = field.closest<HTMLElement>('[data-order-scroll]');
      if (!scroll) return;
      const box = field.getBoundingClientRect(), area = scroll.getBoundingClientRect();
      if (box.top < area.top + 8) scroll.scrollTop += box.top - area.top - 8;
      else if (box.bottom > area.bottom - 8) scroll.scrollTop += box.bottom - area.bottom + 8;
    });
  };
  onMounted(() => {
    window.visualViewport?.addEventListener('resize', update);
    window.visualViewport?.addEventListener('scroll', update);
    document.addEventListener('focusin', update);
    document.addEventListener('focusout', update);
  });
  onScopeDispose(() => {
    cancelAnimationFrame(frame);
    window.visualViewport?.removeEventListener('resize', update);
    window.visualViewport?.removeEventListener('scroll', update);
    document.removeEventListener('focusin', update);
    document.removeEventListener('focusout', update);
  });
  return { keyboardOpen, keyboardStyle: computed(() => ({ maxHeight: maxHeight.value })) };
}
