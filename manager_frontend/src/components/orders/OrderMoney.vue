<script setup lang="ts">
import MoneyAmount from '../money/MoneyAmount.vue';
import { formatMoneyAmount } from './order-utils';
defineProps<{ value?: number | null }>();
</script>

<template>
  <MoneyAmount :value="value" :formatted-value="value == null ? undefined : formatMoneyAmount(value)" />
</template>
