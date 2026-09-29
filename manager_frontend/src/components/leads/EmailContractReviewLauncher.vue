<script setup lang="ts">
import { ref } from 'vue';
import { serviceAttachmentsApi } from '../service-attachments/api';
import EmailContractReview from './EmailContractReview.vue';

type Candidate = { key: string; filename: string; attachmentId?: number; originalPosition?: number };
const props = defineProps<{ orderId: number }>();
const opened = ref(false);
const busy = ref(false);
const error = ref('');
const candidates = ref<Candidate[]>([]);
const selected = ref<Candidate | null>(null);

const start = async () => {
  if (busy.value) return;
  if (opened.value) {
    opened.value = false;
    return;
  }
  opened.value = true;
  busy.value = true;
  error.value = '';
  try {
    const stored = (await serviceAttachmentsApi.list(props.orderId)).items
      .filter((item) => item.source === 'email_lead_intake' && item.id !== null && /\.(pdf|docx?)$/i.test(item.filename))
      .map((item) => ({ key: `stored-${item.id}`, filename: item.filename, attachmentId: item.id! }));
    if (stored.length) {
      candidates.value = stored;
    } else {
      candidates.value = (await serviceAttachmentsApi.listEmailOriginals(props.orderId)).items
        .filter((item) => /\.(pdf|docx?)$/i.test(item.filename))
        .map((item) => ({ key: `original-${item.position}`, filename: item.filename, originalPosition: item.position }));
    }
    if (candidates.value.length === 1) selected.value = candidates.value[0]!;
    if (!candidates.value.length) error.value = 'Договор PDF, DOC или DOCX во вложениях не найден';
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Не удалось открыть вложения письма';
  } finally {
    busy.value = false;
  }
};
</script>

<template>
  <div class="mx-4 mb-3 text-xs">
    <button type="button" class="font-semibold text-brand-700 underline disabled:opacity-50 dark:text-brand-300" :disabled="busy" :aria-expanded="opened" @click="start">
      {{ busy ? 'Открываем договор…' : opened ? 'Скрыть разбор договора' : 'Проверить договор через AI' }}
    </button>
    <p class="mt-1 text-slate-500 dark:text-slate-400">При проверке текст договора будет передан DeepSeek.</p>
    <p v-if="opened && error" class="mt-2 text-red-700 dark:text-red-300" role="alert">{{ error }}</p>
    <div v-if="opened && candidates.length > 1" class="mt-2 flex flex-wrap gap-2" aria-label="Выберите договор">
      <button v-for="candidate in candidates" :key="candidate.key" type="button" class="rounded-lg border border-slate-300 px-2 py-1.5 text-slate-700 dark:border-slate-600 dark:text-slate-200" @click="selected = candidate">{{ candidate.filename }}</button>
    </div>
    <EmailContractReview
      v-if="opened && selected"
      :key="selected.key"
      :order-id="orderId"
      :attachment-id="selected.attachmentId"
      :original-position="selected.originalPosition"
      :auto-start="true"
    />
  </div>
</template>
