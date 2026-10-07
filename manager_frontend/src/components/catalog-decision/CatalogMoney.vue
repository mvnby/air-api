<script setup lang="ts">
import MoneyAmount from '../money/MoneyAmount.vue';
defineProps<{ value?: number | null }>();
</script>

<template>
  <MoneyAmount :value="value" />
</template>
