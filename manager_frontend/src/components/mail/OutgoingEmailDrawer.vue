<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { AlertTriangle, CheckCircle2, Clock3, Copy, RefreshCw, XCircle } from 'lucide-vue-next';
import { ManagerMailService } from '../../client';
import type { OutgoingEmailDetailResponse, OutgoingEmailResponse } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{
  modelValue: boolean;
  emailId?: number | null;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  retry: [email: OutgoingEmailResponse];
  toast: [payload: { message: string; type?: 'success' | 'error' }];
}>();

const email = ref<OutgoingEmailDetailResponse | null>(null);
const loading = ref(false);
const retrying = ref(false);
const error = ref('');
const showBody = ref(true);
const showHtml = ref(false);
const showAttempts = ref(true);

const statusLabel = (value?: string | null) => {
  switch (value) {
    case 'sent':
      return 'Отправлено';
    case 'failed':
      return 'Ошибка';
    case 'pending':
      return 'В очереди';
    default:
      return value || 'Неизвестно';
  }
};

const statusClass = (value?: string | null) => {
  switch (value) {
    case 'sent':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300';
    case 'failed':
      return 'border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300';
    case 'pending':
      return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300';
    default:
      return 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';
  }
};

const statusIcon = computed(() => {
  if (email.value?.status === 'sent') return CheckCircle2;
  if (email.value?.status === 'failed') return XCircle;
  if (email.value?.status === 'pending') return Clock3;
  return AlertTriangle;
});

const formatDate = (value?: string | null) => {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
};

const formatSize = (value?: number | null) => {
  const size = Number(value || 0);
  if (!size) return '—';
  if (size < 1024) return `${size} Б`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} КБ`;
  return `${(size / 1024 / 1024).toFixed(1)} МБ`;
};

const attempts = computed(() => email.value?.retry_attempts || []);
const hasAttachments = computed(() => Boolean(email.value?.attachments?.length));

const copyText = async (text: string, message = 'Скопировано') => {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.left = '-9999px';
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    document.body.removeChild(area);
  }
  emit('toast', { message });
};

const loadEmail = async () => {
  if (!props.modelValue || !props.emailId) return;
  loading.value = true;
  error.value = '';
  try {
    email.value = await ManagerMailService.getManagerOutgoingEmail(props.emailId);
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    loading.value = false;
  }
};

const retryEmail = async () => {
  if (!email.value || email.value.status !== 'failed') return;
  retrying.value = true;
  error.value = '';
  try {
    const result = await ManagerMailService.retryManagerOutgoingEmail(email.value.id);
    emit('retry', result);
    emit('toast', {
      message: result.status === 'sent'
        ? 'Повторная отправка выполнена'
        : `Повторная отправка завершилась ошибкой: ${result.error || 'см. историю'}`,
      type: result.status === 'sent' ? 'success' : 'error',
    });
    await loadEmail();
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    retrying.value = false;
  }
};

const close = () => emit('update:modelValue', false);

watch(
  () => [props.modelValue, props.emailId] as const,
  () => {
    if (props.modelValue) void loadEmail();
  },
  { immediate: true },
);
</script>

<template>
  <teleport to="body">
    <div v-if="modelValue" class="fixed inset-0 z-[110] flex justify-end bg-slate-950/45 backdrop-blur-sm">
      <button class="hidden flex-1 cursor-default md:block" type="button" aria-label="Закрыть" @click="close" />
      <aside class="flex h-full w-full max-w-2xl flex-col overflow-hidden bg-white text-slate-900 shadow-2xl dark:bg-slate-950 dark:text-slate-100">
        <header class="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div class="min-w-0">
            <p class="text-xs font-bold uppercase tracking-[0.18em] text-teal-700 dark:text-teal-300">Исходящее письмо</p>
            <h2 class="mt-1 truncate text-xl font-bold">{{ email?.subject || 'Письмо' }}</h2>
            <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">ID #{{ emailId || email?.id }}</p>
          </div>
          <button type="button" class="rounded-xl p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800" @click="close">
            <span class="material-icons-round text-[22px]">close</span>
          </button>
        </header>

        <div class="flex-1 overflow-y-auto px-5 py-4">
          <div v-if="loading" class="rounded-2xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">
            Загружаю письмо...
          </div>
          <div v-else-if="error" class="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
            {{ error }}
          </div>

          <div v-else-if="email" class="space-y-4">
            <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div class="flex flex-wrap items-center gap-2">
                <span class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-bold" :class="statusClass(email.status)">
                  <component :is="statusIcon" class="h-4 w-4" />
                  {{ statusLabel(email.status) }}
                </span>
                <span v-if="email.order_id" class="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  Заказ #{{ email.order_id }}
                </span>
                <span v-if="email.customer_name" class="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  {{ email.customer_name }}
                </span>
              </div>

              <dl class="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt class="text-xs font-bold uppercase tracking-wide text-slate-400">From</dt>
                  <dd class="mt-1 break-all font-medium">{{ [email.from_name, email.from_email].filter(Boolean).join(' · ') || '—' }}</dd>
                </div>
                <div>
                  <dt class="text-xs font-bold uppercase tracking-wide text-slate-400">To</dt>
                  <dd class="mt-1 break-all font-medium">{{ email.recipient_email }}</dd>
                </div>
                <div>
                  <dt class="text-xs font-bold uppercase tracking-wide text-slate-400">Reply-To</dt>
                  <dd class="mt-1 break-all font-medium">{{ email.reply_to || '—' }}</dd>
                </div>
                <div>
                  <dt class="text-xs font-bold uppercase tracking-wide text-slate-400">Создано / отправлено</dt>
                  <dd class="mt-1 font-medium">{{ formatDate(email.created_at) }} / {{ formatDate(email.sent_at) }}</dd>
                </div>
              </dl>
            </section>

            <section v-if="email.error" class="rounded-2xl border border-red-200 bg-red-50 p-4 dark:border-red-500/30 dark:bg-red-500/10">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <p class="text-xs font-bold uppercase tracking-wide text-red-600 dark:text-red-300">Ошибка отправки</p>
                  <p class="mt-2 whitespace-pre-wrap break-words text-sm font-medium text-red-800 dark:text-red-100">{{ email.error }}</p>
                </div>
                <button type="button" class="inline-flex shrink-0 items-center gap-1 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 dark:border-red-500/30 dark:bg-red-950/30 dark:text-red-200" @click="copyText(email.error || '', 'Ошибка скопирована')">
                  <Copy class="h-3.5 w-3.5" />
                  Копировать
                </button>
              </div>
            </section>

            <section class="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
              <button type="button" class="flex w-full items-center justify-between px-4 py-3 text-left font-semibold" @click="showBody = !showBody">
                <span>Текст письма</span>
                <span class="material-icons-round text-[20px]">{{ showBody ? 'expand_less' : 'expand_more' }}</span>
              </button>
              <pre v-if="showBody" class="max-h-72 overflow-auto border-t border-slate-100 whitespace-pre-wrap break-words px-4 py-3 text-sm leading-6 text-slate-700 dark:border-slate-800 dark:text-slate-200">{{ email.body_text || 'Текстовая версия не сохранена' }}</pre>
            </section>

            <section v-if="email.body_html" class="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
              <button type="button" class="flex w-full items-center justify-between px-4 py-3 text-left font-semibold" @click="showHtml = !showHtml">
                <span>HTML-версия</span>
                <span class="material-icons-round text-[20px]">{{ showHtml ? 'expand_less' : 'expand_more' }}</span>
              </button>
              <div v-if="showHtml" class="border-t border-slate-100 p-3 dark:border-slate-800">
                <iframe class="h-72 w-full rounded-xl border border-slate-200 bg-white dark:border-slate-700" sandbox="" :srcdoc="email.body_html || ''" />
              </div>
            </section>

            <section class="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
              <p class="text-sm font-bold">Вложения</p>
              <div v-if="hasAttachments" class="mt-3 space-y-2">
                <div v-for="(attachment, index) in email.attachments || []" :key="`${attachment.filename}-${index}`" class="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-950">
                  <div class="min-w-0">
                    <p class="truncate text-sm font-semibold">{{ attachment.filename || `Вложение ${index + 1}` }}</p>
                    <p class="text-xs text-slate-500">{{ attachment.mime_type || 'тип не указан' }} · {{ formatSize(attachment.size) }}</p>
                  </div>
                  <button type="button" class="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-400 dark:border-slate-700" disabled :title="attachment.storage_key ? 'Endpoint скачивания будет добавлен в snapshot-фазе' : 'Snapshot PDF еще не сохраняется'">
                    Открыть PDF
                  </button>
                </div>
              </div>
              <p v-else class="mt-2 text-sm text-slate-500 dark:text-slate-400">Вложений нет.</p>
            </section>

            <section class="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
              <button type="button" class="flex w-full items-center justify-between px-4 py-3 text-left font-semibold" @click="showAttempts = !showAttempts">
                <span>Попытки отправки</span>
                <span class="material-icons-round text-[20px]">{{ showAttempts ? 'expand_less' : 'expand_more' }}</span>
              </button>
              <div v-if="showAttempts" class="space-y-2 border-t border-slate-100 p-4 dark:border-slate-800">
                <div v-for="attempt in attempts" :key="attempt.id" class="rounded-xl border border-slate-200 p-3 text-sm dark:border-slate-800">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="font-bold">#{{ attempt.id }}</span>
                    <span class="rounded-full border px-2 py-0.5 text-xs font-bold" :class="statusClass(attempt.status)">{{ statusLabel(attempt.status) }}</span>
                    <span class="text-slate-500">{{ formatDate(attempt.created_at) }}</span>
                  </div>
                  <p v-if="attempt.error" class="mt-2 break-words text-xs font-medium text-red-600 dark:text-red-300">{{ attempt.error }}</p>
                </div>
              </div>
            </section>
          </div>
        </div>

        <footer class="flex flex-col-reverse gap-2 border-t border-slate-200 px-5 py-4 sm:flex-row sm:justify-end dark:border-slate-800">
          <button type="button" class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800" @click="close">
            Закрыть
          </button>
          <button
            v-if="email?.status === 'failed'"
            type="button"
            class="inline-flex items-center justify-center gap-2 rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-teal-700 disabled:opacity-60"
            :disabled="retrying"
            @click="retryEmail"
          >
            <RefreshCw class="h-4 w-4" :class="retrying ? 'animate-spin' : ''" />
            {{ retrying ? 'Повторяю...' : 'Повторить отправку' }}
          </button>
        </footer>
      </aside>
    </div>
  </teleport>
</template>
