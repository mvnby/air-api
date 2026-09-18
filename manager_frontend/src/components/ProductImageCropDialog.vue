<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { RotateCcw, RotateCw, X } from 'lucide-vue-next';
import { ManagerService } from '../client';
import ImageCropSelector from './ImageCropSelector.vue';
import { getApiErrorMessage } from '../utils/api-errors';
import {
  clampLocalCropRect,
  createLocalCroppedImageFile,
  getLocalCropCapabilityError,
  loadLocalCropSource,
  localCropWorkflowAvailability,
  renderLocalCropRotation,
  saveLocalCroppedProductImage,
  type LocalCroppedProductImage,
  type ProductImageCropRect,
  type ProductImageCropSize,
} from '../utils/product-image-local-crop';

export type ProductImageCropDialogImage = {
  id: number;
  url: string;
  is_installation_photo?: boolean;
};

const props = defineProps<{
  open: boolean;
  productId: number;
  image: ProductImageCropDialogImage | null;
}>();

const emit = defineEmits<{
  close: [];
  saved: [image: LocalCroppedProductImage];
}>();

const sourceBitmap = ref<ImageBitmap | null>(null);
const sourceBlob = ref<Blob | null>(null);
const previewBlob = ref<Blob | null>(null);
const previewUrl = ref('');
const sourceSize = ref<ProductImageCropSize>({ width: 0, height: 0 });
const crop = ref<ProductImageCropRect>({ x: 0, y: 0, width: 0, height: 0 });
const quarterTurns = ref(0);
const mode = ref<'append' | 'replace'>('append');
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const warning = ref<string | null>(null);
let loadVersion = 0;

const ready = computed(() => Boolean(sourceBitmap.value && previewBlob.value && sourceSize.value.width && sourceSize.value.height));
const canSave = computed(() => ready.value && !loading.value && !saving.value && !error.value);

const revokePreviewUrl = () => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
  previewUrl.value = '';
};

const resetEditor = () => {
  loadVersion += 1;
  revokePreviewUrl();
  sourceBitmap.value?.close();
  sourceBitmap.value = null;
  sourceBlob.value = null;
  previewBlob.value = null;
  sourceSize.value = { width: 0, height: 0 };
  crop.value = { x: 0, y: 0, width: 0, height: 0 };
  quarterTurns.value = 0;
  loading.value = false;
  saving.value = false;
  error.value = '';
  warning.value = null;
};

const showPreview = (blob: Blob, size: ProductImageCropSize) => {
  revokePreviewUrl();
  previewBlob.value = blob;
  previewUrl.value = URL.createObjectURL(blob);
  sourceSize.value = size;
  crop.value = { x: 0, y: 0, width: size.width, height: size.height };
};

const refreshRotation = async () => {
  if (!sourceBitmap.value) return;
  if (!quarterTurns.value) {
    if (sourceBlob.value) {
      showPreview(sourceBlob.value, { width: sourceBitmap.value.width, height: sourceBitmap.value.height });
    }
    return;
  }
  const rendered = await renderLocalCropRotation(sourceBitmap.value, quarterTurns.value);
  showPreview(rendered.blob, rendered.size);
};

const loadSource = async () => {
  resetEditor();
  if (!props.open || !props.image) return;
  const capabilityError = getLocalCropCapabilityError();
  if (capabilityError) {
    error.value = capabilityError;
    return;
  }
  const version = ++loadVersion;
  loading.value = true;
  try {
    const loaded = await loadLocalCropSource(props.image.url);
    if (version !== loadVersion) {
      loaded.bitmap.close();
      return;
    }
    sourceBitmap.value = loaded.bitmap;
    sourceBlob.value = loaded.blob;
    warning.value = loaded.warning;
    showPreview(loaded.blob, { width: loaded.bitmap.width, height: loaded.bitmap.height });
  } catch (caught) {
    if (version === loadVersion) error.value = getApiErrorMessage(caught);
  } finally {
    if (version === loadVersion) loading.value = false;
  }
};

const rotate = async (direction: -1 | 1) => {
  if (!sourceBitmap.value || loading.value || saving.value) return;
  error.value = '';
  loading.value = true;
  quarterTurns.value += direction;
  try {
    await refreshRotation();
  } catch (caught) {
    error.value = getApiErrorMessage(caught);
  } finally {
    loading.value = false;
  }
};

const resetCrop = () => {
  crop.value = { x: 0, y: 0, width: sourceSize.value.width, height: sourceSize.value.height };
};

const centerSquareCrop = () => {
  const side = Math.min(sourceSize.value.width, sourceSize.value.height);
  crop.value = {
    x: Math.floor((sourceSize.value.width - side) / 2),
    y: Math.floor((sourceSize.value.height - side) / 2),
    width: side,
    height: side,
  };
};

const close = () => {
  if (!saving.value) emit('close');
};

const save = async () => {
  if (!props.image || !canSave.value || !previewBlob.value) return;
  saving.value = true;
  error.value = '';
  try {
    const file = await createLocalCroppedImageFile(
      previewBlob.value,
      clampLocalCropRect(crop.value, sourceSize.value),
    );
    const saved = await saveLocalCroppedProductImage({
      productId: props.productId,
      imageId: props.image.id,
      file,
      mode: mode.value,
      isInstallation: Boolean(props.image.is_installation_photo),
      upload: async (productId, files, isInstallation) => (
        await ManagerService.uploadLocalImages(productId, { files }, isInstallation)
      ),
    });
    emit('saved', saved);
  } catch (caught) {
    error.value = `Не удалось сохранить: ${getApiErrorMessage(caught)}`;
  } finally {
    saving.value = false;
  }
};

watch(() => [props.open, props.image?.id, props.image?.url] as const, loadSource, { immediate: true });
onBeforeUnmount(resetEditor);
</script>

<template>
  <div
    v-if="open && image"
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-3 sm:p-6"
    @click.self="close"
  >
    <section class="flex max-h-full w-full max-w-5xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="product-local-crop-title">
      <header class="flex items-start justify-between gap-4 border-b border-gray-200 px-4 py-3 sm:px-5">
        <div class="min-w-0">
          <h2 id="product-local-crop-title" class="truncate text-lg font-semibold text-gray-950">Обрезать фото</h2>
          <p class="mt-0.5 text-sm text-gray-500">Обработка идёт в браузере, исходник сохраняется по умолчанию.</p>
        </div>
        <button type="button" class="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 disabled:opacity-50" aria-label="Закрыть" :disabled="saving" @click="close">
          <X class="h-5 w-5" />
        </button>
      </header>

      <div class="grid min-h-0 flex-1 gap-4 overflow-y-auto p-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div class="flex min-h-[280px] items-center justify-center rounded-lg bg-gray-100 p-3">
          <div v-if="loading" class="text-sm text-gray-600">Подготавливаем фото в браузере…</div>
          <ImageCropSelector
            v-else-if="ready && previewUrl"
            v-model="crop"
            :src="previewUrl"
            :source-width="sourceSize.width"
            :source-height="sourceSize.height"
            :disabled="saving"
            image-alt="Фото товара для обрезки"
          />
          <p v-else class="max-w-sm text-center text-sm text-gray-600">{{ error || 'Фото недоступно для обработки.' }}</p>
        </div>

        <div class="space-y-4">
          <div v-if="ready" class="text-sm text-gray-600">{{ sourceSize.width }}×{{ sourceSize.height }} px</div>
          <p v-if="warning" class="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">{{ warning }}</p>
          <p v-if="error && ready" role="alert" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>

          <div class="flex gap-2">
            <button type="button" class="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50" :disabled="!ready || loading || saving" @click="rotate(-1)">
              <RotateCcw class="h-4 w-4" /> Повернуть
            </button>
            <button type="button" class="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50" :disabled="!ready || loading || saving" @click="rotate(1)">
              <RotateCw class="h-4 w-4" /> Повернуть
            </button>
          </div>

          <div class="flex flex-wrap gap-2">
            <button type="button" class="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50" :disabled="!ready || saving" @click="resetCrop">Весь кадр</button>
            <button type="button" class="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50" :disabled="!ready || saving" @click="centerSquareCrop">Квадрат</button>
          </div>

          <div class="grid grid-cols-2 overflow-hidden rounded-lg border border-gray-300 p-1">
            <button type="button" class="rounded-md px-3 py-2 text-sm font-medium" :class="mode === 'append' ? 'bg-brand-600 text-white' : 'text-gray-700 hover:bg-gray-100'" :disabled="saving" @click="mode = 'append'">Добавить</button>
            <button type="button" class="rounded-md px-3 py-2 text-sm font-medium" :class="mode === 'replace' ? 'bg-brand-600 text-white' : 'text-gray-700 hover:bg-gray-100'" :disabled="saving" @click="mode = 'replace'">Заменить</button>
          </div>
          <p class="text-xs text-gray-500">{{ mode === 'append' ? 'Оригинал останется в галерее.' : 'Будет заменён только этот элемент галереи; его ID и тип фото сохранятся.' }}</p>
          <p class="text-xs text-gray-500">{{ localCropWorkflowAvailability.backgroundRemovalReason }}</p>
        </div>
      </div>

      <footer class="flex justify-end gap-3 border-t border-gray-200 px-4 py-3 sm:px-5">
        <button type="button" class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50" :disabled="saving" @click="close">Отмена</button>
        <button type="button" class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50" :disabled="!canSave" @click="save">{{ saving ? 'Сохраняем…' : 'Сохранить' }}</button>
      </footer>
    </section>
  </div>
</template>
