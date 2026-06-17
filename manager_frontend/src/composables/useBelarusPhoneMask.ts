import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue';
import { formatPhoneForDisplay, isInternationalPhoneComplete, normalizePhoneForApi } from '../utils/phone';

type PhoneModelRef = Ref<string>;

export function useBelarusPhoneMask(
  inputRef: Ref<HTMLInputElement | null>,
  modelRef: PhoneModelRef,
  options?: { lazy?: boolean; placeholderChar?: string; defaultPrefix?: string },
) {
  const defaultPrefix = options?.defaultPrefix ?? '+375 ';
  const isComplete = computed(() => isInternationalPhoneComplete(modelRef.value || ''));
  const unmaskedValue = ref('');
  let currentInput: HTMLInputElement | null = null;

  const syncState = () => {
    unmaskedValue.value = normalizePhoneForApi(modelRef.value || '');
  };

  const applyDefaultPrefix = () => {
    if (!(modelRef.value || '').trim()) {
      modelRef.value = defaultPrefix;
    }
    syncState();
  };

  const formatCurrentValue = () => {
    const formatted = formatPhoneForDisplay(modelRef.value || '');
    if (formatted !== modelRef.value) {
      modelRef.value = formatted;
    }
    syncState();
  };

  const detachInput = () => {
    if (currentInput) {
      currentInput.removeEventListener('focus', applyDefaultPrefix);
      currentInput.removeEventListener('blur', formatCurrentValue);
      currentInput = null;
    }
  };

  const attachInput = (input: HTMLInputElement | null) => {
    detachInput();
    currentInput = input;
    currentInput?.addEventListener('focus', applyDefaultPrefix);
    currentInput?.addEventListener('blur', formatCurrentValue);
    syncState();
  };

  watch(inputRef, (input) => {
    attachInput(input);
  }, { immediate: true });

  watch(
    modelRef,
    () => syncState(),
    { flush: 'post' },
  );

  onBeforeUnmount(() => {
    detachInput();
  });

  return {
    isComplete,
    unmaskedValue,
  };
}
