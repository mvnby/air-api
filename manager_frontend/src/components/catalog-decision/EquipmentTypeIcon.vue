<script setup lang="ts">
defineProps<{
  type: 'wall' | 'cassette' | 'duct' | 'floor_ceiling' | 'console' | 'column';
}>();
</script>

<template>
  <svg viewBox="0 0 56 40" class="h-8 w-11 shrink-0" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" aria-hidden="true">
    <template v-if="type === 'wall'">
      <rect x="5" y="9" width="46" height="22" rx="4" />
      <path d="M9 25h38M13 29h30" />
    </template>
    <template v-else-if="type === 'cassette'">
      <path d="m28 4 21 14-21 18L7 18 28 4Z" />
      <path d="m28 11 13 8-13 10-13-10 13-8ZM22 20h12M28 16v8" />
    </template>
    <template v-else-if="type === 'duct'">
      <path d="M6 13 43 7l7 7v17L13 37 6 29V13Z" />
      <path d="M12 17h25v12H12zM41 13v17M16 21h17M16 25h17" />
    </template>
    <template v-else-if="type === 'floor_ceiling'">
      <path d="M5 14 45 7l6 6v16L11 35 5 29V14Z" />
      <path d="m10 18 32-5v11l-32 5V18ZM14 22h23" />
    </template>
    <template v-else-if="type === 'console'">
      <rect x="12" y="4" width="32" height="32" rx="4" />
      <path d="M16 11h24M17 24h22M17 28h22M17 32h22" />
    </template>
    <template v-else>
      <rect x="18" y="3" width="20" height="34" rx="3" />
      <path d="M22 10h12M22 14h12M22 18h12M22 27h12M22 31h12" />
    </template>
  </svg>
</template>
