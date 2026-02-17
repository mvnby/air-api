import { onBeforeUnmount, ref, watch, type Ref } from 'vue';
import IMask, { type InputMask } from 'imask';

type PhoneModelRef = Ref<string>;

export function useBelarusPhoneMask(
  inputRef: Ref<HTMLInputElement | null>,
  modelRef: PhoneModelRef,
  options?: { lazy?: boolean; placeholderChar?: string },
) {
  const isComplete = ref(false);
  const unmaskedValue = ref('');

  let mask: InputMask<any> | null = null;

  const syncState = () => {
    if (!mask) {
      isComplete.value = false;
      unmaskedValue.value = '';
      return;
    }
    isComplete.value = Boolean(mask.masked.isComplete);
    unmaskedValue.value = mask.unmaskedValue || '';
  };

  const destroyMask = () => {
    if (mask) {
      mask.destroy();
      mask = null;
    }
    syncState();
  };

  const initMask = (input: HTMLInputElement | null) => {
    destroyMask();
    if (!input) return;

    mask = IMask(input, {
      mask: '+{375} (00) 000-00-00',
      lazy: options?.lazy ?? false,
      placeholderChar: options?.placeholderChar ?? '_',
    });

    if (modelRef.value) {
      mask.value = modelRef.value;
    }

    mask.on('accept', () => {
      if (!mask) return;
      if (modelRef.value !== mask.value) {
        modelRef.value = mask.value;
      }
      syncState();
    });

    syncState();
  };

  watch(inputRef, (input) => {
    initMask(input);
  });

  watch(
    modelRef,
    (value) => {
      if (!mask) return;
      if (value !== mask.value) {
        mask.value = value || '';
      }
      syncState();
    },
    { flush: 'post' },
  );

  onBeforeUnmount(() => {
    destroyMask();
  });

  return {
    isComplete,
    unmaskedValue,
  };
}
