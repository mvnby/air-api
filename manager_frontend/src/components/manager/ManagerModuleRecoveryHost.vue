<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import ManagerModuleRecovery from './ManagerModuleRecovery.vue';
import { recordModuleFailure } from '../../services/manager-module-recovery';

const failed = ref(false);
const onPreloadFailure = () => {
  // Never inspect the payload: it may contain URLs or private query parameters.
  // Leave the rejection intact so the importing panel can handle it too.
  recordModuleFailure('unknown', 'panel', 'preload-failed');
  failed.value = true;
};
onMounted(() => window.addEventListener('vite:preloadError', onPreloadFailure));
onBeforeUnmount(() => window.removeEventListener('vite:preloadError', onPreloadFailure));
</script>

<template>
  <!-- Advisory only: keep editors mounted and their unsaved navigation guards registered. -->
  <ManagerModuleRecovery v-if="failed" category="panel" />
</template>
