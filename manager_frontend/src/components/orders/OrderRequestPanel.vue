<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import type { ManagerOrderRequestContext, OrderRequestFile } from '../../client';
import ServiceAttachmentViewer from '../service-attachments/ServiceAttachmentViewer.vue';
import { formatAttachmentSize, type ServiceAttachmentItem, type ServiceAttachmentAccessResponse } from '../service-attachments/types';

const props = defineProps<{
  context: Required<ManagerOrderRequestContext> | null;
  description: string;
  loading: boolean;
  error: string;
  resolveAccess: (item: ServiceAttachmentItem, download: boolean) => Promise<ServiceAttachmentAccessResponse>;
}>();
defineEmits<{ close: []; retry: [] }>();
const closeButton = ref<HTMLButtonElement | null>(null);
const descriptionExpanded = ref(false);
const longDescription = computed(() => props.description.length > 500 || props.description.split('\n').length > 6);
const viewerId = ref<number | null>(null), actionError = ref(''), downloading = ref<string | null>(null);
const availableFiles = computed(() => props.context?.files.filter(file => file.available && file.id !== null) || []);
let disposed = false;
onBeforeUnmount(() => { disposed = true; });
const key = (file: OrderRequestFile) => String(file.id ?? file.legacy_key);
const safeUrl = (value?: string | null) => {
  if (!value) return null;
  if (/^\/manager\/mail\?emailId=-\d+$/.test(value)) return value;
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; } catch { return null; }
};
const download = async (file: OrderRequestFile) => {
  if (downloading.value) return;
  downloading.value = key(file); actionError.value = '';
  try {
    const access = await props.resolveAccess(file as ServiceAttachmentItem, true);
    if (disposed) return;
    const anchor = document.createElement('a'); anchor.href = access.url; anchor.download = file.filename;
    anchor.rel = 'noopener noreferrer'; anchor.referrerPolicy = 'no-referrer';
    document.body.append(anchor); anchor.click(); anchor.remove();
  } catch (reason) { if (!disposed) actionError.value = reason instanceof Error ? reason.message : 'Не удалось скачать оригинал.'; }
  finally { if (!disposed) downloading.value = null; }
};
defineExpose({ focus: () => closeButton.value?.focus({ preventScroll: true }) });
</script>

<template>
  <section id="order-request-details" aria-label="Заявка и файлы" class="w-full min-w-0 shrink-0 self-start overflow-hidden rounded-xl border border-brand-300 bg-white shadow-sm dark:border-brand-700 dark:bg-slate-900" @keydown.esc.stop.prevent="$emit('close')">
    <header class="flex items-center gap-2 border-b border-brand-200 bg-brand-50 px-4 py-3 dark:border-brand-800 dark:bg-brand-950">
      <h2 class="min-w-0 flex-1 text-base font-bold">Заявка и файлы</h2>
      <button ref="closeButton" type="button" aria-label="Закрыть заявку и файлы" class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-brand-200 bg-white text-xl text-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 dark:bg-slate-800 dark:text-brand-200" @click="$emit('close')">×</button>
    </header>
    <div class="space-y-5 p-4 text-sm leading-6 lg:max-h-[calc(100dvh-19rem)] lg:overflow-y-auto">
      <p v-if="loading" role="status" class="text-slate-600 dark:text-slate-300">Загружаем исходную заявку и список файлов…</p>
      <div v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-red-800 dark:bg-red-950 dark:text-red-200"><p class="break-words">{{ error }}</p><button type="button" class="mt-2 min-h-10 font-semibold underline" @click="$emit('retry')">Повторить загрузку</button></div>
      <section class="min-w-0">
        <h3 class="font-bold">Рабочее описание заказа</h3>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Комментарий менеджера; может отличаться от исходной заявки.</p>
        <p :class="longDescription && !descriptionExpanded ? 'line-clamp-4 lg:line-clamp-6' : ''" class="mt-2 whitespace-pre-wrap break-words [overflow-wrap:anywhere] text-slate-700 dark:text-slate-200">{{ description.trim() || 'Рабочее описание не заполнено.' }}</p>
        <button v-if="longDescription" type="button" class="mt-2 min-h-10 font-semibold text-brand-800 underline dark:text-brand-200" :aria-expanded="descriptionExpanded" @click="descriptionExpanded = !descriptionExpanded">{{ descriptionExpanded ? 'Свернуть описание' : 'Читать полностью' }}</button>
      </section>
      <template v-if="context">
        <div>
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2"><h3 class="font-bold">Файлы заявки и заказа · {{ context.files.length }}</h3><button type="button" class="min-h-9 font-semibold text-brand-800 underline dark:text-brand-200" @click="$emit('retry')">Обновить</button></div>
          <p v-if="!context.files.length" class="text-slate-600 dark:text-slate-300">Сохранённых файлов нет.</p>
          <ul v-else class="space-y-3">
            <li v-for="file in context.files" :key="key(file)" class="min-w-0 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <p class="break-words font-semibold [overflow-wrap:anywhere]" data-testid="request-filename">{{ file.filename }}</p>
              <p class="mt-1 break-words text-xs text-slate-600 dark:text-slate-300">{{ file.origin_label }} · {{ file.mime_type }} · {{ formatAttachmentSize(file.size_bytes) || 'Размер неизвестен' }}</p>
              <p v-if="!file.available" class="mt-2 break-words text-amber-800 dark:text-amber-200">Недоступен: {{ file.processing_error || 'Оригинал ожидает восстановления.' }}</p>
              <div v-else class="mt-2 flex flex-wrap gap-2">
                <button type="button" class="min-h-10 rounded-lg bg-brand-700 px-3 font-semibold text-white hover:bg-brand-800" @click="viewerId = file.id ?? null">Открыть</button>
                <button type="button" class="min-h-10 rounded-lg border border-brand-300 px-3 font-semibold text-brand-800 dark:text-brand-200" :disabled="Boolean(downloading)" @click="download(file)">{{ downloading === key(file) ? 'Скачиваем…' : 'Скачать' }}</button>
              </div>
            </li>
          </ul>
          <p v-if="actionError" role="alert" class="mt-2 break-words text-red-700 dark:text-red-200">{{ actionError }} Нажмите «Скачать», чтобы повторить.</p>
          <p class="mt-2 text-xs text-slate-500 dark:text-slate-400">Исходящие КП и счета — во вкладке «Документы».</p>
        </div>
        <p v-for="warning in context.warnings" :key="warning" class="break-words rounded-lg bg-amber-50 p-3 text-amber-900 dark:bg-amber-950 dark:text-amber-200">{{ warning }}</p>
        <section v-for="(source, index) in context.sources" :key="index" class="min-w-0">
          <h3 class="break-words font-bold">{{ source.label }}</h3>
          <p v-if="source.text" class="mt-2 whitespace-pre-wrap break-words [overflow-wrap:anywhere] text-slate-700 dark:text-slate-200">{{ source.text }}</p>
          <p v-else class="mt-2 text-slate-500">Текст источника отсутствует. Проверьте файлы.</p>
          <p v-if="source.truncated" class="mt-2 text-amber-800 dark:text-amber-200">Сохранён только фрагмент текста.</p>
          <a v-if="safeUrl(source.url)" :href="safeUrl(source.url)!" target="_blank" rel="noopener noreferrer" class="mt-2 inline-block min-h-10 font-semibold text-brand-800 underline dark:text-brand-200">{{ source.url?.startsWith('/manager/mail') ? 'Открыть исходное письмо' : 'Открыть тендер' }} ↗</a>
        </section>
      </template>

    </div>
    <ServiceAttachmentViewer v-model="viewerId" :items="availableFiles as ServiceAttachmentItem[]" :resolve-access="resolveAccess" />
  </section>
</template>
