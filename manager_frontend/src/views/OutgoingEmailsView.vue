<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { AlertTriangle, CheckCircle2, Clock3, Copy, ExternalLink, Mail, RefreshCw, Search, XCircle } from 'lucide-vue-next';
import { ManagerMailService } from '../client';
import type { OutgoingEmailResponse } from '../client';
import OutgoingEmailDrawer from '../components/mail/OutgoingEmailDrawer.vue';
import { getApiErrorMessage } from '../utils/api-errors';

const emails = ref<OutgoingEmailResponse[]>([]);
const loading = ref(false);
const actionId = ref<number | null>(null);
const error = ref('');
const toast = ref('');
const toastType = ref<'success' | 'error'>('success');
const page = ref(1);
const limit = ref(50);
const total = ref(0);
const selectedEmailId = ref<number | null>(null);
const drawerOpen = ref(false);

const filters = ref({
  status: '',
  orderId: '',
  customerId: '',
  recipient: '',
  q: '',
  dateFrom: '',
  dateTo: '',
});

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / limit.value)));

const statusOptions = [
  { value: '', label: 'Все статусы' },
  { value: 'sent', label: 'Отправлено' },
  { value: 'failed', label: 'Ошибка' },
  { value: 'pending', label: 'В очереди' },
];

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
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
};

const dateStart = (value: string) => (value ? `${value}T00:00:00` : undefined);
const dateEnd = (value: string) => (value ? `${value}T23:59:59` : undefined);

const setToast = (message: string, type: 'success' | 'error' = 'success') => {
  toast.value = message;
  toastType.value = type;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2600);
};

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
  setToast(message);
};

const openEmail = (email: OutgoingEmailResponse) => {
  selectedEmailId.value = email.id;
  drawerOpen.value = true;
};

const openOrder = (orderId?: number | null) => {
  if (!orderId) return;
  window.history.pushState({}, '', `/manager/orders/kanban?orderId=${orderId}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const loadEmails = async () => {
  loading.value = true;
  error.value = '';
  try {
    const response = await ManagerMailService.listManagerOutgoingEmails(
      page.value,
      limit.value,
      filters.value.status || undefined,
      filters.value.orderId ? Number(filters.value.orderId) : undefined,
      filters.value.customerId ? Number(filters.value.customerId) : undefined,
      filters.value.recipient.trim() || undefined,
      filters.value.q.trim() || undefined,
      dateStart(filters.value.dateFrom),
      dateEnd(filters.value.dateTo),
    );
    emails.value = response.items || [];
    total.value = response.total;
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    loading.value = false;
  }
};

const applyFilters = () => {
  page.value = 1;
  void loadEmails();
};

const resetFilters = () => {
  filters.value = {
    status: '',
    orderId: '',
    customerId: '',
    recipient: '',
    q: '',
    dateFrom: '',
    dateTo: '',
  };
  page.value = 1;
  void loadEmails();
};

const retryEmail = async (email: OutgoingEmailResponse) => {
  actionId.value = email.id;
  try {
    const result = await ManagerMailService.retryManagerOutgoingEmail(email.id);
    setToast(
      result.status === 'sent'
        ? 'Повторная отправка выполнена'
        : `Повторная отправка завершилась ошибкой: ${result.error || 'см. историю'}`,
      result.status === 'sent' ? 'success' : 'error',
    );
    await loadEmails();
    if (selectedEmailId.value === email.id) drawerOpen.value = true;
  } catch (err) {
    setToast(getApiErrorMessage(err), 'error');
  } finally {
    actionId.value = null;
  }
};

const changePage = (nextPage: number) => {
  page.value = Math.min(Math.max(1, nextPage), totalPages.value);
  void loadEmails();
};

onMounted(() => {
  const params = new URLSearchParams(window.location.search);
  const orderId = params.get('orderId');
  const status = params.get('status');
  if (orderId) filters.value.orderId = orderId;
  if (status) filters.value.status = status;
  void loadEmails();
});
</script>

<template>
  <div class="min-h-screen bg-slate-50 px-4 py-6 text-slate-900 dark:bg-slate-950 dark:text-slate-100 sm:px-6 lg:px-8">
    <OutgoingEmailDrawer
      v-model="drawerOpen"
      :email-id="selectedEmailId"
      @retry="loadEmails"
      @toast="setToast($event.message, $event.type || 'success')"
    />

    <div class="mx-auto max-w-7xl space-y-5">
      <header class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p class="text-xs font-bold uppercase tracking-[0.22em] text-teal-700 dark:text-teal-300">Почта</p>
            <h1 class="mt-1 flex items-center gap-2 text-2xl font-bold">
              <Mail class="h-6 w-6 text-teal-600" />
              Исходящие
            </h1>
            <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">CRM-история отправок. Яндекс “Отправленные” не считается источником истины.</p>
          </div>
          <button
            type="button"
            class="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
            :disabled="loading"
            @click="loadEmails"
          >
            <RefreshCw class="h-4 w-4" :class="loading ? 'animate-spin' : ''" />
            Обновить
          </button>
        </div>
      </header>

      <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div class="grid gap-3 md:grid-cols-4 xl:grid-cols-8">
          <label class="space-y-1">
            <span class="text-xs font-bold uppercase tracking-wide text-slate-500">Статус</span>
            <select v-model="filters.status" class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
              <option v-for="option in statusOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="space-y-1">
            <span class="text-xs font-bold uppercase tracking-wide text-slate-500">Заказ</span>
            <input v-model="filters.orderId" type="number" min="1" class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" placeholder="ID" />
          </label>
          <label class="space-y-1">
            <span class="text-xs font-bold uppercase tracking-wide text-slate-500">Клиент</span>
            <input v-model="filters.customerId" type="number" min="1" class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" placeholder="ID" />
          </label>
          <label class="space-y-1 md:col-span-2">
            <span class="text-xs font-bold uppercase tracking-wide text-slate-500">Получатель</span>
            <input v-model="filters.recipient" class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" placeholder="client@example.com" />
          </label>
          <label class="space-y-1">
            <span class="text-xs font-bold uppercase tracking-wide text-slate-500">С даты</span>
            <input v-model="filters.dateFrom" type="date" class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
          </label>
          <label class="space-y-1">
            <span class="text-xs font-bold uppercase tracking-wide text-slate-500">По дату</span>
            <input v-model="filters.dateTo" type="date" class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
          </label>
          <label class="space-y-1 md:col-span-2 xl:col-span-1">
            <span class="text-xs font-bold uppercase tracking-wide text-slate-500">Поиск</span>
            <input v-model="filters.q" class="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" placeholder="тема / email" />
          </label>
        </div>
        <div class="mt-4 flex flex-wrap gap-2">
          <button type="button" class="inline-flex items-center gap-2 rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-teal-700" @click="applyFilters">
            <Search class="h-4 w-4" />
            Найти
          </button>
          <button type="button" class="rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800" @click="resetFilters">
            Сбросить
          </button>
        </div>
      </section>

      <section class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div class="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <p class="text-sm font-semibold">Всего: {{ total }}</p>
          <div class="flex items-center gap-2">
            <button type="button" class="rounded-xl border border-slate-200 px-3 py-1.5 text-sm font-semibold disabled:opacity-50 dark:border-slate-700" :disabled="page <= 1 || loading" @click="changePage(page - 1)">Назад</button>
            <span class="text-sm font-medium">{{ page }} / {{ totalPages }}</span>
            <button type="button" class="rounded-xl border border-slate-200 px-3 py-1.5 text-sm font-semibold disabled:opacity-50 dark:border-slate-700" :disabled="page >= totalPages || loading" @click="changePage(page + 1)">Вперед</button>
          </div>
        </div>

        <div v-if="error" class="m-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          {{ error }}
        </div>

        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
            <thead class="bg-slate-50 text-xs font-bold uppercase tracking-wide text-slate-500 dark:bg-slate-950/60">
              <tr>
                <th class="px-4 py-3 text-left">Создано</th>
                <th class="px-4 py-3 text-left">Отправлено</th>
                <th class="px-4 py-3 text-left">Статус</th>
                <th class="px-4 py-3 text-left">Получатель</th>
                <th class="px-4 py-3 text-left">Клиент</th>
                <th class="px-4 py-3 text-left">Заказ</th>
                <th class="px-4 py-3 text-left">Тема</th>
                <th class="px-4 py-3 text-left">Ошибка</th>
                <th class="px-4 py-3 text-right">Действия</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
              <tr v-if="loading">
                <td colspan="9" class="px-4 py-8 text-center text-slate-500">Загружаю исходящие...</td>
              </tr>
              <tr v-else-if="!emails.length">
                <td colspan="9" class="px-4 py-8 text-center text-slate-500">Писем не найдено.</td>
              </tr>
              <tr v-for="email in emails" v-else :key="email.id" class="align-top hover:bg-slate-50/70 dark:hover:bg-slate-800/40">
                <td class="whitespace-nowrap px-4 py-3 text-slate-600 dark:text-slate-300">{{ formatDate(email.created_at) }}</td>
                <td class="whitespace-nowrap px-4 py-3 text-slate-600 dark:text-slate-300">{{ formatDate(email.sent_at) }}</td>
                <td class="px-4 py-3">
                  <span class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold" :class="statusClass(email.status)">
                    <component :is="statusIcon(email.status)" class="h-3.5 w-3.5" />
                    {{ statusLabel(email.status) }}
                  </span>
                </td>
                <td class="max-w-[220px] break-all px-4 py-3 font-medium">{{ email.recipient_email }}</td>
                <td class="max-w-[180px] px-4 py-3">
                  <span class="line-clamp-2">{{ email.customer_name || (email.customer_id ? `#${email.customer_id}` : '—') }}</span>
                </td>
                <td class="px-4 py-3">
                  <button v-if="email.order_id" type="button" class="inline-flex items-center gap-1 font-bold text-teal-700 hover:text-teal-900 dark:text-teal-300" @click="openOrder(email.order_id)">
                    #{{ email.order_id }}
                    <ExternalLink class="h-3.5 w-3.5" />
                  </button>
                  <span v-else>—</span>
                </td>
                <td class="max-w-[260px] px-4 py-3">
                  <button type="button" class="line-clamp-2 text-left font-semibold hover:text-teal-700 dark:hover:text-teal-300" @click="openEmail(email)">
                    {{ email.subject }}
                  </button>
                </td>
                <td class="max-w-[260px] px-4 py-3">
                  <div v-if="email.error" class="flex items-start gap-2">
                    <p class="line-clamp-3 min-w-0 text-xs font-medium text-red-600 dark:text-red-300">{{ email.error }}</p>
                    <button type="button" class="shrink-0 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200" title="Скопировать ошибку" @click="copyText(email.error || '', 'Ошибка скопирована')">
                      <Copy class="h-4 w-4" />
                    </button>
                  </div>
                  <span v-else class="text-slate-400">—</span>
                </td>
                <td class="px-4 py-3 text-right">
                  <div class="inline-flex items-center justify-end gap-1">
                    <button type="button" class="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800" @click="openEmail(email)">
                      Открыть
                    </button>
                    <button
                      v-if="email.status === 'failed'"
                      type="button"
                      class="inline-flex items-center gap-1 rounded-lg border border-teal-200 px-2.5 py-1.5 text-xs font-semibold text-teal-700 hover:bg-teal-50 disabled:opacity-60 dark:border-teal-500/30 dark:text-teal-300 dark:hover:bg-teal-500/10"
                      :disabled="actionId === email.id"
                      @click="retryEmail(email)"
                    >
                      <RefreshCw class="h-3.5 w-3.5" :class="actionId === email.id ? 'animate-spin' : ''" />
                      Retry
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <Transition name="fade">
      <div
        v-if="toast"
        class="fixed right-6 top-6 z-[120] rounded-xl px-5 py-3 text-sm font-semibold text-white shadow-2xl"
        :class="toastType === 'success' ? 'bg-teal-600' : 'bg-red-600'"
      >
        {{ toast }}
      </div>
    </Transition>
  </div>
</template>
