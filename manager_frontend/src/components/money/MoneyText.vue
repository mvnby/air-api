<script setup lang="ts">
import { computed } from 'vue';
import MoneyAmount from './MoneyAmount.vue';

const props = defineProps<{ text: string }>();
// Render only existing UI labels; keep the source text and its rounding unchanged.
const parts = computed(() => {
  const result: Array<{ text: string; value?: number }> = [];
  let offset = 0;
  for (const match of props.text.matchAll(/(-?\d(?:[\d\u00a0\u202f ]*\d)?(?:[.,]\d+)?)[ \u00a0\u202f]+BYN\b/g)) {
    result.push({ text: props.text.slice(offset, match.index) });
    const amount = match[1]!;
    result.push({ text: amount, value: Number(amount.replace(/[ \u00a0\u202f]/g, '').replace(',', '.')) });
    offset = match.index! + match[0].length;
  }
  result.push({ text: props.text.slice(offset) });
  return result;
});
</script>

<template>
  <span><template v-for="(part, index) in parts" :key="index"><MoneyAmount v-if="part.value !== undefined" :value="part.value" :formatted-value="part.text" /><template v-else>{{ part.text }}</template></template></span>
</template>
