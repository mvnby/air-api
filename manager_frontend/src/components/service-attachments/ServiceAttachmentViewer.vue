<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { serviceAttachmentsApi } from './api';
import {
  formatAttachmentDate,
  formatAttachmentSize,
  getAttachmentCategoryLabel,
  isAudioAttachment,
  isImageAttachment,
  isPdfAttachment,
  type ServiceAttachmentItem,
} from './types';

const props = defineProps<{
  items: ServiceAttachmentItem[];
  modelValue: number | null;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: number | null];
  close: [];
}>();

const accessUrl = ref('');
const accessLoading = ref(false);
const accessError = ref('');
const zoom = ref(1);
const detailsOpen = ref(false);
let accessRequestId = 0;
let previousBodyOverflow = '';

const activeIndex = computed(() => props.items.findIndex((item) => item.id === props.modelValue));
const activeItem = computed(() => activeIndex.value >= 0 ? props.items[activeIndex.value] : null);
const isOpen = computed(() => Boolean(activeItem.value));
const isImage = computed(() => Boolean(activeItem.value && isImageAttachment(activeItem.value)));
const isPdf = computed(() => Boolean(activeItem.value && isPdfAttachment(activeItem.value)));
const isAudio = computed(() => Boolean(activeItem.value && isAudioAttachment(activeItem.value)));
const hasPrevious = computed(() => activeIndex.value > 0);
const hasNext = computed(() => activeIndex.value >= 0 && activeIndex.value < props.items.length - 1);
const itemPosition = computed(() => activeIndex.value >= 0 ? `${activeIndex.value + 1} / ${props.items.length}` : '');

const statusLabel = computed(() => {
  const status = activeItem.value?.processing_status || '';
  if (status === 'ready' || status === 'completed') return 'Готово';
  if (status === 'failed' || status === 'error') return 'Ошибка обработки';
  if (status === 'pending' || status === 'processing') return 'Обрабатывается';
  return status || 'Сохранено';
});

const fileIcon = computed(() => {
  if (isPdf.value) return 'picture_as_pdf';
  if (isAudio.value) return 'graphic_eq';
  return 'draft';
});

const close = () => {
  emit('update:modelValue', null);
  emit('close');
};

const showPrevious = () => {
  if (!hasPrevious.value) return;
  emit('update:modelValue', props.items[activeIndex.value - 1]?.id ?? null);
};

const showNext = () => {
  if (!hasNext.value) return;
  emit('update:modelValue', props.items[activeIndex.value + 1]?.id ?? null);
};

const setZoom = (value: number) => {
  zoom.value = Math.min(3, Math.max(0.5, Number(value.toFixed(2))));
};

const onWheel = (event: WheelEvent) => {
  if (!isImage.value) return;
  event.preventDefault();
  setZoom(zoom.value + (event.deltaY < 0 ? 0.25 : -0.25));
};

const loadAccess = async () => {
  const item = activeItem.value;
  const requestId = ++accessRequestId;
  accessUrl.value = '';
  accessError.value = '';
  zoom.value = 1;
  detailsOpen.value = false;
  if (!item) return;

  accessLoading.value = true;
  try {
    const response = await serviceAttachmentsApi.getAccess(item.id, 'original');
    if (requestId !== accessRequestId) return;
    accessUrl.value = response.url;
  } catch (error) {
    if (requestId !== accessRequestId) return;
    accessError.value = error instanceof Error ? error.message : 'Не удалось открыть файл';
  } finally {
    if (requestId === accessRequestId) accessLoading.value = false;
  }
};

const onKeydown = (event: KeyboardEvent) => {
  if (!isOpen.value) return;
  if (event.key === 'Escape') close();
  if (event.key === 'ArrowLeft') showPrevious();
  if (event.key === 'ArrowRight') showNext();
  if (isImage.value && (event.key === '+' || event.key === '=')) setZoom(zoom.value + 0.25);
  if (isImage.value && event.key === '-') setZoom(zoom.value - 0.25);
};

watch(() => activeItem.value?.id, () => void loadAccess(), { immediate: true });

watch(isOpen, (open) => {
  if (open) {
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
  } else {
    document.body.style.overflow = previousBodyOverflow;
  }
});

onMounted(() => document.addEventListener('keydown', onKeydown));
onBeforeUnmount(() => {
  accessRequestId += 1;
  document.removeEventListener('keydown', onKeydown);
  if (isOpen.value) document.body.style.overflow = previousBodyOverflow;
});
</script>

<template>
  <Teleport to="body">
    <div
      v-if="isOpen && activeItem"
      class="fixed inset-0 z-[120] flex flex-col bg-slate-950/95 text-white"
      role="dialog"
      aria-modal="true"
      :aria-label="`Просмотр файла ${activeItem.filename}`"
    >
      <header class="flex min-h-14 items-center gap-2 border-b border-white/10 px-3 py-2 sm:px-5">
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-semibold sm:text-base">{{ activeItem.filename }}</p>
          <p class="truncate text-xs text-slate-300">
            {{ getAttachmentCategoryLabel(activeItem.category) }}<span v-if="itemPosition"> · {{ itemPosition }}</span>
          </p>
        </div>

        <div v-if="isImage" class="hidden items-center gap-1 rounded-lg bg-white/10 p-1 sm:flex">
          <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-white/10 disabled:opacity-40" :disabled="zoom <= 0.5" title="Уменьшить" aria-label="Уменьшить" @click="setZoom(zoom - 0.25)">
            <span class="material-icons-round text-[19px]" aria-hidden="true">remove</span>
          </button>
          <button type="button" class="min-w-14 rounded-md px-2 py-1 text-xs font-semibold hover:bg-white/10" title="Сбросить масштаб" @click="setZoom(1)">
            {{ Math.round(zoom * 100) }}%
          </button>
          <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-white/10 disabled:opacity-40" :disabled="zoom >= 3" title="Увеличить" aria-label="Увеличить" @click="setZoom(zoom + 0.25)">
            <span class="material-icons-round text-[19px]" aria-hidden="true">add</span>
          </button>
        </div>

        <a
          v-if="accessUrl"
          :href="accessUrl"
          :download="activeItem.filename"
          target="_blank"
          rel="noopener"
          class="inline-flex h-9 w-9 items-center justify-center rounded-lg hover:bg-white/10"
          title="Скачать оригинал"
          aria-label="Скачать оригинал"
        >
          <span class="material-icons-round text-[21px]" aria-hidden="true">download</span>
        </a>
        <button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-lg hover:bg-white/10" title="Закрыть" aria-label="Закрыть" @click="close">
          <span class="material-icons-round text-[22px]" aria-hidden="true">close</span>
        </button>
      </header>

      <main class="relative min-h-0 flex-1 overflow-hidden">
        <div v-if="accessLoading" class="flex h-full items-center justify-center" aria-live="polite">
          <div class="text-center text-slate-300">
            <span class="material-icons-round animate-spin text-[34px]" aria-hidden="true">progress_activity</span>
            <p class="mt-2 text-sm">Открываем приватный файл...</p>
          </div>
        </div>

        <div v-else-if="accessError" class="flex h-full items-center justify-center p-6 text-center">
          <div class="max-w-md">
            <span class="material-icons-round text-[40px] text-red-300" aria-hidden="true">error</span>
            <p class="mt-2 text-sm font-semibold">Файл не открылся</p>
            <p class="mt-1 text-xs text-slate-300">{{ accessError }}</p>
            <button type="button" class="mt-4 rounded-lg bg-white px-3 py-2 text-sm font-semibold text-slate-900" @click="loadAccess">Повторить</button>
          </div>
        </div>

        <div v-else-if="accessUrl && isImage" class="flex h-full items-center justify-center overflow-auto p-3 sm:p-6" @wheel="onWheel">
          <img
            :src="accessUrl"
            :alt="activeItem.caption || activeItem.filename"
            class="max-h-full max-w-full select-none object-contain transition-transform duration-150"
            :style="{ transform: `scale(${zoom})` }"
            draggable="false"
          />
        </div>

        <div v-else-if="accessUrl && isPdf" class="h-full p-2 sm:p-4">
          <iframe :src="accessUrl" :title="activeItem.filename" class="h-full w-full rounded-lg bg-white" />
        </div>

        <div v-else-if="accessUrl && isAudio" class="flex h-full items-center justify-center p-5">
          <div class="w-full max-w-2xl text-center">
            <span class="material-icons-round text-[64px] text-teal-300" aria-hidden="true">graphic_eq</span>
            <audio :src="accessUrl" controls preload="metadata" class="mt-5 w-full" />
            <div v-if="activeItem.transcript" class="mt-5 max-h-52 overflow-y-auto rounded-lg bg-white/10 p-4 text-left text-sm leading-6 text-slate-100">
              <p class="mb-1 text-xs font-semibold uppercase text-slate-300">Расшифровка</p>
              {{ activeItem.transcript }}
            </div>
          </div>
        </div>

        <div v-else-if="accessUrl" class="flex h-full items-center justify-center p-5 text-center">
          <div class="max-w-md">
            <span class="material-icons-round text-[64px] text-slate-300" aria-hidden="true">{{ fileIcon }}</span>
            <p class="mt-3 truncate text-base font-semibold">{{ activeItem.filename }}</p>
            <p class="mt-1 text-sm text-slate-300">Предпросмотр этого формата недоступен.</p>
            <a :href="accessUrl" target="_blank" rel="noopener" class="mt-5 inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-900">
              <span class="material-icons-round text-[19px]" aria-hidden="true">open_in_new</span>
              Открыть файл
            </a>
          </div>
        </div>

        <button
          v-if="hasPrevious"
          type="button"
          class="absolute left-2 top-1/2 inline-flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-lg bg-slate-950/70 shadow-lg hover:bg-slate-800 sm:left-4"
          title="Предыдущий файл"
          aria-label="Предыдущий файл"
          @click="showPrevious"
        >
          <span class="material-icons-round text-[28px]" aria-hidden="true">chevron_left</span>
        </button>
        <button
          v-if="hasNext"
          type="button"
          class="absolute right-2 top-1/2 inline-flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-lg bg-slate-950/70 shadow-lg hover:bg-slate-800 sm:right-4"
          title="Следующий файл"
          aria-label="Следующий файл"
          @click="showNext"
        >
          <span class="material-icons-round text-[28px]" aria-hidden="true">chevron_right</span>
        </button>
      </main>

      <footer class="border-t border-white/10 bg-slate-950/85 px-3 py-2 sm:px-5">
        <div class="flex items-center gap-3">
          <p class="min-w-0 flex-1 truncate text-xs text-slate-300">
            <span v-if="activeItem.caption" class="text-white">{{ activeItem.caption }}</span>
            <span v-else>{{ formatAttachmentDate(activeItem.captured_at || activeItem.created_at) }}</span>
            <span v-if="formatAttachmentSize(activeItem.size_bytes)"> · {{ formatAttachmentSize(activeItem.size_bytes) }}</span>
          </p>
          <div v-if="isImage" class="flex items-center gap-1 sm:hidden">
            <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-white/10 disabled:opacity-40" :disabled="zoom <= 0.5" aria-label="Уменьшить" @click="setZoom(zoom - 0.25)"><span class="material-icons-round text-[18px]" aria-hidden="true">remove</span></button>
            <button type="button" class="min-w-12 text-xs font-semibold" @click="setZoom(1)">{{ Math.round(zoom * 100) }}%</button>
            <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-white/10 disabled:opacity-40" :disabled="zoom >= 3" aria-label="Увеличить" @click="setZoom(zoom + 0.25)"><span class="material-icons-round text-[18px]" aria-hidden="true">add</span></button>
          </div>
          <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg hover:bg-white/10" :aria-expanded="detailsOpen" title="Сведения о файле" aria-label="Сведения о файле" @click="detailsOpen = !detailsOpen">
            <span class="material-icons-round text-[20px]" aria-hidden="true">info</span>
          </button>
        </div>
        <div v-if="detailsOpen" class="mt-2 grid gap-x-6 gap-y-1 border-t border-white/10 pt-2 text-xs text-slate-300 sm:grid-cols-2">
          <p><span class="text-slate-400">Источник:</span> {{ activeItem.source || 'не указан' }}</p>
          <p><span class="text-slate-400">Статус:</span> {{ statusLabel }}</p>
          <p><span class="text-slate-400">Дата:</span> {{ formatAttachmentDate(activeItem.captured_at || activeItem.created_at) }}</p>
          <p><span class="text-slate-400">Тип:</span> {{ activeItem.mime_type || activeItem.file_kind }}</p>
          <p v-if="activeItem.processing_error" class="text-red-300 sm:col-span-2">{{ activeItem.processing_error }}</p>
          <p v-if="activeItem.transcript && !isAudio" class="whitespace-pre-wrap text-slate-100 sm:col-span-2">{{ activeItem.transcript }}</p>
        </div>
      </footer>
    </div>
  </Teleport>
</template>
