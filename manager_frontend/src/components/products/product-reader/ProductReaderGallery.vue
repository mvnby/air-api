<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ImageOff, Maximize2 } from 'lucide-vue-next';

const props = defineProps<{ images: { url: string; alt?: string | null }[]; title: string }>();
const emit = defineEmits<{ enlarge: [image: { url: string; alt?: string | null }] }>();
const selected = ref(0);
const failed = ref<string[]>([]);
const visibleImages = computed(() => props.images.filter(image => !failed.value.includes(image.url)));
const current = computed(() => visibleImages.value[selected.value] ?? visibleImages.value[0]);
watch(() => props.images, () => { selected.value = 0; failed.value = []; });
</script>

<template>
  <div class="min-w-0 space-y-3">
    <button v-if="current" type="button" class="group relative flex h-64 w-full items-center justify-center rounded-xl border border-[var(--mv-border)] bg-white p-4 sm:h-80" :aria-label="`Увеличить фото ${title}`" @click="emit('enlarge', current)">
      <img :src="current.url" :alt="current.alt || title" class="h-full w-full object-contain" @error="failed.push(current!.url)">
      <span class="absolute bottom-3 right-3 rounded-lg bg-slate-900/75 p-2 text-white"><Maximize2 aria-hidden="true" class="h-4 w-4" /></span>
    </button>
    <div v-else class="flex h-64 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[var(--mv-border)] bg-[var(--mv-bg)] text-sm text-[var(--mv-text-muted)] sm:h-80">
      <ImageOff aria-hidden="true" class="h-10 w-10" />Фотографии пока не добавлены
    </div>
    <div v-if="visibleImages.length > 1" class="flex gap-2 overflow-x-auto pb-1" aria-label="Фотографии товара">
      <button v-for="(image, index) in visibleImages" :key="image.url" type="button" class="h-16 w-20 shrink-0 overflow-hidden rounded-lg border-2 bg-white p-1" :class="current?.url === image.url ? 'border-brand-600' : 'border-transparent'" :aria-label="`Фото ${index + 1}`" :aria-pressed="current?.url === image.url" @click="selected = index">
        <img :src="image.url" :alt="image.alt || ''" loading="lazy" class="h-full w-full object-contain">
      </button>
    </div>
  </div>
</template>
