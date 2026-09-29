<script setup lang="ts">
import { ref } from 'vue';
import { serviceAttachmentsApi } from '../service-attachments/api';
import { formatAttachmentSize, type OriginalEmailAttachmentItem } from '../service-attachments/types';
import EmailContractReview from './EmailContractReview.vue';

const props = defineProps<{ orderId: number }>();
const opened = ref(false);
const busy = ref(false);
const error = ref('');
const items = ref<OriginalEmailAttachmentItem[]>([]);

const open = async () => {
  opened.value = !opened.value;
  if (!opened.value || items.value.length) return;
  busy.value = true;
  error.value = '';
  try {
    items.value = (await serviceAttachmentsApi.listEmailOriginals(props.orderId)).items;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Не удалось открыть письмо';
  } finally {
    busy.value = false;
  }
};

const download = async (item: OriginalEmailAttachmentItem) => {
  error.value = '';
  try {
    await serviceAttachmentsApi.downloadEmailOriginal(props.orderId, item.position, item.filename);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Не удалось скачать вложение';
  }
};
</script>

<template>
  <div class="mx-4 mb-3 text-xs">
    <button type="button" class="font-semibold text-brand-700 underline dark:text-brand-300" :aria-expanded="opened" @click="open">
      {{ opened ? 'Скрыть оригиналы письма' : 'Открыть оригиналы письма' }}
    </button>
    <div v-if="opened" class="mt-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-900/40">
      <p v-if="busy">Загружаем письмо…</p>
      <p v-if="error" class="text-red-700 dark:text-red-300" role="alert">{{ error }}</p>
      <p v-if="!busy && !error && !items.length">Вложений в оригинале письма не найдено.</p>
      <div v-for="item in items" :key="item.position" class="border-t border-slate-200 py-2 first:border-t-0 dark:border-slate-700">
        <p class="font-semibold text-slate-800 dark:text-slate-200">{{ item.filename }} · {{ formatAttachmentSize(item.size_bytes) }}</p>
        <button type="button" class="mt-1 font-semibold text-brand-700 underline dark:text-brand-300" @click="download(item)">Скачать оригинал</button>
        <EmailContractReview v-if="/\.(pdf|docx?)$/i.test(item.filename)" :order-id="orderId" :original-position="item.position" />
      </div>
    </div>
  </div>
</template>
