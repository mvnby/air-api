<script setup lang="ts">
import { computed, ref, watch } from 'vue';
const props = withDefaults(defineProps<{ name?: string | null; src?: string | null; size?: 'sm' | 'md' | 'lg' }>(), { size: 'md' });
const failed = ref(false);
watch(() => props.src, () => { failed.value = false; });
const initials = computed(() => (props.name || 'Аккаунт').trim().split(/\s+/).slice(0, 2).map(word => word.charAt(0)).join('').toUpperCase() || 'А');
const imageUrl = computed(() => {
  if (!props.src || failed.value) return null;
  try {
    const url = new URL(props.src, window.location.origin);
    return url.origin === window.location.origin && /^[1-9]\d*$/.test(url.searchParams.get('tenant_id') || '') && /^\/api\/manager\/staff\/\d+\/avatar$/.test(url.pathname) ? url.pathname + url.search : null;
  } catch { return null; }
});
</script>
<template>
  <span class="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-brand-50 font-bold text-brand-700 dark:bg-brand-950 dark:text-brand-200" :class="size === 'lg' ? 'h-20 w-20 text-2xl' : size === 'sm' ? 'h-9 w-9 text-xs' : 'h-10 w-10 text-sm'">
    <img v-if="imageUrl" :src="imageUrl" :alt="name ? `Фото: ${name}` : 'Фото профиля'" class="h-full w-full object-cover" @error="failed = true" />
    <span v-else aria-hidden="true">{{ initials }}</span>
  </span>
</template>
