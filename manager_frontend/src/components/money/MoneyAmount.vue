<script setup lang="ts">
import { computed } from 'vue';
import BynSymbol from './BynSymbol.vue';

const props = withDefaults(defineProps<{
  value?: number | null;
  currency?: string | null;
  // A numeric string from the field's existing formatter preserves its precision and rounding.
  formattedValue?: string;
}>(), { currency: 'BYN' });
const hasValue = computed(() => typeof props.value === 'number' && Number.isFinite(props.value));
const currencyCode = computed(() => props.currency || 'BYN');
const amount = computed(() => hasValue.value
  ? props.formattedValue ?? props.value!.toLocaleString('ru-BY', { maximumFractionDigits: 2 })
  : '');
</script>

<template>
  <span v-if="hasValue" class="inline-flex items-baseline whitespace-nowrap">
    <span>{{ amount }}<span v-if="currencyCode === 'BYN'" class="sr-only whitespace-pre"> BYN</span><span v-else>&nbsp;{{ currencyCode }}</span></span><BynSymbol v-if="currencyCode === 'BYN'" class="ml-[0.24em]" />
  </span>
  <span v-else aria-label="Нет данных">—</span>
</template>
