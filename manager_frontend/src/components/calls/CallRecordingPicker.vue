<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useDialogA11y } from '../../composables/useDialogA11y';
import { callRecordingsApi as api, minskDateTime, type CallDriveFile, type CallDriveFilesQuery } from '../../services/call-recordings-api';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ open: boolean; folderName: string }>();
const emit = defineEmits<{ close: []; select: [file: CallDriveFile] }>();
const dialogRef = ref<HTMLElement | null>(null);
const searchRef = ref<HTMLInputElement | null>(null);
const mode = ref<'day' | 'range' | 'all'>('day');
const dateFrom = ref(minskDateTime(new Date().toISOString()).slice(0, 10));
const dateTo = ref(dateFrom.value);
const query = ref('');
const items = ref<CallDriveFile[]>([]);
const nextPage = ref<string | null>(null);
const chosen = ref<CallDriveFile | null>(null);
const loading = ref(false);
const error = ref('');
const searched = ref(false);
let activeQuery: CallDriveFilesQuery = {};
let requestVersion = 0;
const close = () => emit('close');
useDialogA11y({ open: computed(() => props.open), dialogRef, initialFocusRef: searchRef, close });

async function search(more = false) {
  if (loading.value) return;
  if (!more && mode.value === 'range' && dateFrom.value && dateTo.value && dateFrom.value > dateTo.value) {
    error.value = 'Дата начала должна быть не позже даты окончания.';
    return;
  }
  const version = ++requestVersion;
  if (!more) {
    activeQuery = { ...(mode.value !== 'all' && dateFrom.value ? { date_from: dateFrom.value } : {}), ...(mode.value !== 'all' && (mode.value === 'day' ? dateFrom.value : dateTo.value) ? { date_to: mode.value === 'day' ? dateFrom.value : dateTo.value } : {}), ...(query.value.trim() ? { query: query.value.trim() } : {}) };
    items.value = []; chosen.value = null; nextPage.value = null; searched.value = false;
  }
  loading.value = true; error.value = '';
  try {
    const result = await api.driveFiles({ ...activeQuery, ...(more && nextPage.value ? { page_token: nextPage.value } : {}) });
    if (version !== requestVersion || !props.open) return;
    const previous = more ? items.value : [];
    items.value = [...new Map([...previous, ...result.items].map(item => [item.file_id, item])).values()].sort((a, b) => (b.call_occurred_at ? Date.parse(b.call_occurred_at) : -Infinity) - (a.call_occurred_at ? Date.parse(a.call_occurred_at) : -Infinity));
    nextPage.value = result.next_page_token ?? null; searched.value = true;
  } catch (caught) {
    if (version === requestVersion && props.open) error.value = getApiErrorMessage(caught) || 'Не удалось получить записи из папки. Попробуйте ещё раз.';
  } finally {
    if (version === requestVersion) loading.value = false;
  }
}
watch([mode, dateFrom, dateTo, query], () => { requestVersion++; loading.value = false; items.value = []; chosen.value = null; nextPage.value = null; searched.value = false; error.value = ''; });
watch(() => props.open, (open) => {
  if (open) { loading.value = false; void search(); }
  else { requestVersion++; loading.value = false; }
}, { immediate: true });
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="picker fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/50 p-0 sm:items-center sm:p-5" @click.self="close">
      <section ref="dialogRef" role="dialog" aria-modal="true" aria-labelledby="call-picker-title" tabindex="-1" class="flex max-h-[94dvh] w-full max-w-3xl flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-2xl outline-none sm:rounded-2xl dark:border-slate-700 dark:bg-slate-900" data-testid="call-recording-picker">
        <header class="flex items-start justify-between gap-3 border-b border-slate-100 p-4 sm:p-5 dark:border-slate-800">
          <div class="min-w-0"><h2 id="call-picker-title" class="text-lg font-semibold">Выбрать запись</h2><p class="mt-1 break-words text-xs text-slate-500 dark:text-slate-400">{{ folderName }} · Даты и время по Минску</p></div>
          <button class="picker-button shrink-0" aria-label="Закрыть выбор записи" @click="close">Закрыть</button>
        </header>
        <form class="space-y-3 border-b border-slate-100 p-4 sm:p-5 dark:border-slate-800" @submit.prevent="search()">
          <label class="picker-label">Имя контакта или номер<input ref="searchRef" v-model="query" class="picker-input" aria-label="Имя контакта или номер" placeholder="Например, Алексей или +375…" maxlength="100" :disabled="loading" /></label>
          <div class="grid grid-cols-2 gap-3 sm:grid-cols-[120px_1fr_1fr_auto] sm:items-end">
            <label class="picker-label">Дата<select v-model="mode" aria-label="Режим выбора даты" class="picker-input" :disabled="loading"><option value="day">Один день</option><option value="range">Период</option><option value="all">За всё время</option></select></label>
            <label v-if="mode !== 'all'" class="picker-label">{{ mode === 'day' ? 'День звонка' : 'С даты' }}<input v-model="dateFrom" type="date" aria-label="Дата начала" class="picker-input" :disabled="loading" /></label>
            <label v-if="mode === 'range'" class="picker-label">По дату<input v-model="dateTo" type="date" aria-label="Дата окончания" class="picker-input" :disabled="loading" /></label>
            <p v-else class="hidden text-xs leading-5 text-slate-400 sm:block" :class="mode === 'all' ? 'sm:col-span-2' : ''">{{ mode === 'all' ? 'Поиск по всем датам, включая неизвестные.' : 'Чтобы искать без даты, выберите «За всё время».' }}</p>
            <button class="picker-button picker-primary self-end" :disabled="loading" data-testid="search-drive-recordings">Найти</button>
          </div>
          <p class="text-xs text-slate-500 dark:text-slate-400">Дата определяется из имени записи. Режим «За всё время» включает файлы с неизвестной датой. Просмотр не запускает обработку.</p>
        </form>
        <div class="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5" :aria-busy="loading">
          <p v-if="error" role="alert" class="mb-3 rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{{ error }}</p>
          <p v-if="loading && !items.length" role="status" class="py-10 text-center text-sm text-slate-500 dark:text-slate-400">Ищем записи в папке…</p>
          <div v-else-if="searched && !items.length && !nextPage" class="py-10 text-center"><p class="text-sm font-medium">Записи не найдены</p><p class="mt-2 text-xs text-slate-500 dark:text-slate-400">Измените день, расширьте период или уточните имя и номер.</p></div>
          <p v-if="searched && !items.length && nextPage" class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">В просмотренной части папки совпадений нет. Продолжите поиск в остальных файлах.</p>
          <div v-if="items.length" class="space-y-2" role="group" aria-label="Файлы в папке">
            <button v-for="file in items" :key="file.file_id" type="button" class="flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-colors" :class="chosen?.file_id === file.file_id ? 'border-brand-300 bg-brand-50 dark:border-brand-700 dark:bg-brand-950/60' : 'border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800'" :aria-pressed="chosen?.file_id === file.file_id" :disabled="loading" data-testid="drive-file-option" @click="chosen = file">
              <span class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs" :class="chosen?.file_id === file.file_id ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 dark:border-slate-600'" aria-hidden="true">{{ chosen?.file_id === file.file_id ? '✓' : '' }}</span>
              <span class="min-w-0"><span class="block break-words text-sm font-medium">{{ file.contact || file.phone || file.filename }}</span><span class="mt-1 block text-xs text-slate-500 dark:text-slate-400">{{ file.phone || 'Телефон не подтверждён' }} · {{ file.call_occurred_at ? minskDateTime(file.call_occurred_at).replace('T', ' ') + ' · Минск' : 'Дата звонка неизвестна' }}</span><span v-if="file.contact || file.phone" class="mt-1 block break-words text-xs text-slate-400">{{ file.filename }}</span></span>
            </button>
          </div>
          <button v-if="nextPage" class="picker-button mt-3 w-full" :disabled="loading" data-testid="more-drive-recordings" @click="search(true)">{{ loading ? 'Загружаем…' : items.length ? 'Показать ещё' : 'Продолжить поиск' }}</button>
          <button v-else-if="error && !items.length" class="picker-button" :disabled="loading" @click="search()">Повторить поиск</button>
        </div>
        <footer class="flex flex-col gap-3 border-t border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5 dark:border-slate-800"><p class="min-w-0 break-words text-xs text-slate-500 dark:text-slate-400">{{ chosen ? 'Выбрана одна запись. Проверку запустите на следующем шаге.' : 'Выберите одну запись из списка.' }}</p><button class="picker-button picker-primary shrink-0" :disabled="!chosen || loading" data-testid="select-drive-recording" @click="chosen && emit('select', chosen)">Выбрать запись</button></footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.picker { @apply text-slate-900 dark:text-slate-100; }
.picker:is(.dark *) { color-scheme: dark; }
.picker-label { @apply block min-w-0 text-xs font-medium text-slate-600 dark:text-slate-300; }
.picker-input { @apply mt-1 block w-full min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-normal text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100; }
.picker-button { @apply rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800; }
.picker-primary { @apply border-brand-600 bg-brand-600 text-white hover:bg-brand-700 dark:border-brand-500 dark:bg-brand-600 dark:text-white dark:hover:bg-brand-500; }
</style>
