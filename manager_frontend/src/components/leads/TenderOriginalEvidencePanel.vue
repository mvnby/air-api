<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { ManagerOrdersService, type CancelablePromise, type ManagerTenderEvidenceJob } from '../../client';
import TenderEvidenceReport from './TenderEvidenceReport.vue';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{
  orderId: number;
  documentIds: string[];
  disabled: boolean;
  downloading: boolean;
}>();
const emit = defineEmits<{ download: [documentId: string] }>();
const job = ref<ManagerTenderEvidenceJob | null>(null);
const waiting = ref(false);
const error = ref('');
const report = computed(() => job.value?.report);
const progress = computed(() => job.value?.status === 'analyzing'
  ? 'Сверяем требования с прочитанным текстом…'
  : job.value ? `Проверяем оригиналы (${job.value.processed} из ${job.value.total})…` : 'Запускаем проверку…');

let version = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let pending: CancelablePromise<ManagerTenderEvidenceJob> | undefined;

function reset() {
  version++;
  clearTimeout(timer);
  pending?.cancel();
  pending = undefined;
  waiting.value = false;
  error.value = '';
  job.value = null;
}

async function check() {
  if (waiting.value || props.disabled || !props.documentIds.length || props.documentIds.length > 8) return;
  reset();
  waiting.value = true;
  const activeVersion = version;
  const orderId = props.orderId;
  const documentIds = [...props.documentIds];
  const deadline = Date.now() + 145_000;

  async function update(request: CancelablePromise<ManagerTenderEvidenceJob>) {
    pending = request;
    try {
      const snapshot = await request;
      if (activeVersion !== version) return;
      job.value = snapshot;
      if (snapshot.status === 'reading' || snapshot.status === 'analyzing') {
        if (Date.now() >= deadline) throw new Error('Ответ о проверке задерживается. Повторите запрос.');
        timer = setTimeout(() => {
          if (activeVersion === version) {
            void update(ManagerOrdersService.getManagerOrderSourceEvidenceJob(orderId, snapshot.job_id));
          }
        }, 2_500);
        return;
      }
      waiting.value = false;
      error.value = snapshot.error || '';
    } catch (reason) {
      if (activeVersion !== version) return;
      waiting.value = false;
      error.value = getApiErrorMessage(reason);
    } finally {
      if (pending === request) pending = undefined;
    }
  }

  await update(ManagerOrdersService.startManagerOrderSourceEvidenceJob(orderId, { document_ids: documentIds }));
}

watch(() => [props.orderId, ...props.documentIds], reset, { flush: 'sync' });
onBeforeUnmount(reset);
</script>

<template>
  <div class="mt-3 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
    <button
      type="button"
      class="btn-mini-outline text-xs"
      :disabled="disabled || waiting || !documentIds.length || documentIds.length > 8"
      @click="check"
    >
      {{ report ? 'Обновить проверку' : 'Проверить полноту и цитаты' }}
    </button>
    <p v-if="waiting" role="status" class="mt-2 text-xs text-slate-500">{{ progress }}</p>
    <p v-if="error" role="alert" class="mt-2 text-xs text-red-700">{{ error }}</p>
    <TenderEvidenceReport
      v-if="report" :report="report" can-download :downloading="downloading"
      @download="emit('download', $event)"
    />
  </div>
</template>
