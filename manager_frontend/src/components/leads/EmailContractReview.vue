<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { serviceAttachmentsApi } from '../service-attachments/api';
import type { ContractReviewResponse } from '../service-attachments/types';

const props = defineProps<{ orderId: number; attachmentId?: number; originalPosition?: number; autoStart?: boolean }>();
const busy = ref(false);
const error = ref('');
const report = ref<ContractReviewResponse | null>(null);
let active = true;
onUnmounted(() => { active = false; });

const review = async () => {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    const started = props.originalPosition === undefined
      ? await serviceAttachmentsApi.reviewEmailContract(props.orderId, props.attachmentId!)
      : await serviceAttachmentsApi.reviewEmailOriginal(props.orderId, props.originalPosition);
    for (let attempt = 0; attempt < 100 && active; attempt += 1) {
      const job = attempt === 0 ? started : await serviceAttachmentsApi.getEmailContractReviewJob(started.job_id);
      if (job.status === 'completed' && job.report) {
        report.value = job.report;
        return;
      }
      if (job.status === 'failed') throw new Error(job.error || 'Не удалось проверить договор');
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    if (active) throw new Error('Проверка заняла слишком много времени; попробуйте ещё раз');
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Не удалось проверить договор';
  } finally {
    busy.value = false;
  }
};
onMounted(() => { if (props.autoStart) void review(); });
</script>

<template>
  <div class="mt-2 text-xs">
    <button type="button" class="font-semibold text-brand-700 underline disabled:opacity-60 dark:text-brand-300" :disabled="busy" @click="review">
      {{ busy ? 'Проверяем договор…' : report ? 'Проверить повторно' : 'Проверить договор через AI' }}
    </button>
    <p class="mt-1 text-slate-500 dark:text-slate-400">По нажатию текст оригинала будет передан DeepSeek. Отчёт доступен до обновления страницы.</p>
    <p v-if="error" class="mt-2 text-red-700 dark:text-red-300" role="alert">{{ error }}</p>
    <div v-if="report" class="mt-3 rounded-lg border border-slate-200 bg-white p-3 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200" role="region" aria-label="Проверка договора">
      <p class="font-semibold">Проверка договора · {{ report.risks.length }} вопросов для согласования</p>
      <p class="mt-1 text-slate-500 dark:text-slate-400">{{ report.note }}</p>
      <p v-if="!report.risks.length" class="mt-2">Подтверждённых цитатами рисков не найдено. Проверьте оригинал вручную.</p>
      <ol v-else class="mt-3 list-decimal space-y-3 pl-4">
        <li v-for="(risk, index) in report.risks" :key="`${risk.clause}-${index}`">
          <p class="font-semibold">{{ risk.topic }}<span v-if="risk.clause"> · {{ risk.clause }}</span><span v-if="risk.page"> · стр. {{ risk.page }}</span></p>
          <blockquote class="mt-1 border-l-2 border-slate-300 pl-2 italic dark:border-slate-600">«{{ risk.quote }}»</blockquote>
          <p class="mt-1">{{ risk.concern }}</p>
          <p class="mt-1 font-medium">Согласовать: {{ risk.proposal }}</p>
        </li>
      </ol>
    </div>
  </div>
</template>
