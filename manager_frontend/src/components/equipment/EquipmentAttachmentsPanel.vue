<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { ChevronDown, ChevronUp, FileText, Images, LoaderCircle, RefreshCw } from 'lucide-vue-next';
import { serviceAttachmentsApi } from '../service-attachments/api';
import ServiceAttachmentViewer from '../service-attachments/ServiceAttachmentViewer.vue';
import {
  formatAttachmentDate,
  getAttachmentCategoryLabel,
  isImageAttachment,
  type ServiceAttachmentItem,
} from '../service-attachments/types';

const props = defineProps<{ equipmentId: number }>();

const expanded = ref(false);
const loaded = ref(false);
const loading = ref(false);
const error = ref('');
const items = ref<ServiceAttachmentItem[]>([]);
const loadedEquipmentId = ref<number | null>(null);
const viewerAttachmentId = ref<number | null>(null);
const previewUrls = reactive<Record<number, string>>({});
let loadRequestId = 0;
let loadingEquipmentId: number | null = null;

const imageItems = computed(() => items.value.filter(isImageAttachment));
const fileItems = computed(() => items.value.filter((item) => !isImageAttachment(item)));

const hydratePreviews = async (attachmentItems: ServiceAttachmentItem[], requestId: number) => {
  for (const item of attachmentItems.filter(isImageAttachment)) {
    if (!item.id || !item.preview_available || previewUrls[item.id]) continue;
    try {
      const access = await serviceAttachmentsApi.getAccess(item.id, 'preview');
      if (requestId !== loadRequestId) return;
      previewUrls[item.id] = access.url;
    } catch {
      // Карточка файла остается доступной даже без превью.
    }
  }
};

const load = async (force = false) => {
  const equipmentId = props.equipmentId;
  if (!force && loaded.value && loadedEquipmentId.value === equipmentId) return;
  if (!force && loading.value && loadingEquipmentId === equipmentId) return;
  const requestId = ++loadRequestId;
  loadingEquipmentId = equipmentId;
  loading.value = true;
  error.value = '';
  try {
    const response = await serviceAttachmentsApi.listEquipment(equipmentId);
    if (requestId !== loadRequestId || props.equipmentId !== equipmentId) return;
    const nextItems = response.items || [];
    items.value = nextItems;
    loaded.value = true;
    loadedEquipmentId.value = equipmentId;
    await hydratePreviews(nextItems, requestId);
  } catch (cause) {
    if (requestId !== loadRequestId || props.equipmentId !== equipmentId) return;
    error.value = cause instanceof Error ? cause.message : 'Не удалось загрузить файлы оборудования';
  } finally {
    if (requestId === loadRequestId) {
      loading.value = false;
      loadingEquipmentId = null;
    }
  }
};

const toggle = () => {
  expanded.value = !expanded.value;
  if (expanded.value) void load();
};

const open = (item: ServiceAttachmentItem) => {
  if (item.id) viewerAttachmentId.value = item.id;
};

const clearPreview = (item: ServiceAttachmentItem) => {
  if (item.id) delete previewUrls[item.id];
};

watch(() => props.equipmentId, () => {
  loadRequestId += 1;
  loadingEquipmentId = null;
  loading.value = false;
  items.value = [];
  loaded.value = false;
  loadedEquipmentId.value = null;
  error.value = '';
  viewerAttachmentId.value = null;
  for (const key of Object.keys(previewUrls)) delete previewUrls[Number(key)];
  if (expanded.value) void load();
});
</script>

<template>
  <section class="mt-4 rounded-xl border border-[var(--mv-border)] bg-[var(--mv-panel)]">
    <button type="button" class="flex w-full items-center gap-3 px-3 py-3 text-left" :aria-expanded="expanded" @click="toggle">
      <Images class="h-4 w-4 shrink-0 text-teal-500" />
      <span class="min-w-0 flex-1">
        <span class="block text-sm font-semibold text-[var(--mv-text)]">Фото и файлы оборудования</span>
        <span class="block text-xs text-[var(--mv-text-muted)]">{{ loaded ? `${items.length} файлов` : 'Загрузятся при открытии' }}</span>
      </span>
      <ChevronUp v-if="expanded" class="h-4 w-4 text-[var(--mv-text-muted)]" />
      <ChevronDown v-else class="h-4 w-4 text-[var(--mv-text-muted)]" />
    </button>

    <div v-if="expanded" class="border-t border-[var(--mv-border)] p-3">
      <div v-if="loading && !loaded" class="flex items-center gap-2 py-4 text-sm text-[var(--mv-text-muted)]">
        <LoaderCircle class="h-4 w-4 animate-spin" />
        Загрузка файлов
      </div>
      <div v-else-if="error" class="flex items-center justify-between gap-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">
        <span>{{ error }}</span>
        <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-red-500/10" title="Повторить" aria-label="Повторить" @click="load(true)">
          <RefreshCw class="h-4 w-4" />
        </button>
      </div>
      <p v-else-if="!items.length" class="py-4 text-center text-sm text-[var(--mv-text-muted)]">Связанных файлов пока нет</p>

      <div v-if="imageItems.length" class="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <button v-for="item in imageItems" :key="item.id || item.legacy_key || `${item.filename}-${item.created_at}`" type="button" class="group relative aspect-square overflow-hidden rounded-lg border border-[var(--mv-border)] bg-[var(--mv-surface)]" @click="open(item)">
          <img v-if="item.id && previewUrls[item.id]" :src="previewUrls[item.id]" :alt="item.caption || item.filename" class="h-full w-full object-cover transition group-hover:scale-[1.02]" @error="clearPreview(item)" />
          <Images v-else class="absolute left-1/2 top-1/2 h-7 w-7 -translate-x-1/2 -translate-y-1/2 text-[var(--mv-text-muted)]" />
          <span class="absolute inset-x-0 bottom-0 bg-black/65 px-2 py-1 text-left text-[10px] font-semibold text-white">{{ getAttachmentCategoryLabel(item.category) }}</span>
        </button>
      </div>

      <div v-if="fileItems.length" class="mt-2 divide-y divide-[var(--mv-border)] border-y border-[var(--mv-border)]">
        <button v-for="item in fileItems" :key="item.id || item.legacy_key || `${item.filename}-${item.created_at}`" type="button" class="flex w-full items-center gap-3 py-2 text-left" @click="open(item)">
          <FileText class="h-4 w-4 shrink-0 text-teal-500" />
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-semibold text-[var(--mv-text)]">{{ item.filename }}</span>
            <span class="block text-xs text-[var(--mv-text-muted)]">{{ getAttachmentCategoryLabel(item.category) }} · {{ formatAttachmentDate(item.created_at) }}</span>
          </span>
        </button>
      </div>
    </div>
  </section>

  <ServiceAttachmentViewer v-model="viewerAttachmentId" :items="items" />
</template>
