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

  // Helper: raw phone from DB looks like '375XXXXXXXXX' (12 digits)
  // IMask `unmaskedValue` only needs digits after the fixed '+375 ' prefix (9 digits)
  const applyValueToMask = (value: string) => {
    if (!mask) return;
    if (/^375\d{9}$/.test(value)) {
      // Raw format: strip the 375 country code
      mask.unmaskedValue = value.slice(3);
    } else {
      // Already formatted or partial
      mask.value = value;
    }
    mask.updateValue();
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
      applyValueToMask(modelRef.value);
      syncState();
      // Sync model to what the mask actually shows
      if (modelRef.value !== mask.value) {
        modelRef.value = mask.value;
      }
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
        // Keep IMask internals aligned when model changes programmatically.
        mask.updateValue();
        syncState();
      }
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
