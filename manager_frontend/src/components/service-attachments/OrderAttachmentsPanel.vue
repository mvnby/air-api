<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { serviceAttachmentsApi } from './api';
import ServiceAttachmentViewer from './ServiceAttachmentViewer.vue';
import {
  SERVICE_ATTACHMENT_CATEGORIES,
  formatAttachmentDate,
  formatAttachmentSize,
  getAttachmentCategoryLabel,
  isAudioAttachment,
  isImageAttachment,
  isPdfAttachment,
  type ServiceAttachmentCategory,
  type ServiceAttachmentEquipmentOption,
  type ServiceAttachmentItem,
} from './types';

const props = withDefaults(defineProps<{
  orderId: number;
  initialCount?: number | null;
  defaultExpanded?: boolean;
  readonly?: boolean;
  equipmentOptions?: ServiceAttachmentEquipmentOption[];
}>(), {
  initialCount: null,
  defaultExpanded: false,
  readonly: false,
  equipmentOptions: () => [],
});

const emit = defineEmits<{
  'count-change': [value: number];
  uploaded: [item: ServiceAttachmentItem];
  updated: [item: ServiceAttachmentItem];
  deleted: [attachmentId: number];
  error: [message: string];
}>();

const fileInput = ref<HTMLInputElement | null>(null);
const expanded = ref(props.defaultExpanded);
const loaded = ref(false);
const loading = ref(false);
const loadError = ref('');
const actionError = ref('');
const actionMessage = ref('');
const items = ref<ServiceAttachmentItem[]>([]);
const total = ref(props.initialCount ?? 0);
const uploadingCount = ref(0);
const uploadCategory = ref<ServiceAttachmentCategory>('other');
const uploadCaption = ref('');
const uploadEquipmentId = ref<number | null>(null);
const uploadComponentId = ref<number | null>(null);
const viewerAttachmentId = ref<number | null>(null);
const editingId = ref<number | null>(null);
const editCategory = ref<ServiceAttachmentCategory | string>('other');
const editCaption = ref('');
const editEquipmentId = ref<number | null>(null);
const editComponentId = ref<number | null>(null);
const savingId = ref<number | null>(null);
const deletingId = ref<number | null>(null);
const previewUrls = reactive<Record<string, string>>({});
const audioUrls = reactive<Record<string, string>>({});
let listRequestId = 0;

const uploading = computed(() => uploadingCount.value > 0);
const visibleCount = computed(() => loaded.value ? total.value : (props.initialCount ?? total.value));
const imageItems = computed(() => items.value.filter(isImageAttachment));
const fileItems = computed(() => items.value.filter((item) => !isImageAttachment(item)));
const editingItem = computed(() => items.value.find((item) => item.id === editingId.value) || null);
const uploadComponents = computed(() => (
  props.equipmentOptions.find((item) => item.id === uploadEquipmentId.value)?.components || []
));
const editComponents = computed(() => (
  props.equipmentOptions.find((item) => item.id === editEquipmentId.value)?.components || []
));

const persistedId = (item: ServiceAttachmentItem) => (
  typeof item.id === 'number' && Number.isInteger(item.id) && item.id > 0 ? item.id : null
);
const attachmentKey = (item: ServiceAttachmentItem) => (
  persistedId(item) !== null ? `id:${item.id}` : (item.legacy_key || `legacy:${item.filename}:${item.created_at}`)
);

const iconForItem = (item: ServiceAttachmentItem) => {
  if (isAudioAttachment(item)) return 'graphic_eq';
  if (isPdfAttachment(item)) return 'picture_as_pdf';
  if (item.mime_type.includes('word') || /\.docx?$/i.test(item.filename)) return 'description';
  return 'draft';
};

const statusLabel = (status: string) => {
  if (status === 'ready' || status === 'completed') return 'Готово';
  if (status === 'failed' || status === 'error') return 'Ошибка';
  if (status === 'pending' || status === 'processing') return 'Обработка';
  return status || 'Сохранено';
};

const statusClass = (status: string) => {
  if (status === 'failed' || status === 'error') return 'bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-200';
  if (status === 'pending' || status === 'processing') return 'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-200';
  return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-200';
};

const reportError = (error: unknown, fallback: string) => {
  const message = error instanceof Error && error.message ? error.message : fallback;
  actionError.value = message;
  actionMessage.value = '';
  emit('error', message);
};

const replaceItem = (updated: ServiceAttachmentItem) => {
  const index = items.value.findIndex((item) => item.id === updated.id);
  if (index >= 0) items.value.splice(index, 1, updated);
};

const loadPreview = async (item: ServiceAttachmentItem) => {
  const attachmentId = persistedId(item);
  const key = attachmentKey(item);
  if (attachmentId === null || !item.preview_available || previewUrls[key]) return;
  try {
    const access = await serviceAttachmentsApi.getAccess(attachmentId, 'preview');
    previewUrls[key] = access.url;
  } catch {
    // A missing preview must not hide the attachment itself.
  }
};

const loadAudio = async (item: ServiceAttachmentItem) => {
  const attachmentId = persistedId(item);
  const key = attachmentKey(item);
  if (attachmentId === null || !isAudioAttachment(item) || audioUrls[key]) return;
  try {
    const access = await serviceAttachmentsApi.getAccess(attachmentId, 'original');
    audioUrls[key] = access.url;
  } catch {
    // The viewer still exposes a retry with the backend error.
  }
};

const hydrateMediaUrls = (attachmentItems: ServiceAttachmentItem[]) => {
  for (const item of attachmentItems) {
    if (isImageAttachment(item)) void loadPreview(item);
    if (isAudioAttachment(item)) void loadAudio(item);
  }
};

const loadAttachments = async (force = false) => {
  if (loading.value || (loaded.value && !force)) return;
  const requestId = ++listRequestId;
  loading.value = true;
  loadError.value = '';
  try {
    const response = await serviceAttachmentsApi.list(props.orderId);
    if (requestId !== listRequestId) return;
    items.value = response.items || [];
    total.value = Number(response.total ?? items.value.length);
    loaded.value = true;
    emit('count-change', total.value);
    hydrateMediaUrls(items.value);
  } catch (error) {
    if (requestId !== listRequestId) return;
    loadError.value = error instanceof Error ? error.message : 'Не удалось загрузить фото и файлы';
    emit('error', loadError.value);
  } finally {
    if (requestId === listRequestId) loading.value = false;
  }
};

const toggleExpanded = () => {
  expanded.value = !expanded.value;
  if (expanded.value) void loadAttachments();
};

const chooseFiles = () => fileInput.value?.click();

const uploadFiles = async (fileList: FileList | File[]) => {
  const files = Array.from(fileList);
  if (!files.length || props.readonly || uploading.value) return;
  const uploadMetadata = {
    category: uploadCategory.value,
    caption: uploadCaption.value,
    equipmentId: uploadEquipmentId.value,
    componentId: uploadComponentId.value,
  };
  actionError.value = '';
  actionMessage.value = '';
  uploadingCount.value += files.length;
  let uploaded = 0;

  for (const file of files) {
    try {
      const created = await serviceAttachmentsApi.upload(props.orderId, file, {
        ...uploadMetadata,
      });
      items.value = [created, ...items.value.filter((item) => item.id !== created.id)];
      total.value += 1;
      loaded.value = true;
      uploaded += 1;
      emit('uploaded', created);
      emit('count-change', total.value);
      hydrateMediaUrls([created]);
    } catch (error) {
      reportError(error, `Не удалось загрузить ${file.name}`);
    } finally {
      uploadingCount.value -= 1;
    }
  }

  if (uploaded) {
    actionMessage.value = uploaded === 1 ? 'Файл добавлен' : `Добавлено файлов: ${uploaded}`;
    uploadCaption.value = '';
  }
};

const onFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement;
  if (input.files?.length) void uploadFiles(input.files);
  input.value = '';
};

const onDrop = (event: DragEvent) => {
  event.preventDefault();
  if (event.dataTransfer?.files?.length) void uploadFiles(event.dataTransfer.files);
};

const onPaste = (event: ClipboardEvent) => {
  if (!expanded.value || props.readonly) return;
  const files: File[] = [];
  for (const item of Array.from(event.clipboardData?.items || [])) {
    if (item.kind !== 'file' || !item.type.startsWith('image/')) continue;
    const file = item.getAsFile();
    if (file) files.push(file);
  }
  if (!files.length) return;
  event.preventDefault();
  void uploadFiles(files);
};

const pasteFromClipboard = async () => {
  actionError.value = '';
  if (!navigator.clipboard?.read) {
    actionError.value = 'Нажмите Ctrl+V или Cmd+V внутри блока: браузер не даёт прямой доступ к буферу.';
    return;
  }
  try {
    const clipboardItems = await navigator.clipboard.read();
    const files: File[] = [];
    for (const item of clipboardItems) {
      const mime = item.types.find((type) => type.startsWith('image/'));
      if (!mime) continue;
      const blob = await item.getType(mime);
      const extension = mime.split('/')[1]?.replace('jpeg', 'jpg') || 'png';
      files.push(new File([blob], `clipboard-${Date.now()}.${extension}`, { type: mime }));
    }
    if (!files.length) throw new Error('В буфере нет изображения');
    await uploadFiles(files);
  } catch (error) {
    const message = error instanceof Error ? error.message : '';
    if (/permission|notallowed|denied/i.test(message)) {
      actionError.value = 'Браузер не дал прямой доступ к буферу. Нажмите Ctrl+V или Cmd+V внутри блока.';
      return;
    }
    reportError(error, 'Не удалось вставить изображение');
  }
};

const openViewer = (item: ServiceAttachmentItem) => {
  const attachmentId = persistedId(item);
  if (attachmentId === null) {
    actionError.value = item.processing_error || 'Старый файл ожидает безопасного переноса.';
    return;
  }
  viewerAttachmentId.value = attachmentId;
};

const beginEdit = (item: ServiceAttachmentItem) => {
  const attachmentId = persistedId(item);
  if (attachmentId === null) return;
  editingId.value = attachmentId;
  editCategory.value = item.category || 'other';
  editCaption.value = item.caption || '';
  editEquipmentId.value = item.equipment_id ?? null;
  editComponentId.value = item.component_id ?? null;
  actionError.value = '';
};

const saveEdit = async () => {
  const item = editingItem.value;
  if (!item) return;
  const attachmentId = persistedId(item);
  if (attachmentId === null) return;
  savingId.value = attachmentId;
  actionError.value = '';
  try {
    const updated = await serviceAttachmentsApi.update(props.orderId, attachmentId, {
      category: editCategory.value,
      caption: editCaption.value.trim() || null,
      ...(props.equipmentOptions.length ? {
        equipment_id: editEquipmentId.value,
        component_id: editComponentId.value,
      } : {}),
    });
    replaceItem(updated);
    editingId.value = null;
    actionMessage.value = 'Данные файла сохранены';
    emit('updated', updated);
  } catch (error) {
    reportError(error, 'Не удалось сохранить изменения');
  } finally {
    savingId.value = null;
  }
};

const deleteAttachment = async (item: ServiceAttachmentItem) => {
  const attachmentId = persistedId(item);
  if (attachmentId === null) return;
  if (!window.confirm(`Архивировать файл «${item.filename}»?`)) return;
  deletingId.value = attachmentId;
  actionError.value = '';
  try {
    await serviceAttachmentsApi.remove(props.orderId, attachmentId);
    items.value = items.value.filter((candidate) => candidate.id !== attachmentId);
    delete previewUrls[attachmentKey(item)];
    delete audioUrls[attachmentKey(item)];
    total.value = Math.max(0, total.value - 1);
    if (viewerAttachmentId.value === attachmentId) viewerAttachmentId.value = null;
    if (editingId.value === attachmentId) editingId.value = null;
    emit('deleted', attachmentId);
    emit('count-change', total.value);
    actionMessage.value = 'Файл перемещён в архив';
  } catch (error) {
    reportError(error, 'Не удалось архивировать файл');
  } finally {
    deletingId.value = null;
  }
};

const refresh = () => loadAttachments(true);
const expand = () => {
  expanded.value = true;
  return loadAttachments();
};

watch(() => props.orderId, () => {
  listRequestId += 1;
  items.value = [];
  total.value = props.initialCount ?? 0;
  loaded.value = false;
  loadError.value = '';
  actionError.value = '';
  viewerAttachmentId.value = null;
  editingId.value = null;
  for (const key of Object.keys(previewUrls)) delete previewUrls[key];
  for (const key of Object.keys(audioUrls)) delete audioUrls[key];
  if (expanded.value) void loadAttachments();
});

watch(() => props.initialCount, (value) => {
  if (!loaded.value) total.value = value ?? 0;
});

watch(uploadEquipmentId, () => {
  uploadComponentId.value = null;
});

if (expanded.value) void loadAttachments();

defineExpose({ refresh, expand });
</script>

<template>
  <section
    class="rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900/70"
    tabindex="0"
    @paste="onPaste"
    @dragover.prevent
    @drop="onDrop"
  >
    <button
      type="button"
      class="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left transition hover:bg-slate-50 dark:hover:bg-slate-800/60 sm:px-4"
      :aria-expanded="expanded"
      @click="toggleExpanded"
    >
      <span class="material-icons-round text-[21px] text-teal-700 dark:text-teal-300" aria-hidden="true">perm_media</span>
      <span class="min-w-0 flex-1">
        <span class="block text-sm font-semibold text-slate-900 dark:text-slate-100">Фото и файлы</span>
        <span class="block truncate text-xs text-slate-500 dark:text-slate-400">
          {{ loaded ? (total ? `${total} файлов` : 'Файлов пока нет') : (visibleCount ? `${visibleCount} файлов` : 'Загрузятся при открытии') }}
        </span>
      </span>
      <span class="inline-flex min-w-7 items-center justify-center rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
        {{ visibleCount }}
      </span>
      <span class="material-icons-round text-[21px] text-slate-500" aria-hidden="true">{{ expanded ? 'expand_less' : 'expand_more' }}</span>
    </button>

    <div v-if="expanded" class="border-t border-slate-200 px-3 pb-4 pt-3 dark:border-slate-700 sm:px-4">
      <div v-if="loadError" class="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200" role="alert">
        <span class="material-icons-round mt-0.5 text-[18px]" aria-hidden="true">error</span>
        <span class="min-w-0 flex-1">{{ loadError }}</span>
        <button type="button" class="shrink-0 font-semibold underline" @click="loadAttachments(true)">Повторить</button>
      </div>

      <div v-if="!readonly" class="grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(150px,0.75fr)_minmax(200px,1.25fr)_auto]">
        <label class="min-w-0">
          <span class="sr-only">Категория нового файла</span>
          <select v-model="uploadCategory" class="field-input h-10 text-sm">
            <option v-for="category in SERVICE_ATTACHMENT_CATEGORIES" :key="category.value" :value="category.value">{{ category.label }}</option>
          </select>
        </label>
        <label class="min-w-0">
          <span class="sr-only">Подпись нового файла</span>
          <input v-model="uploadCaption" class="field-input h-10 text-sm" placeholder="Подпись, если нужна" />
        </label>
        <div class="flex items-center gap-2">
          <button type="button" class="btn-mini h-10 flex-1 justify-center whitespace-nowrap sm:flex-none" :disabled="uploading" @click="chooseFiles">
            <span class="material-icons-round text-[19px]" aria-hidden="true">upload</span>
            <span>{{ uploading ? `Загрузка ${uploadingCount}` : 'Загрузить' }}</span>
          </button>
          <button type="button" class="btn-mini-outline h-10 w-10 justify-center p-0" :disabled="uploading" title="Вставить изображение из буфера" aria-label="Вставить изображение из буфера" @click="pasteFromClipboard">
            <span class="material-icons-round text-[19px]" aria-hidden="true">content_paste</span>
          </button>
          <button v-if="loaded" type="button" class="btn-mini-outline h-10 w-10 justify-center p-0" :disabled="loading" title="Обновить список" aria-label="Обновить список" @click="refresh">
            <span class="material-icons-round text-[19px]" :class="loading ? 'animate-spin' : ''" aria-hidden="true">refresh</span>
          </button>
        </div>
        <input ref="fileInput" type="file" class="hidden" multiple accept="image/*,audio/*,application/pdf,.doc,.docx,.xls,.xlsx,.txt" @change="onFileChange" />
      </div>

      <div v-if="!readonly" class="mt-2 grid gap-2 sm:grid-cols-2">
        <label class="min-w-0">
          <span class="sr-only">Связать с оборудованием</span>
          <select v-model="uploadEquipmentId" class="field-input h-10 text-sm">
            <option :value="null">Без привязки к оборудованию</option>
            <option v-for="equipment in equipmentOptions" :key="equipment.id" :value="equipment.id">{{ equipment.label }}</option>
          </select>
        </label>
        <label v-if="uploadEquipmentId && uploadComponents.length" class="min-w-0">
          <span class="sr-only">Связать с блоком оборудования</span>
          <select v-model="uploadComponentId" class="field-input h-10 text-sm">
            <option :value="null">Вся система</option>
            <option v-for="component in uploadComponents" :key="component.id" :value="component.id">{{ component.label }}</option>
          </select>
        </label>
      </div>

      <p v-if="!readonly" class="mt-2 text-xs text-slate-500 dark:text-slate-400">
        Можно перетащить файлы сюда или вставить изображение через Ctrl+V / Cmd+V.
      </p>

      <div v-if="actionError" class="mt-3 flex items-start gap-2 text-sm text-red-600 dark:text-red-300" role="alert">
        <span class="material-icons-round mt-0.5 text-[18px]" aria-hidden="true">warning</span>
        <span>{{ actionError }}</span>
      </div>
      <div v-else-if="actionMessage" class="mt-3 flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-300" aria-live="polite">
        <span class="material-icons-round text-[18px]" aria-hidden="true">check_circle</span>
        <span>{{ actionMessage }}</span>
      </div>

      <div v-if="loading && !loaded" class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4" aria-label="Загрузка файлов">
        <div v-for="index in 4" :key="index" class="aspect-[4/3] animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
      </div>

      <div v-else-if="loaded && !items.length" class="mt-4 border-t border-dashed border-slate-300 py-8 text-center dark:border-slate-700">
        <span class="material-icons-round text-[34px] text-slate-300 dark:text-slate-600" aria-hidden="true">add_photo_alternate</span>
        <p class="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-200">Фото и документов пока нет</p>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Первый загруженный файл сразу появится здесь.</p>
      </div>

      <div v-if="imageItems.length" class="mt-4">
        <h4 class="mb-2 text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Изображения</h4>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          <article v-for="item in imageItems" :key="attachmentKey(item)" class="group relative min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/50">
            <button type="button" class="block w-full text-left" @click="openViewer(item)">
              <span class="flex aspect-[4/3] items-center justify-center overflow-hidden bg-slate-100 dark:bg-slate-950">
                <img v-if="previewUrls[attachmentKey(item)]" :src="previewUrls[attachmentKey(item)]" :alt="item.caption || item.filename" loading="lazy" class="h-full w-full object-cover" @error="delete previewUrls[attachmentKey(item)]" />
                <span v-else class="material-icons-round text-[34px] text-slate-300 dark:text-slate-600" aria-hidden="true">image</span>
              </span>
              <span class="block min-w-0 p-2">
                <span class="block truncate text-xs font-semibold text-slate-800 dark:text-slate-100">{{ item.caption || item.filename }}</span>
                <span class="mt-0.5 block truncate text-[11px] text-slate-500 dark:text-slate-400">{{ getAttachmentCategoryLabel(item.category) }} · {{ formatAttachmentDate(item.captured_at || item.created_at) }}</span>
              </span>
            </button>
            <span class="absolute left-1.5 top-1.5 rounded-md px-1.5 py-0.5 text-[10px] font-semibold shadow-sm" :class="statusClass(item.processing_status)">{{ statusLabel(item.processing_status) }}</span>
            <button v-if="!readonly && !item.legacy && item.id !== null" type="button" class="absolute right-1.5 top-1.5 inline-flex h-8 w-8 items-center justify-center rounded-lg bg-white/95 text-slate-600 shadow-sm hover:text-teal-700 dark:bg-slate-900/95 dark:text-slate-300" title="Изменить файл" aria-label="Изменить файл" @click.stop="beginEdit(item)">
              <span class="material-icons-round text-[18px]" aria-hidden="true">edit</span>
            </button>
            <p v-if="item.processing_error" class="border-t border-red-100 px-2 py-1.5 text-[11px] text-red-600 dark:border-red-900/40 dark:text-red-300">{{ item.processing_error }}</p>
          </article>
        </div>
      </div>

      <div v-if="fileItems.length" class="mt-4">
        <h4 class="mb-2 text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Документы и аудио</h4>
        <div class="divide-y divide-slate-200 border-y border-slate-200 dark:divide-slate-700 dark:border-slate-700">
          <article v-for="item in fileItems" :key="attachmentKey(item)" class="py-3">
            <div class="flex min-w-0 items-start gap-3">
              <button type="button" class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600 hover:text-teal-700 dark:bg-slate-800 dark:text-slate-300" :title="`Открыть ${item.filename}`" :aria-label="`Открыть ${item.filename}`" @click="openViewer(item)">
                <span class="material-icons-round text-[22px]" aria-hidden="true">{{ iconForItem(item) }}</span>
              </button>
              <button type="button" class="min-w-0 flex-1 text-left" @click="openViewer(item)">
                <span class="block truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{{ item.caption || item.filename }}</span>
                <span class="mt-0.5 block truncate text-xs text-slate-500 dark:text-slate-400">
                  {{ getAttachmentCategoryLabel(item.category) }} · {{ formatAttachmentDate(item.captured_at || item.created_at) }}<span v-if="formatAttachmentSize(item.size_bytes)"> · {{ formatAttachmentSize(item.size_bytes) }}</span>
                </span>
              </button>
              <span class="hidden shrink-0 rounded-md px-2 py-1 text-[11px] font-semibold sm:inline" :class="statusClass(item.processing_status)">{{ statusLabel(item.processing_status) }}</span>
              <button v-if="!readonly && !item.legacy && item.id !== null" type="button" class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-teal-700 dark:text-slate-400 dark:hover:bg-slate-800" title="Изменить файл" aria-label="Изменить файл" @click="beginEdit(item)">
                <span class="material-icons-round text-[19px]" aria-hidden="true">edit</span>
              </button>
            </div>
            <audio v-if="isAudioAttachment(item) && audioUrls[attachmentKey(item)]" :src="audioUrls[attachmentKey(item)]" controls preload="metadata" class="mt-2 h-9 w-full" />
            <p v-if="item.transcript" class="mt-2 line-clamp-3 whitespace-pre-wrap text-xs leading-5 text-slate-600 dark:text-slate-300">{{ item.transcript }}</p>
            <p v-if="item.processing_error" class="mt-1 text-xs text-red-600 dark:text-red-300">{{ item.processing_error }}</p>
          </article>
        </div>
      </div>

      <form v-if="editingItem && !readonly" class="mt-4 border-t border-slate-200 pt-3 dark:border-slate-700" @submit.prevent="saveEdit">
        <div class="mb-2 flex items-center justify-between gap-3">
          <p class="min-w-0 truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{{ editingItem.filename }}</p>
          <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" title="Закрыть редактирование" aria-label="Закрыть редактирование" @click="editingId = null">
            <span class="material-icons-round text-[19px]" aria-hidden="true">close</span>
          </button>
        </div>
        <div class="grid gap-2 sm:grid-cols-2">
          <label class="field-label">
            Категория
            <select v-model="editCategory" class="field-input h-10 text-sm">
              <option v-for="category in SERVICE_ATTACHMENT_CATEGORIES" :key="category.value" :value="category.value">{{ category.label }}</option>
            </select>
          </label>
          <label class="field-label">
            Подпись
            <input v-model="editCaption" class="field-input h-10 text-sm" placeholder="Что изображено или приложено" />
          </label>
          <label class="field-label">
            Связать с оборудованием
            <select v-model="editEquipmentId" class="field-input h-10 text-sm" @change="editComponentId = null">
              <option :value="null">Без привязки к оборудованию</option>
              <option v-for="equipment in equipmentOptions" :key="equipment.id" :value="equipment.id">{{ equipment.label }}</option>
            </select>
          </label>
          <label v-if="editEquipmentId && editComponents.length" class="field-label">
            Блок
            <select v-model="editComponentId" class="field-input h-10 text-sm">
              <option :value="null">Вся система</option>
              <option v-for="component in editComponents" :key="component.id" :value="component.id">{{ component.label }}</option>
            </select>
          </label>
        </div>
        <div class="mt-3 flex flex-wrap items-center justify-between gap-2">
          <button type="button" class="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50 dark:text-red-300 dark:hover:bg-red-950/30" :disabled="deletingId === editingItem.id" @click="deleteAttachment(editingItem)">
            <span class="material-icons-round text-[18px]" aria-hidden="true">delete</span>
            Архивировать
          </button>
          <div class="ml-auto flex items-center gap-2">
            <button type="button" class="btn-mini-outline" @click="editingId = null">Отмена</button>
            <button type="submit" class="btn-mini" :disabled="savingId === editingItem.id">
              <span class="material-icons-round text-[18px]" aria-hidden="true">save</span>
              {{ savingId === editingItem.id ? 'Сохраняем...' : 'Сохранить' }}
            </button>
          </div>
        </div>
      </form>
    </div>
  </section>

  <ServiceAttachmentViewer v-model="viewerAttachmentId" :items="items" />
</template>
