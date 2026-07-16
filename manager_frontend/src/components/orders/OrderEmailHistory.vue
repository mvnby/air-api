<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { AlertTriangle, CheckCircle2, ChevronDown, Clock3, Copy, ExternalLink, RefreshCw, XCircle } from 'lucide-vue-next';
import { ManagerMailService } from '../../client';
import type { OutgoingEmailResponse } from '../../client';
import OutgoingEmailDrawer from '../mail/OutgoingEmailDrawer.vue';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{
  orderId: number;
  refreshKey?: number;
}>();

const emit = defineEmits<{
  toast: [payload: { message: string; type?: 'success' | 'error' }];
}>();

const emails = ref<OutgoingEmailResponse[]>([]);
const loading = ref(false);
const error = ref('');
const selectedEmailId = ref<number | null>(null);
const drawerOpen = ref(false);
const expanded = ref(false);

const failedCount = computed(() => emails.value.filter((item) => item.status === 'failed').length);

const statusLabel = (value?: string | null) => {
  switch (value) {
    case 'sent':
      return 'Отправлено';
    case 'failed':
      return 'Ошибка';
    case 'pending':
      return 'В очереди';
    default:
      return value || '—';
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

const statusIcon = (value?: string | null) => {
  if (value === 'sent') return CheckCircle2;
  if (value === 'failed') return XCircle;
  if (value === 'pending') return Clock3;
  return AlertTriangle;
};

const formatDate = (value?: string | null) => {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
};

const copyText = async (text: string) => {
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
  emit('toast', { message: 'Ошибка скопирована' });
};

const loadEmails = async () => {
  loading.value = true;
  error.value = '';
  try {
    const response = await ManagerMailService.listManagerOrderOutgoingEmails(props.orderId, 8);
    emails.value = response.items || [];
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    loading.value = false;
  }
};

const openEmail = (email: OutgoingEmailResponse) => {
  selectedEmailId.value = email.id;
  drawerOpen.value = true;
};

const openOutbox = () => {
  window.history.pushState({}, '', `/manager/mail/outbox?orderId=${props.orderId}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

watch(
  () => [props.orderId, props.refreshKey] as const,
  () => {
    void loadEmails();
  },
  { immediate: true },
);
</script>

<template>
  <section class="rounded-2xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-950/40">
    <OutgoingEmailDrawer
      v-model="drawerOpen"
      :email-id="selectedEmailId"
      @retry="loadEmails"
      @toast="emit('toast', $event)"
    />

    <button
      type="button"
      class="flex w-full items-center justify-between gap-3 text-left"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <div class="min-w-0">
        <h4 class="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-white">
          <span class="material-icons-round text-[18px] text-teal-600">outgoing_mail</span>
          Письма
          <span v-if="emails.length" class="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">{{ emails.length }}</span>
          <span v-if="failedCount" class="rounded-full bg-red-100 px-2 py-0.5 text-xs font-bold text-red-700 dark:bg-red-500/10 dark:text-red-300">{{ failedCount }} ошибок</span>
        </h4>
        <p class="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">Что отправлялось клиенту по этому заказу.</p>
      </div>
      <ChevronDown class="h-4 w-4 shrink-0 text-slate-400 transition-transform" :class="expanded ? 'rotate-180' : ''" />
    </button>

    <div v-if="expanded" class="mt-3">
      <div class="flex gap-2">
        <button type="button" class="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800" :disabled="loading" @click="loadEmails">
          <RefreshCw class="h-3.5 w-3.5" :class="loading ? 'animate-spin' : ''" />
          Обновить
        </button>
        <button type="button" class="inline-flex items-center gap-1 rounded-lg border border-teal-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-teal-700 hover:bg-teal-50 dark:border-teal-500/30 dark:bg-slate-900 dark:text-teal-300 dark:hover:bg-teal-500/10" @click="openOutbox">
          <ExternalLink class="h-3.5 w-3.5" />
          Все
        </button>
      </div>

      <div v-if="error" class="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
        {{ error }}
      </div>
      <div v-else-if="loading" class="mt-3 rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">
        Загружаю историю писем...
      </div>
      <div v-else-if="!emails.length" class="mt-3 rounded-xl border border-dashed border-slate-300 px-3 py-4 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
        По заказу пока нет отправленных писем.
      </div>
      <div v-else class="mt-3 space-y-2">
        <article
          v-for="email in emails"
          :key="email.id"
          class="cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2 transition hover:border-teal-200 hover:bg-teal-50/40 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-teal-500/30 dark:hover:bg-teal-500/10"
          @click="openEmail(email)"
        >
          <div class="flex flex-wrap items-center gap-2">
            <span class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-bold" :class="statusClass(email.status)">
              <component :is="statusIcon(email.status)" class="h-3 w-3" />
              {{ statusLabel(email.status) }}
            </span>
            <span class="text-xs text-slate-500">{{ formatDate(email.sent_at || email.created_at) }}</span>
            <span v-if="email.attachments?.length" class="text-xs font-semibold text-slate-500">{{ email.attachments.length }} влож.</span>
          </div>
          <div class="mt-1 flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate text-sm font-bold">{{ email.subject }}</p>
              <p class="truncate text-xs text-slate-500 dark:text-slate-400">{{ email.recipient_email }}</p>
              <p v-if="email.error" class="mt-1 line-clamp-2 text-xs font-medium text-red-600 dark:text-red-300">{{ email.error }}</p>
            </div>
            <button v-if="email.error" type="button" class="shrink-0 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200" title="Скопировать ошибку" @click.stop="copyText(email.error || '')">
              <Copy class="h-4 w-4" />
            </button>
          </div>
        </article>
      </div>
    </div>
  </section>
</template>
