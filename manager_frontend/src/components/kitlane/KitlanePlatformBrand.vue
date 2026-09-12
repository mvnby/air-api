<script setup lang="ts">
withDefaults(defineProps<{ attribution?: boolean }>(), { attribution: true });
const markUrl = `${import.meta.env.BASE_URL}kitlane-mark.svg`;
</script>

<template>
  <span class="kitlane-platform" :class="{ 'is-attributed': attribution }" :aria-label="attribution ? 'На платформе KitLane' : 'KitLane'">
    <span v-if="attribution" class="kitlane-platform-caption" aria-hidden="true">На платформе</span>
    <img :src="markUrl" width="28" height="28" alt="" aria-hidden="true" />
    <span class="kitlane-platform-wordmark" aria-hidden="true">KitLane</span>
  </span>
</template>

<style scoped>
.kitlane-platform { display: inline-flex; align-items: center; gap: 8px; flex-shrink: 0; color: var(--kitlane-text); white-space: nowrap; }
.kitlane-platform-caption { color: var(--kitlane-muted); font-size: 11px; }
.kitlane-platform-wordmark { font-size: 17px; font-weight: 750; letter-spacing: -.6px; }
@media (max-width: 1100px) { .kitlane-platform-caption { display: none; } }
@media (max-width: 639px) { .is-attributed .kitlane-platform-wordmark { display: none; } }
</style>
