<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue';
import { ManagerMailService, type EmailLeadImportJobResponse, type EmailLeadImportResponse } from '../../client';

const emit = defineEmits<{
  (e: 'imported', created: number): void;
  (e: 'notice', message: string): void;
}>();

const LOOKBACK_DAYS = 14;
const importing = ref(false);
const job = ref<EmailLeadImportJobResponse | null>(null);
const result = ref<EmailLeadImportResponse | null>(null);
const statusError = ref('');
let disposed = false;

const dateTime = (value: string | null | undefined) => {
  if (!value || Number.isNaN(new Date(value).getTime())) return '';
  return new Date(value).toLocaleString('ru-RU');
};

const errorMessage = (error: unknown) => error instanceof Error && error.message
  ? error.message
  : 'неизвестная ошибка';

const showCompletedJob = (completedJob: EmailLeadImportJobResponse) => {
  result.value = completedJob.result || null;
  if (completedJob.status === 'failed') {
    emit('notice', `Не удалось проверить почту${completedJob.error ? `: ${completedJob.error}` : ''}`);
    return;
  }
  const created = completedJob.result?.created || 0;
  if (completedJob.result) {
    emit('notice', `Почта проверена: обработано ${completedJob.result.processed || 0}, новых обращений ${created}.`);
    if (created) emit('imported', created);
    return;
  }
  emit('notice', completedJob.message || 'Проверка почты завершена.');
};

const pollStatus = async () => {
  for (let attempt = 0; attempt < 60 && !disposed; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 3000));
    if (disposed) return;
    try {
      const currentJob = await ManagerMailService.getManagerEmailLeadImportStatus();
      if (disposed) return;
      job.value = currentJob;
      if (currentJob.status !== 'running') {
        showCompletedJob(currentJob);
        return;
      }
    } catch (error) {
      if (!disposed) {
        statusError.value = `Не удалось узнать статус проверки: ${errorMessage(error)}`;
        emit('notice', statusError.value);
      }
      return;
    }
  }
  if (!disposed) emit('notice', 'Проверка почты ещё выполняется в фоне.');
};

const importEmailLeads = async () => {
  importing.value = true;
  job.value = null;
  result.value = null;
  statusError.value = '';
  try {
    const startedJob = await ManagerMailService.importManagerEmailLeads(false, LOOKBACK_DAYS);
    if (disposed) return;
    job.value = startedJob;
    if (startedJob.status === 'running' || startedJob.already_running) {
      emit('notice', startedJob.already_running ? 'Почта уже проверяется, жду результат.' : 'Проверка почты запущена.');
      await pollStatus();
    } else {
      showCompletedJob(startedJob);
    }
  } catch (error) {
    if (!disposed) emit('notice', `Не удалось проверить почту: ${errorMessage(error)}`);
  } finally {
    if (!disposed) importing.value = false;
  }
};

onBeforeUnmount(() => { disposed = true; });
</script>

<template>
  <section class="mb-5 flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
    <div>
      <p class="text-sm font-semibold text-slate-800 dark:text-white">Почта</p>
      <p class="mt-1 text-sm text-slate-600 dark:text-slate-300">Проверить новые письма за последние 14 дней.</p>
      <p v-if="job?.status === 'running' && !statusError" class="mt-2 text-xs text-slate-500 dark:text-slate-400">
        {{ job.message || 'Проверка почты выполняется.' }}
        <span v-if="dateTime(job.started_at)"> Начата: {{ dateTime(job.started_at) }}.</span>
      </p>
      <p v-if="statusError" class="mt-2 text-xs text-red-700 dark:text-red-300" role="alert">{{ statusError }}</p>
      <p v-else-if="job?.status === 'failed'" class="mt-2 text-xs text-red-700 dark:text-red-300" role="alert">
        {{ job.error || job.message || 'Проверка почты завершилась с ошибкой.' }}
      </p>
      <p v-if="result" class="mt-2 text-xs text-slate-500 dark:text-slate-400">
        Обработано: {{ result.processed || 0 }} · Новых обращений: {{ result.created || 0 }} · Повторов: {{ result.duplicates || 0 }}
      </p>
    </div>
    <button
      type="button"
      class="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-700 disabled:opacity-60"
      :disabled="importing"
      @click="importEmailLeads"
    >
      <span class="material-icons-round text-[18px]" :class="{ 'animate-spin': importing }">{{ importing ? 'refresh' : 'mark_email_read' }}</span>
      {{ importing ? 'Проверяем…' : 'Проверить почту' }}
    </button>
    <details v-if="result" class="basis-full rounded-lg border border-slate-200 dark:border-slate-700">
      <summary class="cursor-pointer px-3 py-2 text-sm font-semibold text-slate-700 dark:text-slate-200">Результаты проверки</summary>
      <div class="border-t border-slate-200 px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:text-slate-300">
        <p>
          Обработано: {{ result.processed || 0 }} · Кандидатов: {{ result.candidates || 0 }} · Проверено: {{ result.ai_checked || 0 }} · Создано: {{ result.created || 0 }} · Повторы: {{ result.duplicates || 0 }} · Отклонено: {{ result.rejected || 0 }} · Ошибки: {{ result.failed || 0 }}
        </p>
        <p v-if="dateTime(result.scanned_since)" class="mt-1">Проверка писем с {{ dateTime(result.scanned_since) }}.</p>
        <div v-if="result.decisions?.length" class="mt-3 overflow-hidden rounded border border-slate-200 dark:border-slate-700">
          <div
            v-for="(decision, index) in result.decisions"
            :key="`${decision.sender_email}-${decision.subject}-${decision.status}-${index}`"
            class="grid gap-1 border-b border-slate-100 px-2 py-2 last:border-b-0 dark:border-slate-700 sm:grid-cols-[100px_minmax(0,1fr)_minmax(0,2fr)]"
          >
            <span class="font-semibold">{{ decision.status === 'rejected' ? 'Отклонено' : decision.status === 'would_create' ? 'Кандидат' : decision.status === 'created' ? 'Создано' : decision.status === 'duplicate' ? 'Повтор' : decision.status === 'filtered' ? 'Пропущено' : 'Ошибка' }}</span>
            <span class="min-w-0 truncate">{{ decision.subject || 'Без темы' }}</span>
            <span class="min-w-0 break-words text-slate-500 dark:text-slate-400">{{ decision.reason === 'keyword_filter' ? 'Не прошло первичный отбор' : decision.reason || decision.sender_email }}</span>
          </div>
        </div>
      </div>
    </details>
  </section>
</template>
