<script setup lang="ts">
import { computed, ref, watch } from 'vue';
const props = defineProps<{
  name?: string | null;
  logoUrl?: string | null;
  compactLogoUrl?: string | null;
  contextKey?: string;
  compact?: boolean;
  desktopCompact?: boolean;
}>();
const name = computed(() => props.name?.trim() || 'Рабочее пространство');
const initials = computed(() => name.value.split(/\s+/).slice(0, 2).map(part => Array.from(part)[0]).join('').toUpperCase());
const failedLogo = ref(false);
const failedCompactLogo = ref(false);
watch(() => [props.contextKey, props.name, props.logoUrl, props.compactLogoUrl], () => {
  failedLogo.value = false;
  failedCompactLogo.value = false;
}, { flush: 'sync' });
</script>

<template>
  <span class="kitlane-partner" :class="{ 'is-compact': compact, 'is-desktop-compact': desktopCompact }" :title="name" :aria-label="name" data-testid="kitlane-partner">
    <span class="kitlane-partner-compact" aria-hidden="true">
      <img v-if="compactLogoUrl && !failedCompactLogo" :key="`${contextKey}:${compactLogoUrl}`" :src="compactLogoUrl" :alt="name" @error="failedCompactLogo = true" />
      <span v-else class="kitlane-partner-initials">{{ initials }}</span>
    </span>
    <span class="kitlane-partner-full" aria-hidden="true">
      <img v-if="logoUrl && !failedLogo" :key="`${contextKey}:${logoUrl}`" :src="logoUrl" :alt="name" @error="failedLogo = true" />
      <span v-else class="kitlane-partner-initials">{{ initials }}</span>
      <span class="kitlane-partner-name">{{ name }}</span>
    </span>
  </span>
</template>

<style scoped>
.kitlane-partner { display: flex; min-width: 0; max-width: 100%; color: inherit; }
.kitlane-partner-full { display: flex; align-items: center; gap: 10px; min-width: 0; }
.kitlane-partner-full:has(img) { flex-direction: column; align-items: flex-start; gap: 2px; }
.kitlane-partner-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; font-size: 14px; font-weight: 650; }
.kitlane-partner-full:has(img) .kitlane-partner-name { font-size: 11px; }
.kitlane-partner-initials { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 36px; height: 36px; border-radius: 9px; background: #e2e8f0; color: #263a52; font-size: 13px; font-weight: 750; }
.kitlane-partner img { display: block; object-fit: contain; width: auto; max-width: min(176px, 100%); height: 32px; padding: 3px; border-radius: 4px; background: #fff; }
.kitlane-partner-compact { display: none; flex-shrink: 0; }
.kitlane-partner-compact img { width: 36px; height: 36px; }
.is-compact .kitlane-partner-full { display: none; }
.is-compact .kitlane-partner-compact { display: flex; }
@media (min-width: 768px) {
  .is-desktop-compact .kitlane-partner-full { display: none; }
  .is-desktop-compact .kitlane-partner-compact { display: flex; }
}
</style>
