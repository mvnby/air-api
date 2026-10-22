<script setup lang="ts">
import { useManagerContextHeader } from '../../composables/useManagerContextHeader';
const props = withDefaults(defineProps<{ compact?: boolean }>(), { compact: false });
const context = useManagerContextHeader(() => props.compact);
</script>

<template>
  <Teleport :to="context?.target.value || 'body'" :disabled="!context?.target.value">
    <div class="manager-page-header" :class="{ 'is-inline': !context }"><slot /></div>
  </Teleport>
</template>

<style scoped>
.manager-page-header { position:relative; min-width:0; width:100%; }
.is-inline { margin-bottom:0.5rem; padding:0.5rem; border:1px solid var(--kitlane-border); border-radius:0.75rem; background:var(--kitlane-surface); }
.is-inline :deep(.orders-filter-panel) { position:static; max-height:none; width:100%; margin-top:0.5rem; }
</style>
