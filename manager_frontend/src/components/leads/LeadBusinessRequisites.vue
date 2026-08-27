<script setup lang="ts">
import AddressSuggestInput from '../ui/AddressSuggestInput.vue';

defineProps<{
  inn: string;
  name: string;
  fullLegalName: string;
  legalAddress: string;
  iban: string;
  bic: string;
  bankName: string;
  isEgrLoading: boolean;
  isBankLoading: boolean;
}>();

const emit = defineEmits<{
  'update:inn': [value: string];
  'update:name': [value: string];
  'update:fullLegalName': [value: string];
  'update:legalAddress': [value: string];
  'update:iban': [value: string];
  'update:bic': [value: string];
  'update:bankName': [value: string];
  searchInput: [];
  innBlur: [];
  ibanBlur: [];
}>();

const inputValue = (event: Event) => (event.target as HTMLInputElement).value;
</script>

<template>
  <div class="grid grid-cols-1 gap-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-800/60 md:grid-cols-2">
    <label class="block text-xs font-semibold text-slate-500">
      УНП
      <span class="relative mt-1 block">
        <input :value="inn" type="text" class="w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900" placeholder="9 цифр" @input="emit('update:inn', inputValue($event)); emit('searchInput')" @blur="emit('innBlur')">
        <span v-if="isEgrLoading" class="absolute right-3 top-2.5"><span class="material-icons-round animate-spin text-sm text-teal-500">refresh</span></span>
      </span>
    </label>
    <label class="block text-xs font-semibold text-slate-500">
      Короткое название
      <input :value="name" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900" @input="emit('update:name', inputValue($event))">
    </label>
    <label class="block text-xs font-semibold text-slate-500 md:col-span-2">
      Полное юридическое название
      <input :value="fullLegalName" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900" @input="emit('update:fullLegalName', inputValue($event))">
    </label>
    <AddressSuggestInput :model-value="legalAddress" class="md:col-span-2" label="Юридический адрес" input-class="bg-white text-sm dark:bg-slate-900" @update:model-value="emit('update:legalAddress', $event)" />
    <label class="block text-xs font-semibold text-slate-500 md:col-span-2">
      IBAN
      <span class="relative mt-1 block">
        <input :value="iban" type="text" class="w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900" @input="emit('update:iban', inputValue($event))" @blur="emit('ibanBlur')">
        <span v-if="isBankLoading" class="absolute right-3 top-2.5"><span class="material-icons-round animate-spin text-sm text-teal-500">refresh</span></span>
      </span>
    </label>
    <label class="block text-xs font-semibold text-slate-500">
      BIC
      <input :value="bic" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900" @input="emit('update:bic', inputValue($event))">
    </label>
    <label class="block text-xs font-semibold text-slate-500">
      Банк
      <input :value="bankName" type="text" class="mt-1 w-full rounded-xl border-0 bg-white px-4 py-2.5 text-sm focus:ring-2 focus:ring-teal-500 dark:bg-slate-900" @input="emit('update:bankName', inputValue($event))">
    </label>
  </div>
</template>
