<script setup lang="ts">
import { computed } from 'vue';
import { parseLineText } from './line-formatted-text';

const props = defineProps<{ text: string }>();
const runs = computed(() => parseLineText(props.text));
const hasEmphasis = computed(() => runs.value.some((run) => run.bold || run.italic));
</script>

<template>
  <span class="whitespace-pre-wrap" :class="{ 'font-normal': hasEmphasis }"><template v-for="(run, index) in runs" :key="index"><strong v-if="run.bold"><em v-if="run.italic">{{ run.text }}</em><template v-else>{{ run.text }}</template></strong><em v-else-if="run.italic">{{ run.text }}</em><template v-else>{{ run.text }}</template></template></span>
</template>
