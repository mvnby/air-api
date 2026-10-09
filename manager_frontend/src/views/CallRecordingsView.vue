<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import CallProposalCard from '../components/calls/CallProposalCard.vue';
import type { CallAdoptPayload, CallDriveStatus, CallRecordingResponse } from '../client';
import { callRecordingsApi as api, callStateLabel, callStageLabel, callErrorLabel, driveId, minskDateTime, minskIso } from '../services/call-recordings-api';
import { getApiErrorMessage } from '../utils/api-errors';
import { useDemoReadOnly } from '../services/manager-demo';

const status = ref<CallDriveStatus | null>(null);
const recordings = ref<CallRecordingResponse[]>([]);
const selected = ref<CallRecordingResponse | null>(null);
const folder = ref('');
const pilotFile = ref('');
const sourceTime = ref('');
const sourcePhone = ref('');
const busy = ref(false);
const error = ref('');
const notice = ref('');
const offset = ref(0);
const total = ref(0);
const readOnly = useDemoReadOnly();
const canProcess = computed(() => status.value?.pipeline_enabled && status.value.connected && status.value.folder_id && !readOnly.value);
const canRetry = computed(() => selected.value && ['failed', 'reconnect_required', 'manual_review'].includes(selected.value.state));
async function action(operation: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true; error.value = ''; notice.value = '';
  try { await operation(); } catch (caught) { error.value = getApiErrorMessage(caught) || 'Не удалось выполнить действие'; }
  finally { busy.value = false; }
}
async function load() {
  const [connection, list] = await Promise.all([api.status(), api.list(offset.value)]);
  status.value = connection; recordings.value = list.items; total.value = list.total;
  if (!folder.value) folder.value = connection.folder_url || '';
  if (selected.value) await openRecording(selected.value.id);
}
async function openRecording(id: number) {
  selected.value = await api.get(id);
  sourceTime.value = minskDateTime(selected.value.call_occurred_at);
  sourcePhone.value = selected.value.phone || '';
}
async function connect() { await action(async () => { const value = await api.authorize(); window.open(value.url, '_blank', 'noopener'); notice.value = 'Завершите подключение Google и обновите эту страницу.'; }); }
async function saveFolder() { await action(async () => { const id = driveId(folder.value); if (!id) throw new Error('Вставьте ссылку на папку Google Диска'); status.value = await api.folder(id, false); notice.value = 'Папка сохранена. Автоматическая проверка выключена.'; }); }
async function toggleAuto(event: Event) { const enabled = (event.target as HTMLInputElement).checked; await action(async () => { status.value = await api.folder(status.value!.folder_id!, enabled); }); }
async function poll() { await action(async () => { const id = pilotFile.value ? driveId(pilotFile.value) : null; if (pilotFile.value && !id) throw new Error('Вставьте ссылку на запись Google Диска'); const result = await api.poll(id); await load(); notice.value = `Проверено: ${result.observed}. В очереди: ${result.queued}. Для готовности файла нужны две проверки с интервалом не менее минуты.`; }); }
async function retry() { await action(async () => { selected.value = await api.retry(selected.value!.id, selected.value!.version); await load(); }); }
async function saveMetadata() { await action(async () => { selected.value = await api.metadata(selected.value!.id, selected.value!.version, minskIso(sourceTime.value), sourcePhone.value.trim() || null); notice.value = 'Исходные данные сохранены. Повторите незавершённый этап, чтобы обновить предложения.'; }); }
async function adopt(proposalId: number, payload: CallAdoptPayload) { await action(async () => { await api.adopt(selected.value!.id, proposalId, payload); await load(); notice.value = 'Выбранное действие сохранено.'; }); }
onMounted(() => action(load));
</script>

<template>
  <div class="mx-auto max-w-6xl p-4 sm:p-6 space-y-6">
    <div class="flex justify-between gap-4"><div><h1 class="text-2xl font-semibold">Записи звонков</h1><p class="text-gray-500">Ваши записи, расшифровки и предлагаемые действия доступны только вам в текущей компании.</p></div><button class="border rounded px-3 py-2" :disabled="busy" @click="action(load)">Обновить</button></div>
    <p v-if="error" role="alert" class="rounded bg-red-50 text-red-700 p-3">{{ error }}</p>
    <p v-if="notice" role="status" class="rounded bg-blue-50 text-blue-800 p-3">{{ notice }}</p>
    <section v-if="status" class="rounded-xl border p-4 space-y-3" data-testid="call-setup">
      <h2 class="font-semibold">Личный Google Диск</h2>
      <p>{{ status.connected ? `Подключён: ${status.account_label || 'Google Диск'}` : 'Подключение для записей отсутствует' }}</p>
      <p v-if="!status.pipeline_enabled" class="text-amber-700">Обработка записей выключена на сервере. Подключение само по себе не запускает обработку.</p>
      <p v-if="!status.transcription_configured" class="text-amber-700">Распознавание речи требует настройки на сервере.</p>
      <div class="flex gap-3"><button class="border rounded px-3 py-2" :disabled="busy || readOnly" @click="connect">{{ status.connected ? 'Переподключить Google' : 'Подключить Google' }}</button><button v-if="status.connected" class="border rounded px-3 py-2" :disabled="busy || readOnly" @click="action(async () => { status = await api.disconnect(); })">Отключить</button></div>
      <form v-if="status.connected" class="flex flex-wrap gap-2" @submit.prevent="saveFolder"><input v-model="folder" class="border rounded p-2 flex-1" aria-label="Папка записей" placeholder="Ссылка на выбранную папку Google Диска" /><button :disabled="busy || readOnly" class="border rounded px-3 py-2">Сохранить папку</button></form>
      <a v-if="status.folder_url" :href="status.folder_url" target="_blank" rel="noopener" class="text-blue-600">{{ status.folder_name || 'Открыть папку' }}</a>
      <label class="block"><input type="checkbox" :checked="status.auto_poll_enabled" :disabled="busy || !canProcess" @change="toggleAuto" /> Автоматически проверять выбранную папку</label>
      <p class="text-sm text-gray-500">Включение запускает распознавание новых записей из этой папки: до {{ status.max_files_per_poll }} файлов за проверку, до {{ status.max_recordings_per_day }} новых записей в сутки. До {{ (status.max_bytes ?? 10485760) / 1024 / 1024 }} МБ и {{ (status.max_duration_seconds ?? 600) / 60 }} минут на запись; до {{ status.max_stage_attempts }} попыток этапа. Проверьте, что в папке нет личных разговоров, которые вы не хотите разбирать.</p>
      <form class="flex flex-wrap gap-2" @submit.prevent="poll"><input v-model="pilotFile" aria-label="Тестовая запись" class="border rounded p-2 flex-1" placeholder="Ссылка на одну тестовую запись (пусто — проверить папку)" /><button :disabled="busy || !canProcess" class="border rounded px-3 py-2" data-testid="poll-call-recordings">Проверить записи</button></form>
      <p v-if="status.last_error_code" class="text-amber-700">Подключение требует проверки: {{ callErrorLabel(status.last_error_code) }}</p>
    </section>
    <div class="grid gap-5 lg:grid-cols-[320px_1fr]">
      <section class="space-y-2"><h2 class="font-semibold">Записи ({{ total }})</h2><p v-if="!recordings.length">Пока нет записей для разбора.</p>
        <button v-for="item in recordings" :key="item.id" class="block w-full rounded-lg border p-3 text-left" :class="{ 'border-blue-500': selected?.id === item.id }" :disabled="busy" @click="action(() => openRecording(item.id))"><span class="block break-words">{{ item.filename }}</span><span class="text-sm text-gray-500">{{ callStateLabel(item.state) }} · {{ callStageLabel(item.stage) }}</span></button>
        <div class="flex gap-3"><button :disabled="busy || offset === 0" @click="action(async () => { offset -= 50; await load(); })">Назад</button><button :disabled="busy || offset + 50 >= total" @click="action(async () => { offset += 50; await load(); })">Далее</button></div>
      </section>
      <section v-if="selected" class="space-y-4" data-testid="call-review">
        <div class="rounded-xl border p-4 space-y-3"><h2 class="font-semibold break-words">{{ selected.filename }}</h2><p>{{ callStateLabel(selected.state) }} · {{ callStageLabel(selected.stage) }}</p><a :href="selected.source_url" target="_blank" rel="noopener" class="text-blue-600">Открыть исходную запись</a><p class="text-sm text-gray-500">Время звонка: {{ selected.call_occurred_at ? minskDateTime(selected.call_occurred_at).replace('T', ' ') + ' (Минск)' : 'Неизвестно — уточните вручную' }}. {{ selected.time_source === 'samsung_filename' ? 'Из имени записи Samsung.' : selected.time_source === 'manual' ? 'Указано вручную.' : '' }} Телефон: {{ selected.phone || 'не подтверждён' }}.</p>
          <p v-if="selected.last_error_code" class="text-amber-700">Не завершён этап «{{ callStageLabel(selected.stage) }}»: {{ callErrorLabel(selected.last_error_code) }}. Успешные этапы сохраняются.</p>
          <button v-if="canRetry" :disabled="busy || !canProcess" class="border rounded px-3 py-2" @click="retry">Повторить незавершённый этап</button>
          <details><summary>Уточнить исходные данные</summary><form class="mt-3 space-y-2" @submit.prevent="saveMetadata"><label class="block">Дата и время звонка (Минск)<input v-model="sourceTime" type="datetime-local" class="border rounded p-2" /></label><label class="block">Подтверждённый телефон<input v-model="sourcePhone" class="border rounded p-2" /></label><button class="border rounded px-3 py-2" :disabled="busy || readOnly || ['queued', 'processing'].includes(selected.state)">Сохранить исходные данные</button></form></details>
        </div>
        <div v-if="selected.transcript" class="rounded-xl border p-4"><h3 class="font-semibold">Расшифровка</h3><p class="whitespace-pre-wrap mt-2">{{ selected.transcript }}</p></div>
        <div v-if="selected.structure" class="rounded-xl border p-4"><h3 class="font-semibold">Предварительный разбор</h3><p>{{ selected.structure.summary }}</p><ul v-if="Array.isArray(selected.structure.conditions)"><li v-for="condition in selected.structure.conditions" :key="String(condition)">{{ condition }}</li></ul></div>
        <p v-if="selected.proposals?.length" class="text-sm text-gray-500">Проверьте и при необходимости исправьте каждое действие. Сохраняется только выбранное действие.</p>
        <CallProposalCard v-for="proposal in selected.proposals" :key="`${selected.id}:${selected.version}:${proposal.id}`" :proposal="proposal" :version="selected.version" :disabled="busy || readOnly || selected.state !== 'ready_for_review'" @adopt="adopt" />
      </section>
    </div>
  </div>
</template>
