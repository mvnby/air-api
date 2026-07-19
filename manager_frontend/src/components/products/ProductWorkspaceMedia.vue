<script setup lang="ts">
import { computed } from 'vue';
import { Images, ImagePlus, Star, ExternalLink } from 'lucide-vue-next';
import type { Product } from '../../api';

const props = defineProps<{
  product: Product;
}>();

const emit = defineEmits<{
  (event: 'open-editor'): void;
}>();

const getImageUrl = (path: string | null | undefined): string => {
  if (!path) return '';
  if (path.startsWith('http') || path.startsWith('/')) return path;
  return `/${path}`;
};

const galleryImages = computed(() => (
  props.product.gallery_images.filter((image) => image.url !== props.product.main_image)
));

const imageCount = computed(() => galleryImages.value.length + (props.product.main_image ? 1 : 0));
</script>

<template>
  <section class="min-h-[520px] bg-white px-4 py-5 dark:bg-slate-900 sm:px-6">
    <div class="flex flex-col gap-4 border-b border-gray-100 pb-5 dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p class="text-xs font-bold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">Медиа товара</p>
        <h2 class="mt-1 text-xl font-bold text-gray-950 dark:text-white">Галерея и главное изображение</h2>
        <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
          {{ imageCount }} изображений. Редактирование использует общий быстрый медиарежим каталога.
        </p>
      </div>
      <button
        type="button"
        class="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-700"
        @click="emit('open-editor')"
      >
        <ImagePlus class="h-4 w-4" />
        Открыть редактор
      </button>
    </div>

    <div v-if="product.main_image" class="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(240px,0.5fr)]">
      <button
        type="button"
        class="group relative min-h-[280px] overflow-hidden rounded-lg border border-gray-200 bg-gray-100 text-left dark:border-slate-700 dark:bg-slate-800"
        @click="emit('open-editor')"
      >
        <img :src="getImageUrl(product.main_image)" :alt="product.title" class="h-full max-h-[520px] w-full object-contain p-4" />
        <span class="absolute left-3 top-3 inline-flex items-center gap-1 rounded-md bg-white/95 px-2 py-1 text-xs font-bold text-gray-800 shadow-sm dark:bg-slate-900/95 dark:text-slate-100">
          <Star class="h-3.5 w-3.5 fill-amber-400 text-amber-500" /> Главное
        </span>
        <span class="absolute bottom-3 right-3 inline-flex items-center gap-1 rounded-md bg-gray-950/75 px-2 py-1 text-xs font-semibold text-white opacity-0 transition group-hover:opacity-100">
          <ExternalLink class="h-3.5 w-3.5" /> Редактировать
        </span>
      </button>

      <div class="grid grid-cols-2 gap-3 content-start">
        <button
          v-for="image in galleryImages"
          :key="image.id"
          type="button"
          class="aspect-square overflow-hidden rounded-lg border border-gray-200 bg-gray-100 transition hover:border-teal-400 dark:border-slate-700 dark:bg-slate-800"
          @click="emit('open-editor')"
        >
          <img :src="getImageUrl(image.url)" :alt="product.title" class="h-full w-full object-contain p-2" />
        </button>
      </div>
    </div>

    <button
      v-else
      type="button"
      class="mt-6 flex min-h-[360px] w-full flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 bg-gray-50 px-6 text-center transition hover:border-teal-400 hover:bg-teal-50/40 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-teal-700"
      @click="emit('open-editor')"
    >
      <span class="flex h-14 w-14 items-center justify-center rounded-full bg-white text-gray-400 shadow-sm dark:bg-slate-800 dark:text-slate-500">
        <Images class="h-7 w-7" />
      </span>
      <span class="mt-4 text-base font-bold text-gray-900 dark:text-white">Изображения ещё не добавлены</span>
      <span class="mt-1 max-w-md text-sm text-gray-500 dark:text-slate-400">Загрузите файл, вставьте ссылку или выберите изображение из медиатеки.</span>
      <span class="mt-4 inline-flex h-10 items-center gap-2 rounded-lg bg-teal-600 px-4 text-sm font-semibold text-white">
        <ImagePlus class="h-4 w-4" /> Добавить изображения
      </span>
    </button>
  </section>
</template>
