<script setup lang="ts">
import { computed } from 'vue';
import BynSymbol from './BynSymbol.vue';

const props = defineProps<{ value?: number | null }>();

const hasValue = computed(() => typeof props.value === 'number' && Number.isFinite(props.value));
const formattedValue = computed(() => hasValue.value
  ? props.value!.toLocaleString('ru-BY', { maximumFractionDigits: 2 })
  : '');
</script>

<template>
  <span v-if="hasValue" class="inline-flex items-center whitespace-nowrap">
    <span>{{ formattedValue }}</span><span class="sr-only"> BYN</span><BynSymbol class="ml-[0.24em]" />
  </span>
  <span v-else aria-label="Нет данных">—</span>
</template>
