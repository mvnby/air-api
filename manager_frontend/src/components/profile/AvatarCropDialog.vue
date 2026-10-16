<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { X } from 'lucide-vue-next';
import ImageCropSelector, { type ImageCropValue } from '../ImageCropSelector.vue';
import { createLocalCroppedImageFile } from '../../utils/product-image-local-crop';
import { useDialogA11y } from '../../composables/useDialogA11y';
import { getApiErrorMessage } from '../../utils/api-errors';
const props = defineProps<{ file: File | null; busy?: boolean; errorMessage?: string }>();
const emit = defineEmits<{ close: []; save: [file: File] }>();
const src = ref('');
const width = ref(0);
const height = ref(0);
const crop = ref<ImageCropValue>({ x: 0, y: 0, width: 0, height: 0 });
const preparing = ref(false);
const error = ref('');
const busy = computed(() => props.busy || preparing.value);
const dialogRef = ref<HTMLElement | null>(null);
useDialogA11y({ open: computed(() => Boolean(props.file)), dialogRef, close: () => { if (!busy.value) emit('close'); } });
const release = () => { if (src.value) URL.revokeObjectURL(src.value); src.value = ''; };
watch(() => props.file, file => {
  release(); width.value = 0; height.value = 0; error.value = '';
  if (file) src.value = URL.createObjectURL(file);
}, { immediate: true });
const loaded = (size: { width: number; height: number }) => {
  width.value = size.width; height.value = size.height;
  const side = Math.min(size.width, size.height);
  crop.value = { x: Math.floor((size.width - side) / 2), y: Math.floor((size.height - side) / 2), width: side, height: side };
};
const save = async () => {
  if (!props.file || busy.value || !width.value) return;
  preparing.value = true; error.value = '';
  try { emit('save', await createLocalCroppedImageFile(props.file, crop.value)); }
  catch (cause) { error.value = getApiErrorMessage(cause); }
  finally { preparing.value = false; }
};
onBeforeUnmount(release);
</script>
<template>
  <Teleport to="body"><div v-if="file" role="dialog" aria-modal="true" aria-labelledby="avatar-crop-title" class="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4">
    <section ref="dialogRef" tabindex="-1" class="max-h-[92dvh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-5 text-gray-900 shadow-xl dark:bg-slate-900 dark:text-white">
      <header class="mb-4 flex items-center justify-between gap-3"><h2 id="avatar-crop-title" class="text-lg font-bold">Фото профиля</h2><button type="button" aria-label="Закрыть кадрирование" :disabled="busy" @click="emit('close')"><X class="h-5 w-5" /></button></header>
      <p class="mb-3 text-sm text-gray-600 dark:text-slate-300">Выделите нужную часть фотографии. На аватаре она будет показана по центру.</p>
      <ImageCropSelector v-if="src" v-model="crop" :src="src" :source-width="width" :source-height="height" :disabled="busy" image-alt="Предпросмотр фото профиля" @source-load="loaded" />
      <p v-if="error || errorMessage" role="alert" class="mt-3 text-sm text-red-700 dark:text-red-300">{{ error || errorMessage }}</p>
      <footer class="mt-4 flex justify-end gap-3"><button type="button" class="rounded-lg border px-3 py-2 text-sm" :disabled="busy" @click="emit('close')">Отмена</button><button type="button" class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="busy || !width" @click="save">{{ busy ? 'Сохраняем…' : 'Сохранить фото' }}</button></footer>
    </section>
  </div></Teleport>
</template>
