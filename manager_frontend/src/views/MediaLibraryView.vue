<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import {
  ClipboardPaste,
  Copy,
  Clock3,
  Image as ImageIcon,
  Link,
  RefreshCw,
  Save,
  Scissors,
  Search,
  Trash2,
  UploadCloud,
  Wand2,
  X,
} from 'lucide-vue-next';
import { api, type ManagerMediaAssetResponse, type ManagerMediaProcessingJobResponse } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';
import {
  backgroundRemovalProviderOptions,
  type BackgroundRemovalProvider,
} from '../utils/media-processing';
import ImageCropSelector, { type ImageCropSourceSize, type ImageCropValue } from '../components/ImageCropSelector.vue';

type MediaKind = { value: string; label: string };
type BackgroundRemovalModelOption = {
  value: string;
  label: string;
  description?: string;
  recommended?: boolean;
};

const kindOptions: MediaKind[] = [
  { value: 'misc', label: 'Разное' },
  { value: 'product', label: 'Товары' },
  { value: 'article', label: 'Статьи' },
  { value: 'service', label: 'Услуги' },
  { value: 'installation', label: 'Монтажи' },
  { value: 'strobe', label: 'Штробы' },
  { value: 'brand', label: 'Бренды' },
];

const assets = ref<ManagerMediaAssetResponse[]>([]);
const loading = ref(false);
const uploading = ref(false);
const saving = ref(false);
const deleting = ref(false);
const processing = ref<'crop' | 'background' | ''>('');
const queueing = ref(false);
const backgroundProvider = ref<BackgroundRemovalProvider>('rembg');
const backgroundModel = ref('u2net');
const backgroundModelsLoading = ref(false);
const backgroundModelOptions = ref<BackgroundRemovalModelOption[]>([
  { value: 'u2net', label: 'U2Net', recommended: true },
]);
const page = ref(1);
const limit = ref(40);
const total = ref(0);
const pages = ref(1);
const query = ref('');
const kind = ref('');
const tag = ref('');
const status = ref('');
const uploadKind = ref('misc');
const uploadTags = ref('');
const uploadUrl = ref('');
const uploadInput = ref<HTMLInputElement | null>(null);
const selectedAsset = ref<ManagerMediaAssetResponse | null>(null);
const processingJobs = ref<ManagerMediaProcessingJobResponse[]>([]);
const processingJobsLoading = ref(false);
let processingJobsTimer: ReturnType<typeof window.setInterval> | null = null;
const toast = ref('');
const toastType = ref<'success' | 'error'>('success');
const dragActive = ref(false);
const cropMode = ref(false);
const cropBox = ref<ImageCropValue>({ x: 0, y: 0, width: 0, height: 0 });
const cropSourceSize = ref<ImageCropSourceSize>({ width: 0, height: 0 });
const editForm = ref({
  title: '',
  alt_text: '',
  description: '',
  kind: 'misc',
  tagsText: '',
});

const tagList = computed(() => {
  const values = new Set<string>();
  for (const asset of assets.value) {
    for (const item of asset.tags || []) {
      if (item) values.add(item);
    }
  }
  return Array.from(values).sort((a, b) => a.localeCompare(b, 'ru'));
});

const selectedUrl = computed(() => selectedAsset.value ? imageUrl(selectedAsset.value.url) : '');
const showRembgModelSelect = computed(() => (
  backgroundProvider.value === 'rembg' || backgroundProvider.value === 'auto'
));
const selectedBackgroundModelOption = computed(() => (
  backgroundModelOptions.value.find((option) => option.value === backgroundModel.value)
));
const showBackgroundExperimentWarning = computed(() => (
  backgroundProvider.value === 'birefnet'
  || backgroundProvider.value === 'ben'
  || (showRembgModelSelect.value && selectedBackgroundModelOption.value?.recommended === false)
));
const activeSelectedProcessingJob = computed(() => {
  if (!selectedAsset.value) return null;
  return processingJobs.value.find((job) => (
    job.source_asset_id === selectedAsset.value?.id
    && (job.status === 'queued' || job.status === 'running')
  )) || null;
});
const visibleProcessingJobs = computed(() => processingJobs.value.slice(0, 5));

const setToast = (message: string, type: 'success' | 'error' = 'success') => {
  toast.value = message;
  toastType.value = type;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 3200);
};

const mediaErrorMessage = (err: unknown, fallback: string) => {
  const message = getApiErrorMessage(err);
  if (!message) return fallback;
  if (/permission|notallowed|denied/i.test(message)) {
    return 'Браузер не дал прямой доступ к буферу. Нажмите Ctrl+V или Cmd+V на странице.';
  }
  if (/fetch/i.test(message)) {
    return 'API медиатеки недоступен. Проверьте, что backend запущен, и повторите поиск.';
  }
  if (/rembg provider is not installed/i.test(message)) {
    return 'Удаление фона пока не настроено: установите rembg в backend-окружении.';
  }
  if (/provider is not configured|provider is not installed/i.test(message)) {
    return 'Провайдер удаления фона пока не настроен на backend. Проверьте env-команду или зависимости модели.';
  }
  return message;
};

const imageUrl = (path?: string | null) => {
  if (!path) return '';
  if (path.startsWith('http')) return path;
  return path.startsWith('/') ? path : `/${path}`;
};

const bytesLabel = (value?: number | null) => {
  const size = Number(value || 0);
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} МБ`;
  if (size >= 1024) return `${Math.round(size / 1024)} КБ`;
  return `${size} Б`;
};

const kindLabel = (value?: string | null) => (
  kindOptions.find((item) => item.value === value)?.label || 'Разное'
);

const variantLabel = (value?: string | null) => {
  if (value === 'background_removed') return 'без фона';
  if (value === 'crop') return 'crop';
  return 'original';
};

const processingJobStatusLabel = (status?: string | null) => {
  if (status === 'queued') return 'в очереди';
  if (status === 'running') return 'в работе';
  if (status === 'success') return 'готово';
  if (status === 'failed') return 'ошибка';
  if (status === 'canceled') return 'отменено';
  return status || 'неизвестно';
};

const processingJobStatusClass = (status?: string | null) => {
  if (status === 'queued') return 'bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-200';
  if (status === 'running') return 'bg-teal-50 text-teal-700 dark:bg-teal-950 dark:text-teal-200';
  if (status === 'success') return 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200';
  if (status === 'failed') return 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200';
  return 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300';
};

const parseTags = (value: string) => value
  .split(',')
  .map((item) => item.trim())
  .filter(Boolean);

const fallbackAltText = (title?: string | null, sourceFilename?: string | null) => (
  (title || sourceFilename || '').trim()
);

const appendUploadedAssets = (items: ManagerMediaAssetResponse[], count: number) => {
  assets.value = [...items, ...assets.value];
  total.value += count;
  if (items[0]) selectAsset(items[0]);
};

const loadAssets = async () => {
  loading.value = true;
  try {
    const response = await api.listMediaAssets({
      page: page.value,
      limit: limit.value,
      q: query.value.trim() || null,
      kind: kind.value || null,
      tag: tag.value || null,
      status: status.value || null,
    });
    assets.value = response.items || [];
    total.value = response.meta.total;
    pages.value = response.meta.pages;
    if (selectedAsset.value) {
      const refreshed = assets.value.find((item) => item.id === selectedAsset.value?.id);
      if (refreshed) selectedAsset.value = refreshed;
    }
  } catch (err) {
    setToast(mediaErrorMessage(err, 'Не удалось загрузить медиатеку'), 'error');
  } finally {
    loading.value = false;
  }
};

const loadBackgroundRemovalConfig = async () => {
  backgroundModelsLoading.value = true;
  try {
    const config = await api.getMediaBackgroundRemovalConfig();
    if (config.default_provider) {
      backgroundProvider.value = config.default_provider as BackgroundRemovalProvider;
    }
    if (config.rembg_models?.length) {
      backgroundModelOptions.value = config.rembg_models;
    }
    if (config.default_rembg_model) {
      backgroundModel.value = config.default_rembg_model;
    }
  } catch (err) {
    console.warn('Failed to load background removal config', err);
  } finally {
    backgroundModelsLoading.value = false;
  }
};

const loadProcessingJobs = async () => {
  const activeBefore = new Set(
    processingJobs.value
      .filter((job) => job.status === 'queued' || job.status === 'running')
      .map((job) => job.job_id),
  );
  processingJobsLoading.value = true;
  try {
    const response = await api.listMediaProcessingJobs({ limit: 12 });
    processingJobs.value = response.items || [];
    const finished = processingJobs.value.some((job) => (
      activeBefore.has(job.job_id) && (job.status === 'success' || job.status === 'failed')
    ));
    if (finished) {
      void loadAssets();
    }
  } catch (err) {
    console.warn('Failed to load media processing jobs', err);
  } finally {
    processingJobsLoading.value = false;
  }
};

const uploadFiles = async (files: FileList | File[]) => {
  const imageFiles = Array.from(files).filter((file) => file.type.startsWith('image/'));
  if (!imageFiles.length) {
    setToast('Выберите изображения', 'error');
    return;
  }
  uploading.value = true;
  try {
    const response = await api.uploadMediaAssets({
      files: imageFiles,
      kind: uploadKind.value,
      tags_json: JSON.stringify(parseTags(uploadTags.value)),
    });
    appendUploadedAssets(response.items, response.uploaded);
    setToast(`Загружено: ${response.uploaded}`);
  } catch (err) {
    setToast(mediaErrorMessage(err, 'Не удалось загрузить файлы'), 'error');
  } finally {
    uploading.value = false;
    dragActive.value = false;
    if (uploadInput.value) uploadInput.value.value = '';
  }
};

const uploadFromUrl = async () => {
  const url = uploadUrl.value.trim();
  if (!url) {
    setToast('Укажите URL изображения', 'error');
    return;
  }
  uploading.value = true;
  try {
    const response = await api.uploadMediaAssetFromUrl({
      url,
      kind: uploadKind.value,
      tags: parseTags(uploadTags.value),
    });
    appendUploadedAssets(response.items, response.uploaded);
    uploadUrl.value = '';
    setToast('Изображение загружено по URL');
  } catch (err) {
    setToast(mediaErrorMessage(err, 'Не удалось загрузить изображение по URL'), 'error');
  } finally {
    uploading.value = false;
  }
};

type ClipboardImageItem = {
  types: readonly string[];
  getType: (type: string) => Promise<Blob>;
};

const extensionFromMime = (mimeType: string) => mimeType.split('/')[1]?.replace('jpeg', 'jpg') || 'png';

const uploadClipboardFiles = async (files: File[]) => {
  if (!files.length) {
    setToast('В буфере нет изображения', 'error');
    return;
  }
  await uploadFiles(files);
};

const pasteFromClipboard = async () => {
  const clipboard = navigator.clipboard as Clipboard & { read?: () => Promise<ClipboardImageItem[]> };
  if (!clipboard?.read) {
    setToast('Вставьте изображение через Ctrl+V или Cmd+V', 'error');
    return;
  }
  try {
    const items = await clipboard.read();
    const files: File[] = [];
    for (const item of items) {
      const imageType = item.types.find((type) => type.startsWith('image/'));
      if (!imageType) continue;
      const blob = await item.getType(imageType);
      files.push(new File([blob], `clipboard-${Date.now()}.${extensionFromMime(imageType)}`, { type: imageType }));
    }
    await uploadClipboardFiles(files);
  } catch (err) {
    setToast(mediaErrorMessage(err, 'Не удалось прочитать изображение из буфера'), 'error');
  }
};

const selectAsset = (asset: ManagerMediaAssetResponse) => {
  const title = asset.title || '';
  selectedAsset.value = asset;
  editForm.value = {
    title,
    alt_text: asset.alt_text || fallbackAltText(title, asset.source_filename),
    description: asset.description || '',
    kind: asset.kind || 'misc',
    tagsText: (asset.tags || []).join(', '),
  };
  cropMode.value = false;
  cropBox.value = { x: 0, y: 0, width: 0, height: 0 };
  cropSourceSize.value = {
    width: Number(asset.width || 0),
    height: Number(asset.height || 0),
  };
};

const saveSelected = async () => {
  if (!selectedAsset.value) return;
  saving.value = true;
  try {
    const updated = await api.updateMediaAsset(selectedAsset.value.id, {
      title: editForm.value.title,
      alt_text: editForm.value.alt_text || fallbackAltText(editForm.value.title, selectedAsset.value.source_filename),
      description: editForm.value.description,
      kind: editForm.value.kind,
      tags: parseTags(editForm.value.tagsText),
    });
    selectedAsset.value = updated;
    assets.value = assets.value.map((item) => item.id === updated.id ? updated : item);
    setToast('Метаданные сохранены');
  } catch (err) {
    setToast(mediaErrorMessage(err, 'Не удалось сохранить'), 'error');
  } finally {
    saving.value = false;
  }
};

const copyUrl = async (asset = selectedAsset.value) => {
  if (!asset) return;
  try {
    await navigator.clipboard.writeText(asset.url);
    setToast('URL скопирован');
  } catch {
    setToast(asset.url);
  }
};

const deleteSelected = async () => {
  if (!selectedAsset.value) return;
  const used = Number(selectedAsset.value.usage_count || 0) > 0;
  if (!confirm(used ? 'Файл используется. Удалить metadata принудительно?' : 'Удалить файл из медиатеки?')) return;
  const assetId = selectedAsset.value.id;
  deleting.value = true;
  try {
    await api.deleteMediaAsset(assetId, used);
    assets.value = assets.value.filter((item) => item.id !== assetId);
    selectedAsset.value = null;
    total.value = Math.max(0, total.value - 1);
    setToast('Файл удален');
  } catch (err) {
    setToast(mediaErrorMessage(err, 'Не удалось удалить'), 'error');
  } finally {
    deleting.value = false;
  }
};

const resetCropBoxToFullFrame = () => {
  if (!cropSourceSize.value.width || !cropSourceSize.value.height) return;
  cropBox.value = {
    x: 0,
    y: 0,
    width: cropSourceSize.value.width,
    height: cropSourceSize.value.height,
  };
};

const toggleCropMode = () => {
  cropMode.value = !cropMode.value;
  if (cropMode.value) resetCropBoxToFullFrame();
};

const handleCropSourceLoad = (size: ImageCropSourceSize) => {
  cropSourceSize.value = size;
  if (cropMode.value && (!cropBox.value.width || !cropBox.value.height)) {
    resetCropBoxToFullFrame();
  }
};

const applyCrop = async () => {
  if (!selectedAsset.value) return;
  if (cropBox.value.width < 8 || cropBox.value.height < 8) {
    setToast('Выделите область крупнее', 'error');
    return;
  }
  processing.value = 'crop';
  try {
    const cropped = await api.cropMediaAsset(selectedAsset.value.id, {
      x: Math.round(cropBox.value.x),
      y: Math.round(cropBox.value.y),
      width: Math.round(cropBox.value.width),
      height: Math.round(cropBox.value.height),
      title: `${selectedAsset.value.title || 'Image'} crop`,
    });
    assets.value = [cropped, ...assets.value];
    selectAsset(cropped);
    setToast('Crop сохранен как новая версия');
  } catch (err) {
    setToast(mediaErrorMessage(err, 'Не удалось обрезать изображение'), 'error');
  } finally {
    processing.value = '';
  }
};

const removeBackground = async () => {
  if (!selectedAsset.value) return;
  processing.value = 'background';
  try {
    const processed = await api.removeMediaAssetBackground(
      selectedAsset.value.id,
      backgroundProvider.value,
      showRembgModelSelect.value ? backgroundModel.value : null,
    );
    assets.value = [processed, ...assets.value];
    selectAsset(processed);
    setToast('Версия без фона готова');
  } catch (err) {
    setToast(mediaErrorMessage(err, 'Не удалось удалить фон'), 'error');
  } finally {
    processing.value = '';
  }
};

const enqueueBackgroundRemoval = async () => {
  if (!selectedAsset.value) return;
  queueing.value = true;
  try {
    const job = await api.createMediaProcessingJob(selectedAsset.value.id, {
      operation: 'background_removal',
      provider: backgroundProvider.value,
      rembg_model: showRembgModelSelect.value ? backgroundModel.value : null,
      options: {},
      priority: showBackgroundExperimentWarning.value ? 120 : 100,
    });
    processingJobs.value = [job, ...processingJobs.value.filter((item) => item.job_id !== job.job_id)].slice(0, 12);
    setToast('Задача поставлена в очередь локальному worker-у');
  } catch (err) {
    setToast(mediaErrorMessage(err, 'Не удалось поставить задачу в очередь'), 'error');
  } finally {
    queueing.value = false;
  }
};

const onDrop = (event: DragEvent) => {
  event.preventDefault();
  if (event.dataTransfer?.files?.length) {
    void uploadFiles(event.dataTransfer.files);
  }
};

const onPaste = (event: ClipboardEvent) => {
  const files: File[] = [];
  for (const item of Array.from(event.clipboardData?.items || [])) {
    if (item.kind !== 'file' || !item.type.startsWith('image/')) continue;
    const file = item.getAsFile();
    if (file) files.push(file);
  }
  if (files.length) {
    event.preventDefault();
    void uploadClipboardFiles(files);
    return;
  }

  const text = event.clipboardData?.getData('text/plain')?.trim() || '';
  if (/^https?:\/\//i.test(text)) {
    uploadUrl.value = text;
  }
};

const applyFilters = () => {
  if (page.value !== 1) {
    page.value = 1;
    return;
  }
  void loadAssets();
};

watch(page, () => void loadAssets());

onMounted(() => {
  document.addEventListener('paste', onPaste);
  void loadBackgroundRemovalConfig();
  void loadProcessingJobs();
  void loadAssets();
  processingJobsTimer = window.setInterval(() => {
    if (processingJobs.value.some((job) => job.status === 'queued' || job.status === 'running')) {
      void loadProcessingJobs();
    }
  }, 8000);
});

onUnmounted(() => {
  document.removeEventListener('paste', onPaste);
  if (processingJobsTimer) window.clearInterval(processingJobsTimer);
});
</script>

<template>
  <div class="space-y-6 px-4 pb-6 lg:px-0">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div class="min-h-12 pl-16 lg:min-h-0 lg:pl-0">
        <h1 class="text-2xl font-semibold text-gray-900 dark:text-white">Медиатека</h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {{ total }} файлов · изображения для товаров, статей и сервисных материалов
        </p>
      </div>
      <input
        ref="uploadInput"
        type="file"
        accept="image/*"
        multiple
        class="hidden"
        @change="event => uploadFiles((event.target as HTMLInputElement).files || [])"
      />
    </div>

    <div
      class="rounded-xl border border-dashed p-3 transition dark:border-gray-700 lg:p-4"
      :class="dragActive ? 'border-teal-500 bg-teal-50 dark:bg-teal-950/30' : 'border-gray-300 bg-white dark:bg-gray-900'"
      @dragenter.prevent="dragActive = true"
      @dragover.prevent="dragActive = true"
      @dragleave.prevent="dragActive = false"
      @drop="onDrop"
    >
      <div class="grid gap-2 lg:grid-cols-[1fr_180px_1fr_auto] lg:items-end lg:gap-3">
        <label class="block">
          <span class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Теги загрузки</span>
          <input
            v-model="uploadTags"
            type="text"
            placeholder="монтаж, штробы, обслуживание"
            class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-gray-700 dark:bg-gray-950 dark:text-white"
          />
        </label>
        <label class="block">
          <span class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Тип</span>
          <select
            v-model="uploadKind"
            class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-gray-700 dark:bg-gray-950 dark:text-white"
          >
            <option v-for="item in kindOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <div class="hidden min-h-[42px] items-center rounded-lg bg-gray-50 px-3 text-sm text-gray-500 dark:bg-gray-950 dark:text-gray-400 lg:flex">
          Перетащите изображения сюда
        </div>
        <button
          type="button"
          class="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-60 lg:min-w-[120px]"
          :disabled="uploading"
          @click="uploadInput?.click()"
        >
          <UploadCloud class="h-4 w-4" />
          {{ uploading ? 'Загрузка...' : 'Выбрать' }}
        </button>
      </div>
      <div class="mt-2 lg:mt-3">
        <div class="relative">
          <Link class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            v-model="uploadUrl"
            type="url"
            placeholder="https://site.by/image.jpg"
            class="w-full rounded-lg border border-gray-300 bg-white py-2 pl-9 pr-24 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-gray-700 dark:bg-gray-950 dark:text-white"
            @keydown.enter.prevent="uploadFromUrl"
          />
          <div class="absolute right-1 top-1/2 flex -translate-y-1/2 gap-1">
            <button
              type="button"
              class="inline-flex h-8 w-8 items-center justify-center rounded-md text-teal-700 transition hover:bg-teal-50 disabled:cursor-not-allowed disabled:opacity-50 dark:text-teal-200 dark:hover:bg-teal-950/40"
              :disabled="uploading"
              title="Скачать по URL"
              aria-label="Скачать по URL"
              @click="uploadFromUrl"
            >
              <UploadCloud class="h-4 w-4" />
            </button>
            <button
              type="button"
              class="inline-flex h-8 w-8 items-center justify-center rounded-md text-gray-600 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:text-gray-300 dark:hover:bg-gray-800"
              :disabled="uploading"
              title="Вставить из буфера"
              aria-label="Вставить из буфера"
              @click="pasteFromClipboard"
            >
              <ClipboardPaste class="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-2 rounded-xl border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-900 lg:grid-cols-[1fr_180px_180px_160px_120px] lg:gap-3 lg:p-4">
      <label class="relative col-span-2 block lg:col-span-1">
        <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input
          v-model="query"
          type="search"
          placeholder="Поиск по названию, alt, файлу"
          class="w-full rounded-lg border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-gray-700 dark:bg-gray-950 dark:text-white"
          @keydown.enter="applyFilters"
        />
      </label>
      <select v-model="kind" class="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-gray-700 dark:bg-gray-950 dark:text-white">
        <option value="">Все типы</option>
        <option v-for="item in kindOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
      </select>
      <select v-model="tag" class="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-gray-700 dark:bg-gray-950 dark:text-white">
        <option value="">Все теги</option>
        <option v-for="item in tagList" :key="item" :value="item">{{ item }}</option>
      </select>
      <select v-model="status" class="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-gray-700 dark:bg-gray-950 dark:text-white">
        <option value="">Все статусы</option>
        <option value="ready">Готово</option>
        <option value="processing">В обработке</option>
        <option value="failed">Ошибка</option>
      </select>
      <button
        type="button"
        class="inline-flex items-center justify-center gap-2 rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-white dark:text-gray-950 dark:hover:bg-gray-100"
        :disabled="loading"
        @click="applyFilters"
      >
        <Search class="h-4 w-4" />
        {{ loading ? 'Ищу...' : 'Найти' }}
      </button>
    </div>

    <div class="grid gap-6 xl:grid-cols-[1fr_420px]">
      <div class="xl:min-h-[440px]">
        <div v-if="loading" class="grid grid-cols-2 gap-4 md:grid-cols-3 2xl:grid-cols-4">
          <div v-for="idx in 8" :key="idx" class="h-60 animate-pulse rounded-xl bg-gray-100 dark:bg-gray-800" />
        </div>
        <div v-else-if="!assets.length" class="flex min-h-[360px] items-center justify-center rounded-xl border border-gray-200 bg-white text-center dark:border-gray-800 dark:bg-gray-900">
          <div>
            <ImageIcon class="mx-auto h-12 w-12 text-gray-300" />
            <p class="mt-3 text-sm font-medium text-gray-900 dark:text-white">Файлов пока нет</p>
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">Загрузите первые изображения для медиатеки.</p>
          </div>
        </div>
        <div v-else class="grid grid-cols-2 gap-4 md:grid-cols-3 2xl:grid-cols-4">
          <button
            v-for="asset in assets"
            :key="asset.id"
            type="button"
            class="group overflow-hidden rounded-xl border bg-white text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:bg-gray-900"
            :class="selectedAsset?.id === asset.id ? 'border-teal-500 ring-2 ring-teal-500/20' : 'border-gray-200 dark:border-gray-800'"
            @click="selectAsset(asset)"
          >
            <div class="flex aspect-[4/3] items-center justify-center bg-gray-100 dark:bg-gray-950">
              <img :src="imageUrl(asset.url)" :alt="asset.alt_text || asset.title" class="h-full w-full object-contain" loading="lazy" />
            </div>
            <div class="space-y-2 p-3">
              <div class="flex items-start justify-between gap-2">
                <p class="line-clamp-2 text-sm font-medium text-gray-900 dark:text-white">{{ asset.title || asset.source_filename || asset.url }}</p>
                <span class="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-300">{{ variantLabel(asset.variant_type) }}</span>
              </div>
              <div class="flex flex-wrap gap-1">
                <span class="rounded bg-teal-50 px-1.5 py-0.5 text-[11px] font-medium text-teal-700 dark:bg-teal-950 dark:text-teal-200">{{ kindLabel(asset.kind) }}</span>
                <span v-for="item in (asset.tags || []).slice(0, 2)" :key="item" class="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-300">{{ item }}</span>
              </div>
              <p class="text-xs text-gray-500 dark:text-gray-400">{{ asset.width || 0 }}×{{ asset.height || 0 }} · {{ bytesLabel(asset.size_bytes) }}</p>
            </div>
          </button>
        </div>

        <div class="mt-4 flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
          <span>Страница {{ page }} из {{ pages }}</span>
          <div class="flex gap-2">
            <button class="rounded-lg border border-gray-300 px-3 py-1.5 disabled:opacity-50 dark:border-gray-700" :disabled="page <= 1" @click="page -= 1">Назад</button>
            <button class="rounded-lg border border-gray-300 px-3 py-1.5 disabled:opacity-50 dark:border-gray-700" :disabled="page >= pages" @click="page += 1">Вперед</button>
          </div>
        </div>
      </div>

      <aside class="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        <div v-if="!selectedAsset" class="flex min-h-[520px] items-center justify-center p-8 text-center">
          <div>
            <ImageIcon class="mx-auto h-10 w-10 text-gray-300" />
            <p class="mt-3 text-sm font-medium text-gray-900 dark:text-white">Выберите файл</p>
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">Метаданные и редактор появятся здесь.</p>
          </div>
        </div>
        <div v-else class="flex max-h-[calc(100vh-140px)] flex-col">
          <div class="flex items-center justify-between border-b border-gray-200 p-4 dark:border-gray-800">
            <div>
              <p class="text-sm font-semibold text-gray-900 dark:text-white">{{ selectedAsset.title || 'Без названия' }}</p>
              <p class="text-xs text-gray-500 dark:text-gray-400">#{{ selectedAsset.id }} · {{ selectedAsset.width }}×{{ selectedAsset.height }}</p>
            </div>
            <button class="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800" @click="selectedAsset = null">
              <X class="h-5 w-5" />
            </button>
          </div>

          <div class="space-y-5 overflow-y-auto p-4">
            <div class="rounded-xl bg-gray-100 p-3 dark:bg-gray-950">
              <ImageCropSelector
                v-if="cropMode"
                v-model="cropBox"
                :src="selectedUrl"
                :source-width="cropSourceSize.width"
                :source-height="cropSourceSize.height"
                :image-alt="selectedAsset.alt_text || selectedAsset.title || 'Изображение медиатеки'"
                @source-load="handleCropSourceLoad"
              />
              <div v-else class="mx-auto flex max-h-[420px] max-w-full justify-center">
                <img
                  :src="selectedUrl"
                  :alt="selectedAsset.alt_text || selectedAsset.title"
                  class="block max-h-[420px] max-w-full rounded-lg object-contain"
                  draggable="false"
                />
              </div>
            </div>

            <div class="grid grid-cols-2 gap-2">
              <button class="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800" @click="copyUrl()">
                <Copy class="h-4 w-4" />
                URL
              </button>
              <button class="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800" @click="toggleCropMode">
                <Scissors class="h-4 w-4" />
                Crop
              </button>
              <button class="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800" :disabled="Boolean(processing)" @click="removeBackground">
                <Wand2 class="h-4 w-4" />
                {{ processing === 'background' ? 'Фон...' : 'Без фона' }}
              </button>
              <button class="inline-flex items-center justify-center gap-2 rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-sm font-medium text-teal-800 transition hover:bg-teal-100 disabled:opacity-50 dark:border-teal-900/70 dark:bg-teal-950/30 dark:text-teal-100 dark:hover:bg-teal-950/60" :disabled="queueing || Boolean(activeSelectedProcessingJob)" @click="enqueueBackgroundRemoval">
                <Clock3 class="h-4 w-4" />
                {{ queueing ? 'Очередь...' : activeSelectedProcessingJob ? 'В очереди' : 'В очередь' }}
              </button>
              <button class="inline-flex items-center justify-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-600 transition hover:bg-red-50 disabled:opacity-50 dark:border-red-900/60 dark:hover:bg-red-950/30" :disabled="deleting" @click="deleteSelected">
                <Trash2 class="h-4 w-4" />
                Удалить
              </button>
            </div>
            <div class="grid gap-2 sm:grid-cols-2">
              <label class="block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Провайдер
                <select
                  v-model="backgroundProvider"
                  class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-800 focus:outline-none focus:ring-2 focus:ring-teal-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                >
                  <option
                    v-for="option in backgroundRemovalProviderOptions"
                    :key="option.value"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label v-if="showRembgModelSelect" class="block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Модель
                <select
                  v-model="backgroundModel"
                  class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-800 focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:opacity-60 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                  :disabled="backgroundModelsLoading"
                >
                  <option
                    v-for="option in backgroundModelOptions"
                    :key="option.value"
                    :value="option.value"
                  >
                    {{ option.recommended === false ? `${option.label} exp.` : option.label }}
                  </option>
                </select>
              </label>
            </div>
            <div v-if="showBackgroundExperimentWarning" class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-100">
              Экспериментальный режим лучше отправлять в очередь локальному worker-у: страница не зависнет, а слабый сервер не будет держать модель в памяти.
            </div>

            <div class="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-950/70">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-gray-900 dark:text-white">Очередь обработки</p>
                  <p class="text-xs text-gray-500 dark:text-gray-400">Локальный worker забирает задачи с этой очереди.</p>
                </div>
                <button
                  type="button"
                  class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-gray-600 transition hover:bg-white disabled:opacity-50 dark:text-gray-300 dark:hover:bg-gray-900"
                  :disabled="processingJobsLoading"
                  title="Обновить очередь"
                  aria-label="Обновить очередь"
                  @click="loadProcessingJobs"
                >
                  <RefreshCw class="h-4 w-4" :class="processingJobsLoading ? 'animate-spin' : ''" />
                </button>
              </div>
              <div v-if="activeSelectedProcessingJob" class="mt-3 rounded-md border border-teal-200 bg-white px-3 py-2 text-sm text-teal-900 dark:border-teal-900/70 dark:bg-gray-900 dark:text-teal-100">
                Текущий файл: {{ processingJobStatusLabel(activeSelectedProcessingJob.status) }}
              </div>
              <div v-if="visibleProcessingJobs.length" class="mt-3 space-y-2">
                <div
                  v-for="job in visibleProcessingJobs"
                  :key="job.job_id"
                  class="grid grid-cols-[1fr_auto] gap-2 rounded-md bg-white px-3 py-2 text-xs dark:bg-gray-900"
                >
                  <div class="min-w-0">
                    <p class="truncate font-medium text-gray-900 dark:text-white">{{ job.source_title || `asset #${job.source_asset_id}` }}</p>
                    <p class="truncate text-gray-500 dark:text-gray-400">{{ job.provider || 'worker' }}{{ job.rembg_model ? ` · ${job.rembg_model}` : '' }}</p>
                  </div>
                  <span class="self-start rounded px-2 py-0.5 font-medium" :class="processingJobStatusClass(job.status)">
                    {{ processingJobStatusLabel(job.status) }}
                  </span>
                </div>
              </div>
              <p v-else class="mt-3 text-xs text-gray-500 dark:text-gray-400">Очередь пуста.</p>
            </div>

            <div v-if="cropMode" class="rounded-lg border border-teal-200 bg-teal-50 p-3 dark:border-teal-900 dark:bg-teal-950/30">
              <div class="flex items-center justify-between gap-3">
                <p class="text-sm text-teal-900 dark:text-teal-100">Потяните рамку или углы, чтобы выбрать область.</p>
                <button class="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-teal-700 disabled:opacity-50" :disabled="!cropBox.width || !cropBox.height || processing === 'crop'" @click="applyCrop">
                  <Scissors class="h-4 w-4" />
                  {{ processing === 'crop' ? 'Сохраняю...' : 'Сохранить crop' }}
                </button>
              </div>
            </div>

            <div class="space-y-3">
              <label class="block">
                <span class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Название</span>
                <input v-model="editForm.title" class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-gray-700 dark:bg-gray-950 dark:text-white" />
              </label>
              <label class="block">
                <span class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Alt text</span>
                <input v-model="editForm.alt_text" class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-gray-700 dark:bg-gray-950 dark:text-white" />
              </label>
              <div class="grid grid-cols-2 gap-3">
                <label class="block">
                  <span class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Тип</span>
                  <select v-model="editForm.kind" class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-gray-700 dark:bg-gray-950 dark:text-white">
                    <option v-for="item in kindOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
                  </select>
                </label>
                <label class="block">
                  <span class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Теги</span>
                  <input v-model="editForm.tagsText" class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-gray-700 dark:bg-gray-950 dark:text-white" />
                </label>
              </div>
              <label class="block">
                <span class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Описание</span>
                <textarea v-model="editForm.description" rows="3" class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-gray-700 dark:bg-gray-950 dark:text-white" />
              </label>
              <button class="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-gray-800 disabled:opacity-50 dark:bg-white dark:text-gray-950" :disabled="saving" @click="saveSelected">
                <Save class="h-4 w-4" />
                {{ saving ? 'Сохраняю...' : 'Сохранить метаданные' }}
              </button>
            </div>

            <div class="space-y-1 rounded-lg bg-gray-50 p-3 text-xs text-gray-500 dark:bg-gray-950 dark:text-gray-400">
              <p class="break-all"><span class="font-medium">URL:</span> {{ selectedAsset.url }}</p>
              <p><span class="font-medium">Использований:</span> {{ selectedAsset.usage_count || 0 }}</p>
              <p><span class="font-medium">Hash:</span> {{ selectedAsset.content_hash?.slice(0, 16) || '—' }}</p>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <div
      v-if="toast"
      class="fixed bottom-5 right-5 z-50 rounded-xl px-4 py-3 text-sm font-medium shadow-lg"
      :class="toastType === 'error' ? 'bg-red-600 text-white' : 'bg-gray-900 text-white dark:bg-white dark:text-gray-950'"
    >
      {{ toast }}
    </div>
  </div>
</template>
