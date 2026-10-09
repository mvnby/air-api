<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import CallRecordingPicker from '../components/calls/CallRecordingPicker.vue';
import CallProposalCard from '../components/calls/CallProposalCard.vue';
import type { CallAdoptPayload, CallDriveStatus, CallRecordingResponse } from '../client';
import { callRecordingsApi as api, callStateLabel, callStageLabel, callErrorLabel, driveId, minskDateTime, minskIso, callProviderLabel, type CallDriveFile, type CallTranscriptionProvider } from '../services/call-recordings-api';
import { getApiErrorMessage } from '../utils/api-errors';
import { useDemoReadOnly } from '../services/manager-demo';

const status = ref<CallDriveStatus | null>(null);
const recordings = ref<CallRecordingResponse[]>([]);
const selected = ref<CallRecordingResponse | null>(null);
const folder = ref('');
const transcriptionProvider = ref<CallTranscriptionProvider>('groq');
const pilotFile = ref('');
const pickerOpen = ref(false);
const pickedFile = ref<CallDriveFile | null>(null);
function pickFile(file: CallDriveFile) { pickedFile.value = file; pilotFile.value = ''; pickerOpen.value = false; }
const sourceTime = ref('');
const sourcePhone = ref('');
const busy = ref(false);
const error = ref('');
const notice = ref('');
const offset = ref(0);
const total = ref(0);
const readOnly = useDemoReadOnly();
const canProcess = computed(() => status.value?.pipeline_enabled && status.value.connected && status.value.folder_id && !readOnly.value);
const selectedProviderReady = computed(() => transcriptionProvider.value === 'google_batch' ? status.value?.google_batch_configured : transcriptionProvider.value === 'soniox' ? status.value?.soniox_configured : status.value?.groq_configured);
const canRetry = computed(() => selected.value && !['call_google_wait_expired', 'call_soniox_submission_uncertain', 'call_soniox_wait_expired', 'call_soniox_operation_failed', 'call_soniox_invalid_audio'].includes(selected.value.last_error_code || '') && ['failed', 'reconnect_required', 'manual_review'].includes(selected.value.state));
async function action(operation: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true; error.value = ''; notice.value = '';
  try { await operation(); } catch (caught) { error.value = getApiErrorMessage(caught) || 'Не удалось выполнить действие'; }
  finally { busy.value = false; }
}
async function load() {
  const [connection, list] = await Promise.all([api.status(), api.list(offset.value)]);
  status.value = connection; recordings.value = list.items; total.value = list.total;
  transcriptionProvider.value = connection.transcription_provider || 'groq';
  if (!folder.value) folder.value = connection.folder_url || '';
  if (selected.value) await openRecording(selected.value.id);
}
async function openRecording(id: number) {
  selected.value = await api.get(id);
  sourceTime.value = minskDateTime(selected.value.call_occurred_at);
  sourcePhone.value = selected.value.phone || '';
}
async function connect() { await action(async () => { const value = await api.authorize(); window.open(value.url, '_blank', 'noopener'); notice.value = 'Завершите подключение Google и обновите эту страницу.'; }); }
async function saveFolder() { await action(async () => { const id = driveId(folder.value); if (!id) throw new Error('Вставьте ссылку на папку Google Диска'); status.value = await api.folder(id, status.value?.auto_poll_enabled ?? false, transcriptionProvider.value); notice.value = 'Папка и способ распознавания сохранены.'; }); }
async function toggleAuto(event: Event) { const enabled = (event.target as HTMLInputElement).checked; await action(async () => { status.value = await api.folder(status.value!.folder_id!, enabled, transcriptionProvider.value); }); }
async function poll(fileId?: string) { await action(async () => { const id = fileId || (pilotFile.value ? driveId(pilotFile.value) : null); if (!fileId && pilotFile.value && !id) throw new Error('Вставьте ссылку на запись Google Диска'); const result = await api.poll(id); await load(); notice.value = `Проверено: ${result.observed}. В очереди: ${result.queued}. Для готовности файла нужны две проверки с интервалом не менее минуты.`; }); }
async function retry() { await action(async () => { selected.value = await api.retry(selected.value!.id, selected.value!.version); await load(); }); }
async function saveMetadata() { await action(async () => { selected.value = await api.metadata(selected.value!.id, selected.value!.version, minskIso(sourceTime.value), sourcePhone.value.trim() || null); notice.value = 'Исходные данные сохранены. Повторите незавершённый этап, чтобы обновить предложения.'; }); }
async function adopt(proposalId: number, payload: CallAdoptPayload) { await action(async () => { await api.adopt(selected.value!.id, proposalId, payload); await load(); notice.value = 'Выбранное действие сохранено.'; }); }
onMounted(() => action(load));
</script>

<template>
  <main class="call-page mx-auto max-w-7xl space-y-5 p-4 sm:p-6" :aria-busy="busy">
    <header class="space-y-3">
      <a href="/manager/settings" class="call-link text-slate-500 dark:text-slate-400">← Настройки</a>
      <div class="flex items-start justify-between gap-3"><div class="min-w-0"><h1 class="text-2xl font-semibold tracking-tight sm:text-3xl">Записи звонков</h1><p class="mt-1 text-sm text-slate-500 dark:text-slate-400">Личные записи, расшифровки и действия по разговору.</p></div><button class="call-button shrink-0" :disabled="busy" @click="action(load)">{{ busy ? 'Обновляем…' : 'Обновить' }}</button></div>
      <div v-if="status" class="flex flex-wrap gap-2"><span class="call-badge bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300">Только вам в текущей компании</span><span class="call-badge bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">{{ status.auto_poll_enabled ? 'Автопроверка включена' : 'Автопроверка выключена' }}</span></div>
    </header>
    <p v-if="error" role="alert" class="call-message bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300">{{ error }}</p>
    <p v-if="notice" role="status" class="call-message bg-brand-50 text-brand-800 dark:bg-brand-950 dark:text-brand-200">{{ notice }}</p>
    <div v-if="busy && !status" role="status" class="call-panel py-12 text-center text-sm text-slate-500 dark:text-slate-400">Загружаем подключение и записи…</div>
    <template v-if="status">
      <section class="call-panel !p-0" data-testid="call-setup">
        <details :open="!status.connected || !status.folder_id">
          <summary class="cursor-pointer px-4 py-4 sm:px-5"><span class="font-semibold">Google Диск и распознавание</span><span class="mt-1 block text-sm text-slate-500 dark:text-slate-400">{{ status.connected ? (status.account_label || 'Google Диск подключён') : 'Подключите папку с записями' }}<span v-if="status.connected && status.folder_id"> · {{ status.folder_name || 'Папка выбрана' }}</span></span></summary>
          <div class="space-y-4 border-t border-slate-100 px-4 py-4 sm:px-5 dark:border-slate-800">
            <p v-if="!status.pipeline_enabled" class="call-message bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">Обработка записей выключена на сервере. Подключение само по себе не запускает обработку.</p>
            <div class="grid gap-4 lg:grid-cols-2">
              <div class="space-y-3">
                <div class="flex flex-wrap gap-2"><button class="call-button" :disabled="busy || readOnly" @click="connect">{{ status.connected ? 'Переподключить Google' : 'Подключить Google' }}</button><button v-if="status.connected" class="call-button" :disabled="busy || readOnly" @click="action(async () => { status = await api.disconnect(); })">Отключить</button></div>
                <form v-if="status.connected" class="space-y-2" @submit.prevent="saveFolder"><label class="call-label">Папка записей<input v-model="folder" class="call-input" aria-label="Папка записей" placeholder="Ссылка на папку Google Диска" /></label><div class="flex flex-wrap items-center gap-3"><button :disabled="busy || readOnly" class="call-button">Сохранить папку</button><a v-if="status.folder_url" :href="status.folder_url" target="_blank" rel="noopener" class="call-link">{{ status.folder_name || 'Открыть папку' }} ↗</a></div></form>
              </div>
              <div class="space-y-2"><label class="call-label">Распознавание речи<select v-model="transcriptionProvider" class="call-input" aria-label="Провайдер распознавания"><option value="google_batch">Google — отложенная обработка</option><option value="groq">Groq — Whisper</option><option value="soniox">Soniox — отложенная обработка</option></select></label><p class="text-sm" :class="selectedProviderReady ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'">{{ selectedProviderReady ? 'Выбранный провайдер настроен.' : 'Выбранный провайдер не настроен на сервере.' }}</p><p class="call-help">{{ transcriptionProvider === 'google_batch' ? 'Результат может появиться в течение 24 часов.' : transcriptionProvider === 'soniox' ? 'Запись отправляется в Soniox, а результат появляется после завершения обработки.' : 'Используется Whisper через Groq.' }} Выбор сохраняется вместе с папкой.</p></div>
            </div>
            <div class="rounded-xl bg-slate-50 p-3 dark:bg-slate-950/60"><label class="flex cursor-pointer items-start gap-3 text-sm font-medium"><input type="checkbox" class="mt-0.5 h-4 w-4 accent-brand-600" :checked="status.auto_poll_enabled" :disabled="busy || !canProcess" @change="toggleAuto" /><span>Автоматически проверять выбранную папку<span class="mt-1 block text-xs font-normal leading-relaxed text-slate-500 dark:text-slate-400">Включение запускает распознавание новых записей. Проверьте, что в папке нет личных разговоров, которые вы не хотите разбирать.</span></span></label><p class="call-help mt-3">До {{ status.max_files_per_poll }} файлов за проверку и {{ status.max_recordings_per_day }} новых записей в сутки. До {{ (status.max_bytes ?? 10485760) / 1024 / 1024 }} МБ и {{ (status.max_duration_seconds ?? 600) / 60 }} минут на запись; до {{ status.max_stage_attempts }} попыток этапа.</p></div>
            <p v-if="status.last_error_code" class="text-sm text-amber-700 dark:text-amber-300">Подключение требует проверки: {{ callErrorLabel(status.last_error_code) }}</p>
          </div>
        </details>
      </section>
      <section class="call-panel space-y-3">
        <div><h2 class="font-semibold">Ручная проверка</h2><p class="call-help mt-1">Найдите нужный разговор в подключённой папке по дате, имени или номеру.</p></div>
        <div class="flex flex-wrap items-center gap-3"><button class="call-button call-primary" data-testid="choose-drive-recording" :disabled="busy || !status.connected || !status.folder_id" @click="pickerOpen = true">Выбрать запись</button><span v-if="!pickedFile" class="call-help">Просмотр списка не запускает распознавание.</span></div>
        <div v-if="pickedFile" class="flex flex-col gap-3 rounded-xl bg-slate-50 p-3 sm:flex-row sm:items-center sm:justify-between dark:bg-slate-950/60" data-testid="picked-drive-recording"><div class="min-w-0"><p class="break-words text-sm font-medium">{{ pickedFile.contact || pickedFile.phone || pickedFile.filename }}</p><p class="call-help mt-1">{{ pickedFile.phone || 'Телефон не подтверждён' }} · {{ pickedFile.call_occurred_at ? minskDateTime(pickedFile.call_occurred_at).replace('T', ' ') + ' · Минск' : 'Дата звонка неизвестна' }}</p></div><button class="call-button call-primary shrink-0" :disabled="busy || !canProcess" data-testid="start-picked-recording" @click="poll(pickedFile.file_id)">Проверить запись</button></div>
        <details class="text-sm"><summary class="cursor-pointer text-slate-500 dark:text-slate-400">Указать ссылку вручную</summary><form class="mt-3 flex flex-col gap-2 sm:flex-row" @submit.prevent="poll()"><input v-model="pilotFile" aria-label="Тестовая запись" class="call-input min-w-0 flex-1" placeholder="Ссылка на запись Google Диска" /><button :disabled="busy || !canProcess || !pilotFile.trim()" class="call-button shrink-0" data-testid="poll-call-recordings">Проверить запись</button></form></details>
        <p class="call-help">Для готовности файла нужны две проверки с интервалом не менее минуты.</p>
        <p v-if="!canProcess" class="call-help">{{ !status.connected || !status.folder_id ? 'Для проверки подключите Google Диск и выберите папку.' : !status.pipeline_enabled ? 'Проверка станет доступна после включения обработки на сервере.' : 'Проверка недоступна в режиме просмотра.' }}</p>
      </section>
      <CallRecordingPicker :open="pickerOpen" :folder-name="status.folder_name || 'Папка записей'" @close="pickerOpen = false" @select="pickFile" />
    </template>
    <div v-if="status" class="grid items-start gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
      <section class="call-panel !p-0 overflow-hidden" aria-label="Список записей">
        <div class="flex items-center justify-between border-b border-slate-100 p-4 dark:border-slate-800"><h2 class="font-semibold">Записи</h2><span class="call-badge bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300">{{ total }}</span></div>
        <div v-if="!recordings.length" class="space-y-2 p-5 text-sm"><p class="font-medium">Пока нет записей для разбора.</p><p class="call-help">Проверьте файл вручную или включите проверку папки в настройках подключения.</p></div>
        <div v-else class="max-h-[28rem] space-y-2 overflow-y-auto p-2 lg:max-h-[42rem]"><button v-for="item in recordings" :key="item.id" class="w-full rounded-xl border p-3 text-left transition-colors disabled:opacity-60" :class="selected?.id === item.id ? 'border-brand-200 bg-brand-50 dark:border-brand-800 dark:bg-brand-950/60' : 'border-transparent hover:bg-slate-50 dark:hover:bg-slate-800'" :aria-pressed="selected?.id === item.id" :disabled="busy" @click="action(() => openRecording(item.id))"><span class="block break-words text-sm font-medium">{{ item.filename }}</span><span class="mt-2 block text-xs" :class="item.state === 'failed' || item.state === 'reconnect_required' ? 'text-amber-700 dark:text-amber-300' : 'text-slate-500 dark:text-slate-400'">{{ callStateLabel(item.state, item.transcription_provider) }} · {{ callStageLabel(item.stage) }}</span><span class="mt-1 block text-xs text-slate-400">{{ item.call_occurred_at ? minskDateTime(item.call_occurred_at).replace('T', ' ') + ' · Минск' : 'Время не уточнено' }}</span></button></div>
        <div v-if="total > 50" class="flex items-center justify-between gap-3 border-t border-slate-100 p-3 dark:border-slate-800"><button class="call-button" :disabled="busy || offset === 0" @click="action(async () => { offset -= 50; await load(); })">Назад</button><span class="text-xs text-slate-500">{{ offset + 1 }}–{{ Math.min(offset + 50, total) }}</span><button class="call-button" :disabled="busy || offset + 50 >= total" @click="action(async () => { offset += 50; await load(); })">Далее</button></div>
      </section>
      <section v-if="selected" class="min-w-0 space-y-4" data-testid="call-review" aria-label="Разбор записи">
        <div class="call-panel space-y-4">
          <div><p class="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">Разбор записи</p><h2 class="break-words text-lg font-semibold">{{ selected.filename }}</h2><p class="mt-2 text-sm text-brand-700 dark:text-brand-300">{{ callStateLabel(selected.state, selected.transcription_provider) }} · {{ callStageLabel(selected.stage) }}</p></div>
          <p v-if="selected.state === 'waiting_transcription'" class="call-message bg-brand-50 text-brand-800 dark:bg-brand-950 dark:text-brand-200">Запись уже отправлена в {{ selected.transcription_provider === 'soniox' ? 'Soniox' : 'Google' }} на распознавание. Обновите список позже; повторная отправка не требуется.</p>
          <dl class="grid gap-3 rounded-xl bg-slate-50 p-3 text-sm sm:grid-cols-2 dark:bg-slate-950/60"><div><dt class="call-help">Время звонка · Минск</dt><dd class="mt-1">{{ selected.call_occurred_at ? minskDateTime(selected.call_occurred_at).replace('T', ' ') : 'Неизвестно — уточните вручную' }}</dd><dd class="call-help mt-1">{{ selected.time_source === 'samsung_filename' ? 'Из имени записи Samsung.' : selected.time_source === 'manual' ? 'Указано вручную.' : '' }}</dd></div><div><dt class="call-help">Телефон</dt><dd class="mt-1">{{ selected.phone || 'Не подтверждён' }}</dd></div></dl>
          <a :href="selected.source_url" target="_blank" rel="noopener" class="call-link inline-flex">Открыть исходную запись ↗</a>
          <div v-if="selected.last_error_code" class="call-message space-y-3 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200"><p>Не завершён этап «{{ callStageLabel(selected.stage) }}»: {{ callErrorLabel(selected.last_error_code) }}. Успешные этапы сохраняются.</p><button v-if="canRetry" :disabled="busy || !canProcess" class="call-button" @click="retry">Повторить незавершённый этап</button></div>
          <button v-else-if="canRetry" :disabled="busy || !canProcess" class="call-button" @click="retry">Повторить незавершённый этап</button>
          <details class="border-t border-slate-100 pt-3 dark:border-slate-800"><summary class="cursor-pointer text-sm font-medium">Уточнить исходные данные</summary><form class="mt-3 space-y-3" @submit.prevent="saveMetadata"><div class="grid gap-3 sm:grid-cols-2"><label class="call-label">Дата и время звонка (Минск)<input v-model="sourceTime" type="datetime-local" class="call-input" /></label><label class="call-label">Подтверждённый телефон<input v-model="sourcePhone" class="call-input" placeholder="Неизвестен" /></label></div><button class="call-button" :disabled="busy || readOnly || ['queued', 'processing'].includes(selected.state)">Сохранить исходные данные</button></form></details>
          <details v-if="selected.transcription_provider || selected.transcription_model" class="text-xs text-slate-500 dark:text-slate-400"><summary class="cursor-pointer">Сведения о распознавании</summary><p class="mt-2">Распознавание этой записи: {{ callProviderLabel(selected.transcription_provider) }}<span v-if="selected.transcription_model"> · {{ selected.transcription_model }}</span></p></details>
        </div>
        <div v-if="selected.structure" class="call-panel space-y-3"><h3 class="font-semibold">Предварительный разбор</h3><p class="whitespace-pre-wrap break-words text-sm leading-6">{{ selected.structure.summary }}</p><ul v-if="Array.isArray(selected.structure.conditions)" class="list-disc space-y-1 pl-5 text-sm leading-6"><li v-for="condition in selected.structure.conditions" :key="String(condition)">{{ condition }}</li></ul></div>
        <div v-if="selected.proposals?.length" class="space-y-1 px-1"><h3 class="font-semibold">Предлагаемые действия</h3><p class="call-help">Проверьте и при необходимости исправьте каждое действие. Сохраняется только выбранное действие.</p></div>
        <CallProposalCard v-for="proposal in selected.proposals" :key="`${selected.id}:${selected.version}:${proposal.id}`" :proposal="proposal" :version="selected.version" :disabled="busy || readOnly || selected.state !== 'ready_for_review'" @adopt="adopt" />
        <details v-if="selected.transcript" class="call-panel" open><summary class="cursor-pointer font-semibold">Расшифровка</summary><p class="mt-4 max-h-[32rem] overflow-y-auto whitespace-pre-wrap break-words text-sm leading-7">{{ selected.transcript }}</p></details>
      </section>
      <section v-else class="call-panel flex min-h-[240px] flex-col items-center justify-center text-center" data-testid="call-selection-empty"><div class="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950 dark:text-brand-300" aria-hidden="true">↗</div><h2 class="font-semibold">Выберите запись</h2><p class="call-help mt-2 max-w-sm">Здесь появятся исходные данные, расшифровка и действия, которые можно проверить и сохранить.</p></section>
    </div>
  </main>
</template>
<style scoped>
.call-page { @apply text-slate-900 dark:text-slate-100; }
.call-page:is(.dark *) { color-scheme: dark; }
.call-panel { @apply rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 dark:border-slate-800 dark:bg-slate-900; }
.call-button { @apply rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800; }
.call-primary { @apply border-brand-600 bg-brand-600 text-white hover:bg-brand-700 dark:border-brand-500 dark:bg-brand-600 dark:text-white dark:hover:bg-brand-500; }
.call-input { @apply mt-1 block w-full min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100; }
.call-label { @apply block text-sm font-medium text-slate-600 dark:text-slate-300; }
.call-help { @apply text-xs leading-relaxed text-slate-500 dark:text-slate-400; }
.call-link { @apply text-sm font-medium text-brand-600 hover:underline dark:text-brand-400; }
.call-message { @apply rounded-xl p-3 text-sm leading-relaxed; }
.call-badge { @apply rounded-full px-2.5 py-1 text-xs font-medium; }
</style>
