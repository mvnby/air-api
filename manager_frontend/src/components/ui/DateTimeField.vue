<script setup lang="ts">
import { CalendarDays } from 'lucide-vue-next';
import { computed, ref } from 'vue';

const props = withDefaults(
  defineProps<{
    modelValue?: string | null;
    label?: string;
    placeholder?: string;
    disabled?: boolean;
    required?: boolean;
    error?: string;
    id?: string;
    name?: string;
    ariaLabel?: string;
  }>(),
  {
    label: '',
    placeholder: '',
    disabled: false,
    required: false,
    error: '',
    id: '',
    name: '',
    ariaLabel: '',
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: string];
}>();

const inputRef = ref<HTMLInputElement | null>(null);

const localValue = computed({
  get: () => props.modelValue ?? '',
  set: (value: string) => emit('update:modelValue', value),
});

const openPicker = () => {
  if (props.disabled || !inputRef.value) return;
  const input = inputRef.value as HTMLInputElement & { showPicker?: () => void };
  if (typeof input.showPicker === 'function') {
    input.showPicker();
    return;
  }
  input.focus();
};
</script>

<template>
  <label class="field-label">
    <span v-if="label">{{ label }}</span>
    <div class="relative">
      <input
        :id="id || undefined"
        ref="inputRef"
        v-model="localValue"
        :name="name || undefined"
        :placeholder="placeholder || undefined"
        :disabled="disabled"
        :required="required"
        :aria-label="ariaLabel || label || 'Дата и время'"
        type="datetime-local"
        class="field-input pr-10"
        :class="error ? 'border-red-500 focus:outline-red-400' : ''"
      />
      <button
        type="button"
        class="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-300 hover:bg-slate-700/40 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="disabled"
        :aria-label="`Выбрать ${label || 'дату и время'}`"
        @click="openPicker"
      >
        <CalendarDays class="h-4 w-4" />
      </button>
    </div>
    <span v-if="error" class="text-xs text-red-300">{{ error }}</span>
  </label>
</template>
