import { shallowRef, watch, type Ref } from 'vue';

// A phone keyboard can shrink the visible area without changing CSS viewport units.
export function useDialogViewport(open: Readonly<Ref<boolean>>) {
  const style = shallowRef<Record<string, string>>();
  watch(open, (visible, _previous, onCleanup) => {
    const viewport = window.visualViewport;
    if (!visible || !viewport) {
      style.value = undefined;
      return;
    }
    const measure = () => {
      style.value = {
        '--kitlane-dialog-top': `${viewport.offsetTop}px`,
        '--kitlane-dialog-height': `${viewport.height}px`,
      };
    };
    measure();
    viewport.addEventListener('resize', measure);
    viewport.addEventListener('scroll', measure);
    onCleanup(() => {
      viewport.removeEventListener('resize', measure);
      viewport.removeEventListener('scroll', measure);
    });
  }, { immediate: true });
  return style;
}
