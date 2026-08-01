<script setup lang="ts">
import ManagerStorefrontSwitcher from './ManagerStorefrontSwitcher.vue';
import { managerStorefrontSelection } from '../../services/manager-storefront-selection';

defineProps<{ collapsed: boolean }>();

const {
  storefronts,
  selectedSlug,
  loading,
  switching,
  error,
} = managerStorefrontSelection;
</script>

<template>
  <div :class="collapsed ? 'md:hidden' : ''">
    <ManagerStorefrontSwitcher
      :storefronts="storefronts"
      :selected-slug="selectedSlug"
      :disabled="loading || switching"
      @select="managerStorefrontSelection.switchTo"
    />
    <p v-if="error" class="mt-1 px-1 text-[11px] leading-snug text-amber-700" role="status">
      {{ error }}
    </p>
  </div>
</template>
