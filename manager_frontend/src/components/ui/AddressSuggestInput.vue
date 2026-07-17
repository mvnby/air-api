<script setup lang="ts">
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue';
import { AlertCircle, CheckCircle2, LoaderCircle, RotateCcw, X } from 'lucide-vue-next';
import { ManagerSettingsService } from '../../client';
import type { CancelablePromise } from '../../client/core/CancelablePromise';
import type { AddressSuggestResponse } from '../../client/models/AddressSuggestResponse';
import {
  ADDRESS_SUGGEST_DEBOUNCE_MS,
  hasEnoughAddressCharacters,
  normalizeAddressQuery,
  type NormalizedAddressSuggestion,
} from '../../utils/address';

type GeoPriority = {
  latitude?: number | null;
  longitude?: number | null;
};

const props = withDefaults(defineProps<{
  modelValue: string;
  label?: string;
  placeholder?: string;
  error?: string;
  inputClass?: string | string[] | Record<string, boolean>;
  disabled?: boolean;
  readonly?: boolean;
  required?: boolean;
  showStatus?: boolean;
  autocomplete?: string;
  geoPriority?: GeoPriority | null;
}>(), {
  label: '',
  placeholder: 'Введите адрес',
  error: '',
  inputClass: '',
  disabled: false,
  readonly: false,
  required: false,
  showStatus: true,
  autocomplete: 'street-address',
  geoPriority: null,
});

const emit = defineEmits<{
  'update:modelValue': [value: string];
  input: [value: string];
  select: [value: NormalizedAddressSuggestion];
  'selection-cleared': [];
}>();

const inputId = `address-${useId()}`;
const listboxId = `${inputId}-listbox`;
const statusId = `${inputId}-status`;
const inputValue = ref(props.modelValue || '');
const suggestions = ref<NormalizedAddressSuggestion[]>([]);
const loading = ref(false);
const serviceError = ref(false);
const open = ref(false);
const focused = ref(false);
const activeIndex = ref(-1);
const confirmedValue = ref('');
const touched = ref(false);
const blurredAfterEdit = ref(false);
let debounceTimer: number | null = null;
let activeRequest: CancelablePromise<AddressSuggestResponse> | null = null;
let requestId = 0;

const suggestionCache = new Map<string, NormalizedAddressSuggestion[]>();
const MAX_CACHE_SIZE = 30;

const status = computed<'idle' | 'confirmed' | 'manual' | 'error'>(() => {
  if (serviceError.value && touched.value) return 'error';
  if (confirmedValue.value && confirmedValue.value === inputValue.value) return 'confirmed';
  if (touched.value && blurredAfterEdit.value && inputValue.value.trim()) return 'manual';
  return 'idle';
});

const statusText = computed(() => {
  if (status.value === 'confirmed') return 'Адрес выбран из подсказок';
  if (status.value === 'manual') return 'Адрес введён вручную и не подтверждён подсказками';
  if (status.value === 'error') return 'Не удалось проверить адрес. Его можно сохранить вручную';
  return '';
});

const describedBy = computed(() => [props.error ? `${inputId}-error` : '', statusText.value ? statusId : ''].filter(Boolean).join(' ') || undefined);

const cancelPending = () => {
  if (debounceTimer !== null) {
    window.clearTimeout(debounceTimer);
    debounceTimer = null;
  }
  if (activeRequest) {
    requestId += 1;
    activeRequest.cancel();
  }
  activeRequest = null;
};

const closeSuggestions = () => {
  open.value = false;
  activeIndex.value = -1;
};

const setSuggestions = (items: NormalizedAddressSuggestion[]) => {
  suggestions.value = items;
  open.value = focused.value && items.length > 0;
  activeIndex.value = items.length ? 0 : -1;
};

const cacheSuggestions = (query: string, items: NormalizedAddressSuggestion[]) => {
  if (suggestionCache.size >= MAX_CACHE_SIZE) {
    const oldestKey = suggestionCache.keys().next().value;
    if (oldestKey) suggestionCache.delete(oldestKey);
  }
  suggestionCache.set(query, items);
};

const fetchSuggestions = async (rawQuery: string) => {
  const query = normalizeAddressQuery(rawQuery);
  if (!hasEnoughAddressCharacters(query)) {
    setSuggestions([]);
    return;
  }

  const cached = suggestionCache.get(query);
  if (cached) {
    serviceError.value = false;
    setSuggestions(cached);
    return;
  }

  activeRequest?.cancel();
  const currentRequestId = ++requestId;
  loading.value = true;
  serviceError.value = false;
  try {
    const latitude = props.geoPriority?.latitude ?? undefined;
    const longitude = props.geoPriority?.longitude ?? undefined;
    const hasCoordinatePriority = Number.isFinite(latitude) && Number.isFinite(longitude);
    const request = ManagerSettingsService.suggestAddress(
      query,
      hasCoordinatePriority ? latitude : undefined,
      hasCoordinatePriority ? longitude : undefined,
    );
    activeRequest = request;
    const response = await request;
    if (currentRequestId !== requestId || normalizeAddressQuery(inputValue.value) !== query) return;
    const items = (response.items || []) as NormalizedAddressSuggestion[];
    cacheSuggestions(query, items);
    setSuggestions(items);
  } catch (error) {
    if (currentRequestId !== requestId || activeRequest?.isCancelled) return;
    console.warn('Address suggestions are temporarily unavailable', error);
    serviceError.value = true;
    setSuggestions([]);
  } finally {
    if (currentRequestId === requestId) {
      loading.value = false;
      activeRequest = null;
    }
  }
};

const scheduleSuggestions = () => {
  cancelPending();
  const query = inputValue.value;
  if (!hasEnoughAddressCharacters(query)) {
    loading.value = false;
    serviceError.value = false;
    setSuggestions([]);
    return;
  }
  debounceTimer = window.setTimeout(() => {
    debounceTimer = null;
    void fetchSuggestions(query);
  }, ADDRESS_SUGGEST_DEBOUNCE_MS);
};

const onInput = (event: Event) => {
  const value = (event.target as HTMLInputElement).value;
  inputValue.value = value;
  emit('update:modelValue', value);
  emit('input', value);
  touched.value = true;
  blurredAfterEdit.value = false;
  serviceError.value = false;
  if (confirmedValue.value && value !== confirmedValue.value) {
    confirmedValue.value = '';
    emit('selection-cleared');
  }
  scheduleSuggestions();
};

const chooseSuggestion = (item: NormalizedAddressSuggestion) => {
  const value = item.value || item.title || '';
  cancelPending();
  inputValue.value = value;
  confirmedValue.value = value;
  touched.value = true;
  blurredAfterEdit.value = false;
  serviceError.value = false;
  emit('update:modelValue', value);
  emit('select', item);
  closeSuggestions();
};

const clear = () => {
  cancelPending();
  inputValue.value = '';
  confirmedValue.value = '';
  touched.value = true;
  blurredAfterEdit.value = false;
  serviceError.value = false;
  setSuggestions([]);
  emit('update:modelValue', '');
  emit('input', '');
  emit('selection-cleared');
};

const onFocus = () => {
  focused.value = true;
  if (suggestions.value.length) open.value = true;
};

const onBlur = () => {
  focused.value = false;
  blurredAfterEdit.value = touched.value && confirmedValue.value !== inputValue.value;
  window.setTimeout(closeSuggestions, 120);
};

const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    closeSuggestions();
    return;
  }
  if (event.key === 'Tab') {
    closeSuggestions();
    return;
  }
  if (!open.value || !suggestions.value.length) return;
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    activeIndex.value = (activeIndex.value + 1) % suggestions.value.length;
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    activeIndex.value = (activeIndex.value - 1 + suggestions.value.length) % suggestions.value.length;
  } else if (event.key === 'Enter' && activeIndex.value >= 0) {
    const item = suggestions.value[activeIndex.value];
    if (item) {
      event.preventDefault();
      chooseSuggestion(item);
    }
  }
};

const retry = () => {
  serviceError.value = false;
  scheduleSuggestions();
};

watch(() => props.modelValue, (value) => {
  const nextValue = value || '';
  if (nextValue === inputValue.value) return;
  cancelPending();
  inputValue.value = nextValue;
  confirmedValue.value = '';
  touched.value = false;
  blurredAfterEdit.value = false;
  serviceError.value = false;
  setSuggestions([]);
});

onBeforeUnmount(() => {
  requestId += 1;
  cancelPending();
});

</script>

<template>
  <div class="relative min-w-0">
    <label v-if="label" :for="inputId" class="field-label mb-1 block">{{ label }}</label>
    <div class="relative">
      <input
        :id="inputId"
        :value="inputValue"
        type="text"
        role="combobox"
        :class="['field-input w-full pr-20', inputClass, error ? 'border-red-500 focus:outline-red-400' : '']"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        :required="required"
        :autocomplete="autocomplete"
        :aria-expanded="open"
        :aria-controls="listboxId"
        :aria-activedescendant="activeIndex >= 0 ? `${inputId}-option-${activeIndex}` : undefined"
        :aria-describedby="describedBy"
        :aria-invalid="Boolean(error)"
        @input="onInput"
        @focus="onFocus"
        @blur="onBlur"
        @keydown="onKeydown"
      />
      <div class="absolute inset-y-0 right-2 flex items-center gap-1">
        <LoaderCircle v-if="loading" :size="17" class="animate-spin text-teal-600 dark:text-teal-300" aria-label="Проверяем адрес" />
        <button
          v-if="inputValue && !disabled && !readonly"
          type="button"
          class="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-500 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          aria-label="Очистить адрес"
          @mousedown.prevent
          @click="clear"
        >
          <X :size="15" />
        </button>
      </div>
    </div>

    <ul
      v-if="open && suggestions.length"
      :id="listboxId"
      role="listbox"
      class="absolute left-0 top-full z-[70] mt-1 max-h-60 w-full overflow-auto rounded-xl border border-slate-200 bg-white p-1 shadow-2xl ring-1 ring-black/5 dark:border-slate-700 dark:bg-slate-900"
    >
      <li
        v-for="(item, index) in suggestions"
        :id="`${inputId}-option-${index}`"
        :key="`${item.value}-${index}`"
        role="option"
        :aria-selected="activeIndex === index"
        class="cursor-pointer rounded-lg px-3 py-2 text-sm transition-colors"
        :class="activeIndex === index ? 'bg-teal-50 dark:bg-teal-500/15' : 'hover:bg-slate-50 dark:hover:bg-slate-800'"
        @mousemove="activeIndex = index"
        @mousedown.prevent="chooseSuggestion(item)"
      >
        <span class="block font-medium text-slate-900 dark:text-slate-100">{{ item.title || item.value }}</span>
        <span v-if="item.subtitle" class="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">{{ item.subtitle }}</span>
      </li>
    </ul>

    <p v-if="error" :id="`${inputId}-error`" class="mt-1 text-xs text-red-600 dark:text-red-300">{{ error }}</p>
    <div v-else-if="showStatus && statusText" :id="statusId" class="mt-1 flex items-start gap-1.5 text-xs" :class="status === 'confirmed' ? 'text-emerald-700 dark:text-emerald-300' : status === 'error' ? 'text-amber-700 dark:text-amber-300' : 'text-slate-500 dark:text-slate-400'">
      <CheckCircle2 v-if="status === 'confirmed'" :size="14" class="mt-px shrink-0" />
      <AlertCircle v-else :size="14" class="mt-px shrink-0" />
      <span>{{ statusText }}</span>
      <button v-if="status === 'error'" type="button" class="ml-1 inline-flex items-center gap-1 font-semibold underline underline-offset-2" @click="retry">
        <RotateCcw :size="12" /> Повторить
      </button>
    </div>
  </div>
</template>
