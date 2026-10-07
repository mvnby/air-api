<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { Loader2 } from 'lucide-vue-next';

import {
  incomingApi,
  newIncomingIdempotencyKey,
  type IncomingCreatePayload,
  type IncomingResponse,
  type IncomingUpdatePayload,
} from '../../services/incoming-api';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ leadId?: number | null }>();
const emit = defineEmits<{
  close: [];
  saved: [incoming: IncomingResponse];
}>();

const requestText = ref('');
const name = ref('');
const phone = ref('');
const email = ref('');
const address = ref('');
const region = ref('');
const requestedTime = ref('');
const callBeforeVisit = ref<boolean | null>(null);
const originalRequestedTime = ref('');
const requestedAt = ref<string | null>(null);
const requestedDatePrecision = ref<'date' | 'datetime' | null>(null);
const recordedNow = ref(false);
const sourceOccurredAt = ref<string | null>(null);
const version = ref<number | null>(null);
const intakeState = ref<IncomingResponse['intake_state'] | null>(null);
const missingFields = ref<string[]>([]);
const loading = ref(Boolean(props.leadId));
const saving = ref(false);
const error = ref('');
const versionConflict = ref(false);
const mutationKey = ref(newIncomingIdempotencyKey());
const failedSignature = ref<string | null>(null);
const missingFieldNames: Record<string, string> = { name: 'Имя', phone: 'Телефон', email: 'Email', address_text: 'Адрес', region_text: 'Регион', requested_time_text: 'Желаемое время' };
const visibleMissingFields = computed(() => missingFields.value.map(field => missingFieldNames[field] || field));
const intakeLabel = computed(() => {
  if (intakeState.value === 'ready_for_review') return 'Готово к проверке';
  if (visibleMissingFields.value.includes('Адрес') || visibleMissingFields.value.includes('Регион')) return 'Нужно уточнить адрес';
  if (intakeState.value === 'needs_contact') return 'Нужен контакт';
  return 'Нужно уточнить детали';
});

const optional = (value: string): string | null => value.trim() || null;
const createPayload = computed<IncomingCreatePayload>(() => ({
  request_text: requestText.value,
  name: optional(name.value),
  phone: optional(phone.value),
  email: optional(email.value),
  address_text: optional(address.value),
  region_text: optional(region.value),
  requested_time_text: optional(requestedTime.value),
  call_before_visit: callBeforeVisit.value,
  requested_at: requestedAt.value,
  source_occurred_at: sourceOccurredAt.value,
  source_timezone: 'Europe/Minsk',
}));
const updatePayload = computed<IncomingUpdatePayload>(() => {
  const wishedTime = optional(requestedTime.value);
  return {
    request_text: requestText.value,
    name: optional(name.value),
    phone: optional(phone.value),
    email: optional(email.value),
    address_text: optional(address.value),
    region_text: optional(region.value),
    requested_time_text: wishedTime,
    call_before_visit: callBeforeVisit.value,
    ...(wishedTime === null || requestedTime.value === originalRequestedTime.value
      ? { requested_at: requestedAt.value }
      : {}),
    expected_version: version.value || 1,
  };
});
const commandSignature = computed(() => JSON.stringify(
  props.leadId ? updatePayload.value : createPayload.value,
));

watch(commandSignature, (signature) => {
  if (failedSignature.value !== null && signature !== failedSignature.value) {
    mutationKey.value = newIncomingIdempotencyKey();
    failedSignature.value = null;
  }
}, { flush: 'sync' });

watch(recordedNow, (checked) => {
  if (props.leadId) return;
  sourceOccurredAt.value = checked ? new Date().toISOString() : null;
});

watch(requestedTime, (value) => {
  if (value !== originalRequestedTime.value) {
    requestedAt.value = null;
    requestedDatePrecision.value = null;
  }
});

const fill = (incoming: IncomingResponse) => {
  requestText.value = incoming.request_text;
  name.value = incoming.name || '';
  phone.value = incoming.phone || '';
  email.value = incoming.email || '';
  address.value = incoming.address_text || '';
  region.value = incoming.region_text || '';
  callBeforeVisit.value = incoming.call_before_visit ?? null;
  originalRequestedTime.value = incoming.requested_time_text || '';
  requestedTime.value = originalRequestedTime.value;
  requestedAt.value = incoming.requested_at || null;
  requestedDatePrecision.value = incoming.date_precision || null;
  sourceOccurredAt.value = incoming.source_occurred_at || null;
  recordedNow.value = Boolean(incoming.source_occurred_at);
  version.value = incoming.version;
  intakeState.value = incoming.intake_state;
  missingFields.value = incoming.missing_fields;
};

const formatRequestedAt = (value: string): string => new Intl.DateTimeFormat(
  'ru-BY',
  requestedDatePrecision.value === 'date'
    ? { timeZone: 'Europe/Minsk', dateStyle: 'medium' }
    : { timeZone: 'Europe/Minsk', dateStyle: 'medium', timeStyle: 'short' },
).format(new Date(value));

onMounted(async () => {
  if (!props.leadId) return;
  try { fill(await incomingApi.get(props.leadId)); }
  catch (caught) { error.value = getApiErrorMessage(caught); }
  finally { loading.value = false; }
});

const submit = async () => {
  if (!requestText.value.trim() || saving.value || loading.value) return;
  saving.value = true;
  error.value = '';
  versionConflict.value = false;
  const signature = commandSignature.value;
  try {
    const saved = props.leadId
      ? await incomingApi.update(props.leadId, updatePayload.value, mutationKey.value)
      : await incomingApi.create(createPayload.value, mutationKey.value);
    emit('saved', saved);
  } catch (caught) {
    failedSignature.value = signature;
    versionConflict.value = Boolean(
      props.leadId && typeof caught === 'object' && caught !== null
      && 'status' in caught && caught.status === 409,
    );
    error.value = getApiErrorMessage(caught);
  } finally {
    saving.value = false;
  }
};

const reloadActual = async () => {
  if (!props.leadId || loading.value) return;
  loading.value = true;
  try {
    failedSignature.value = null;
    fill(await incomingApi.get(props.leadId));
    mutationKey.value = newIncomingIdempotencyKey();
    versionConflict.value = false;
    error.value = '';
  } catch (caught) {
    error.value = getApiErrorMessage(caught);
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <section class="max-h-[calc(100vh-2rem)] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl dark:bg-slate-800" data-testid="quick-incoming-capture">
    <header class="mb-4 flex items-start justify-between gap-3">
      <div>
        <h2 class="text-lg font-bold text-slate-900 dark:text-white">{{ leadId ? `Исправить входящее #${leadId}` : 'Быстро записать входящее' }}</h2>
        <p class="mt-1 text-sm text-slate-500 dark:text-slate-300">Достаточно исходного текста. Контакты можно добавить позже.</p>
      </div>
      <button type="button" class="rounded-lg px-2 py-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700" aria-label="Закрыть" @click="emit('close')">✕</button>
    </header>

    <div v-if="loading" class="flex justify-center py-10 text-slate-500" role="status"><Loader2 class="h-5 w-5 animate-spin" />Загружаем…</div>
    <form v-else class="grid gap-3" @submit.prevent="submit">
      <div v-if="leadId && intakeState" class="flex flex-wrap gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:bg-slate-900 dark:text-slate-300" data-testid="incoming-intake-state"><strong class="text-slate-800 dark:text-white">{{ intakeLabel }}</strong><span v-if="visibleMissingFields.length">Не указано: {{ visibleMissingFields.join(', ') }}</span></div>
      <label>
        <span class="mb-1 block text-sm font-semibold text-slate-700 dark:text-slate-200">Текст обращения *</span>
        <textarea v-model="requestText" data-testid="incoming-request-text" required maxlength="12000" rows="5" placeholder="Вставьте или запишите запрос клиента как есть" class="w-full rounded-xl border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-900" />
      </label>

      <label v-if="!leadId" class="flex items-start gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700 dark:bg-slate-900 dark:text-slate-200">
        <input v-model="recordedNow" data-testid="incoming-recorded-now" type="checkbox" class="mt-0.5" />
        <span><strong>Текст записан сейчас</strong><small class="block text-slate-500">Не включайте для старой переписки или текста без точного времени.</small></span>
      </label>
      <p v-if="!leadId && !recordedNow" class="text-xs text-slate-500" data-testid="incoming-time-unknown">Время исходного обращения: неизвестно</p>

      <details class="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
        <summary class="cursor-pointer text-sm font-semibold text-slate-700 dark:text-slate-200">Контакты и детали</summary>
        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <label><span class="mb-1 block text-xs text-slate-500">Имя</span><input v-model="name" data-testid="incoming-name" maxlength="200" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-900" /></label>
          <label><span class="mb-1 block text-xs text-slate-500">Телефон</span><input v-model="phone" data-testid="incoming-phone" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-900" /></label>
          <label><span class="mb-1 block text-xs text-slate-500">Email</span><input v-model="email" type="email" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-900" /></label>
          <label><span class="mb-1 block text-xs text-slate-500">Регион</span><input v-model="region" maxlength="300" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-900" /></label>
          <label class="sm:col-span-2"><span class="mb-1 block text-xs text-slate-500">Адрес</span><input v-model="address" maxlength="500" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-900" /></label>
          <label class="sm:col-span-2"><span class="mb-1 block text-xs text-slate-500">Желаемое время словами</span><input v-model="requestedTime" data-testid="incoming-requested-time" maxlength="300" placeholder="Например: в пятницу после 16:00" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-900" /></label>
          <label class="sm:col-span-2"><input v-model="callBeforeVisit" type="checkbox" data-testid="incoming-call-before-visit" /> Созвониться перед выездом</label>
          <div v-if="requestedAt" class="sm:col-span-2 flex items-center gap-2 text-xs text-slate-500"><span data-testid="incoming-requested-at">Распознано: {{ formatRequestedAt(requestedAt) }}</span><button type="button" class="underline" @click="requestedAt = null; requestedDatePrecision = null">Сбросить дату</button></div>
        </div>
      </details>

      <p v-if="error" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300" role="alert">{{ error }} <button v-if="versionConflict" type="button" class="ml-2 font-semibold underline" @click="reloadActual">Загрузить актуальную версию</button></p>
      <div class="flex justify-end gap-2">
        <button type="button" class="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold dark:border-slate-600" @click="emit('close')">Отмена</button>
        <button type="submit" data-testid="incoming-save" :disabled="saving || !requestText.trim()" class="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"><Loader2 v-if="saving" class="h-4 w-4 animate-spin" />{{ leadId ? 'Сохранить исправления' : 'Сохранить входящее' }}</button>
      </div>
    </form>
  </section>
</template>
