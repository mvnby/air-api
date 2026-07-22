<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { AlertTriangle, CheckCircle2, ExternalLink, RefreshCw, Search, Trash2, XCircle } from 'lucide-vue-next';
import { ManagerMailService } from '../client';
import type { BankReceiptResponse } from '../client';
import { getApiErrorMessage } from '../utils/api-errors';
import { confirmDialog, promptDialog } from '../services/ui-feedback';

type GroupOrderCandidate = {
  order_id?: number;
  title?: string | null;
  customer_name?: string | null;
  status?: string | null;
  total_amount?: number;
  total_payments?: number;
  balance_due?: number;
};

type GroupMatchMeta = {
  available?: boolean;
  is_exact?: boolean;
  selection_mode?: string | null;
  total_balance_due?: number;
  open_balance_due?: number;
  receipt_amount?: number;
  order_ids?: number[];
  orders?: GroupOrderCandidate[];
  open_order_ids?: number[];
  open_orders?: GroupOrderCandidate[];
};

const receipts = ref<BankReceiptResponse[]>([]);
const loading = ref(false);
const importing = ref(false);
const importingStatement = ref(false);
const actionId = ref<number | null>(null);
const error = ref('');
const notice = ref('');
const statementFile = ref<File | null>(null);
const page = ref(1);
const limit = ref(50);
const total = ref(0);
const status = ref('');
const payerUnp = ref('');
const orderId = ref('');
const expandedId = ref<number | null>(null);

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / limit.value)));

const statusOptions = [
  { value: '', label: 'Все' },
  { value: 'requires_review', label: 'Требуют проверки' },
  { value: 'matched', label: 'Разнесены' },
  { value: 'closed_orders', label: 'Закрытые заказы' },
  { value: 'non_order_income', label: 'Не CRM' },
  { value: 'void', label: 'Ошибочные' },
  { value: 'parse_failed', label: 'Ошибки парсинга' },
];

const statusLabel = (value?: string | null) => {
  switch (value) {
    case 'matched':
      return 'Разнесен';
    case 'requires_review':
      return 'Проверить';
    case 'closed_orders':
      return 'Закрытые заказы';
    case 'non_order_income':
      return 'Не CRM';
    case 'void':
      return 'Ошибочный';
    case 'parse_failed':
      return 'Не распознан';
    default:
      return value || 'Новый';
  }
};

const statusClass = (value?: string | null) => {
  switch (value) {
    case 'matched':
      return 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20';
    case 'requires_review':
      return 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20';
    case 'closed_orders':
      return 'bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-500/20';
    case 'non_order_income':
      return 'bg-violet-100 text-violet-700 border-violet-200 dark:bg-violet-500/10 dark:text-violet-300 dark:border-violet-500/20';
    case 'void':
      return 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-700/50 dark:text-slate-300 dark:border-slate-600';
    case 'parse_failed':
      return 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20';
    default:
      return 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-slate-700 dark:text-slate-300 dark:border-slate-600';
  }
};

const formatDate = (value?: string | null) => {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ru-BY', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
};

const formatMoneyValue = (amount?: number | null, currency = 'BYN') => {
  return `${new Intl.NumberFormat('ru-BY', { maximumFractionDigits: 2 }).format(Number(amount || 0))} ${currency}`;
};

const formatAmount = (receipt: BankReceiptResponse) => {
  return formatMoneyValue(receipt.amount, receipt.currency);
};

const candidateOrders = (receipt: BankReceiptResponse) => {
  const ids = receipt.match_meta?.candidate_order_ids;
  return Array.isArray(ids) ? ids.filter(Boolean) : [];
};

const groupMatch = (receipt: BankReceiptResponse): GroupMatchMeta | null => {
  const raw = receipt.match_meta?.group_match;
  return raw && typeof raw === 'object' ? raw as GroupMatchMeta : null;
};

const groupOrders = (receipt: BankReceiptResponse) => {
  const items = groupMatch(receipt)?.orders;
  return Array.isArray(items) ? items.filter((item) => item?.order_id) : [];
};

const groupOrderIds = (receipt: BankReceiptResponse) => {
  const ids = groupMatch(receipt)?.order_ids;
  if (Array.isArray(ids) && ids.length) return ids.map(Number).filter(Boolean);
  return groupOrders(receipt).map((item) => Number(item.order_id)).filter(Boolean);
};

const groupMatchLabel = (receipt: BankReceiptResponse) => {
  const match = groupMatch(receipt);
  if (!match) return '';
  if (match.selection_mode === 'exact_subset') return 'Подобрана часть открытых актов';
  if (match.is_exact) return 'Открытая задолженность совпадает';
  return 'Открытая задолженность по УНП';
};

const canAttachGroup = (receipt: BankReceiptResponse) => {
  const match = groupMatch(receipt);
  return Boolean(
    match?.available
    && match?.is_exact
    && groupOrderIds(receipt).length > 1
    && receipt.status !== 'matched'
    && !receipt.matched_payment_id,
  );
};

const loadReceipts = async () => {
  loading.value = true;
  error.value = '';
  try {
    const response = await ManagerMailService.listManagerBankReceipts(
      page.value,
      limit.value,
      status.value || undefined,
      payerUnp.value.trim() || undefined,
      orderId.value.trim() ? Number(orderId.value.trim()) : undefined,
    );
    receipts.value = response.items;
    total.value = response.total;
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    loading.value = false;
  }
};

const applyFilters = () => {
  page.value = 1;
  void loadReceipts();
};

const importNow = async () => {
  importing.value = true;
  error.value = '';
  notice.value = '';
  try {
    const result = await ManagerMailService.importManagerBankReceipts(50);
    notice.value = `Импорт: обработано ${result.processed}, создано ${result.created}, дублей ${result.duplicates}, ошибок ${result.failed}.`;
    await loadReceipts();
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    importing.value = false;
  }
};

const onStatementFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement;
  statementFile.value = input.files?.[0] || null;
};

const importStatement = async () => {
  if (!statementFile.value) {
    error.value = 'Выберите CSV-файл выписки.';
    return;
  }
  importingStatement.value = true;
  error.value = '';
  notice.value = '';
  try {
    const result = await ManagerMailService.importManagerBankStatement({ file: statementFile.value });
    const suspiciousIds = result.suspicious_receipt_ids?.length ? ` Подозрительные ID: ${result.suspicious_receipt_ids.join(', ')}.` : '';
    notice.value = `Выписка: кредитных строк ${result.credit_rows || 0}, создано ${result.created || 0}, совпало ${result.matched_existing || 0}, подозрительных ${result.suspicious || 0}.${suspiciousIds}`;
    await loadReceipts();
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    importingStatement.value = false;
  }
};

const attachGroup = async (receipt: BankReceiptResponse) => {
  const orders = groupOrders(receipt);
  const orderLines = orders.map((item) => {
    const title = item.title ? ` · ${item.title}` : '';
    return `#${item.order_id}${title}: ${formatMoneyValue(item.balance_due, receipt.currency)}`;
  });
  const confirmed = await confirmDialog({
    title: `Разнести поступление #${receipt.id}?`,
    description: [
      groupMatchLabel(receipt),
      '',
      ...orderLines,
      '',
      `Итого: ${formatMoneyValue(groupMatch(receipt)?.total_balance_due, receipt.currency)}`,
      groupMatch(receipt)?.selection_mode === 'exact_subset'
        ? `Всего открыто по УНП: ${formatMoneyValue(groupMatch(receipt)?.open_balance_due, receipt.currency)}`
        : '',
    ].join('\n'),
    confirmText: 'Разнести поступление',
    variant: 'warning',
  });
  if (!confirmed) return;

  actionId.value = receipt.id;
  error.value = '';
  notice.value = '';
  try {
    await ManagerMailService.attachManagerBankReceiptGroup(receipt.id, {
      order_ids: groupOrderIds(receipt),
      payment_type: 'postpayment',
    });
    notice.value = `Поступление #${receipt.id} разнесено по группе заказов.`;
    await loadReceipts();
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    actionId.value = null;
  }
};

const markVoid = async (receipt: BankReceiptResponse) => {
  const reason = await promptDialog({
    title: 'Пометить платёж ошибочным',
    inputLabel: 'Причина',
    initialValue: 'Отозван/ошибочный банковский платеж',
    inputKind: 'textarea',
    required: true,
    confirmText: 'Пометить ошибочным',
    variant: 'danger',
  });
  if (reason === null) return;
  actionId.value = receipt.id;
  error.value = '';
  notice.value = '';
  try {
    await ManagerMailService.patchManagerBankReceiptStatus(receipt.id, {
      status: 'void',
      reason: reason.trim() || 'Ошибочный банковский платеж',
    });
    notice.value = `Поступление #${receipt.id} помечено ошибочным.`;
    await loadReceipts();
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    actionId.value = null;
  }
};

const markClosedOrders = async (receipt: BankReceiptResponse) => {
  const reason = await promptDialog({
    title: 'Оплата закрытых заказов',
    inputLabel: 'Комментарий',
    initialValue: 'Оплата по актам/закрытым заказам',
    inputKind: 'textarea',
    required: true,
    confirmText: 'Сохранить статус',
    variant: 'warning',
  });
  if (reason === null) return;
  await updateReceiptStatus(receipt, 'closed_orders', reason.trim() || 'Оплата закрытых заказов', `Поступление #${receipt.id} помечено оплатой закрытых заказов.`);
};

const markNonOrderIncome = async (receipt: BankReceiptResponse) => {
  const reason = await promptDialog({
    title: 'Не относится к заказам',
    inputLabel: 'Причина',
    initialValue: 'Не CRM-поступление',
    inputKind: 'textarea',
    required: true,
    confirmText: 'Сохранить статус',
    variant: 'warning',
  });
  if (reason === null) return;
  await updateReceiptStatus(receipt, 'non_order_income', reason.trim() || 'Не относится к заказам', `Поступление #${receipt.id} помечено как не CRM.`);
};

const updateReceiptStatus = async (receipt: BankReceiptResponse, nextStatus: string, reason: string, successMessage: string) => {
  actionId.value = receipt.id;
  error.value = '';
  notice.value = '';
  try {
    await ManagerMailService.patchManagerBankReceiptStatus(receipt.id, {
      status: nextStatus,
      reason,
    });
    notice.value = successMessage;
    await loadReceipts();
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    actionId.value = null;
  }
};

const deleteReceipt = async (receipt: BankReceiptResponse) => {
  if (!await confirmDialog({
    title: `Удалить поступление #${receipt.id}?`,
    description: 'Удалить можно только непривязанное поступление.',
    confirmText: 'Удалить',
    variant: 'danger',
  })) return;
  actionId.value = receipt.id;
  error.value = '';
  notice.value = '';
  try {
    await ManagerMailService.deleteManagerBankReceipt(receipt.id);
    notice.value = `Поступление #${receipt.id} удалено.`;
    await loadReceipts();
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    actionId.value = null;
  }
};

const goToOrder = (orderIdValue: number) => {
  window.history.pushState({}, '', `/manager/orders/kanban?orderId=${orderIdValue}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const nextPage = () => {
  if (page.value >= totalPages.value) return;
  page.value += 1;
  void loadReceipts();
};

const prevPage = () => {
  if (page.value <= 1) return;
  page.value -= 1;
  void loadReceipts();
};

onMounted(loadReceipts);
</script>

<template>
  <div class="min-h-full bg-gray-50 p-6 dark:bg-slate-950">
    <div class="mx-auto max-w-7xl space-y-5">
      <header class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p class="text-sm font-medium text-teal-700 dark:text-teal-300">CRM платежи</p>
          <h1 class="text-2xl font-semibold text-gray-900 dark:text-slate-100">Банковские поступления</h1>
        </div>
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
          <label class="inline-flex min-h-10 items-center rounded-lg border border-gray-300 bg-white px-3 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800">
            <input class="sr-only" type="file" accept=".csv,text/csv" @change="onStatementFileChange" />
            {{ statementFile ? statementFile.name : 'Выбрать CSV' }}
          </label>
          <button
            class="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-teal-200 px-4 text-sm font-semibold text-teal-700 shadow-sm transition hover:bg-teal-50 disabled:opacity-60 dark:border-teal-500/30 dark:text-teal-200 dark:hover:bg-teal-500/10"
            :disabled="importingStatement"
            @click="importStatement"
          >
            <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': importingStatement }" />
            Сверить выписку
          </button>
          <button
            class="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-700 disabled:opacity-60"
            :disabled="importing"
            @click="importNow"
          >
            <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': importing }" />
            Проверить почту
          </button>
        </div>
      </header>

      <section class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <div class="grid gap-3 md:grid-cols-[1fr_1fr_1fr_auto]">
          <label class="block">
            <span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Статус</span>
            <select v-model="status" class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100">
              <option v-for="option in statusOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">УНП</span>
            <input v-model="payerUnp" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" placeholder="Например 192663084" />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Заказ</span>
            <input v-model="orderId" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" placeholder="ID заказа" />
          </label>
          <button class="mt-5 inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 transition hover:bg-gray-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800" @click="applyFilters">
            <Search class="h-4 w-4" />
            Найти
          </button>
        </div>
      </section>

      <div v-if="notice" class="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200">{{ notice }}</div>
      <div v-if="error" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200">{{ error }}</div>

      <section class="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <div class="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-slate-700">
          <p class="text-sm text-gray-600 dark:text-slate-300">Всего: <span class="font-semibold text-gray-900 dark:text-slate-100">{{ total }}</span></p>
          <div class="flex items-center gap-2 text-sm text-gray-500 dark:text-slate-400">
            <button class="rounded-lg border border-gray-300 px-3 py-1.5 disabled:opacity-40 dark:border-slate-700" :disabled="page <= 1" @click="prevPage">Назад</button>
            <span>{{ page }} / {{ totalPages }}</span>
            <button class="rounded-lg border border-gray-300 px-3 py-1.5 disabled:opacity-40 dark:border-slate-700" :disabled="page >= totalPages" @click="nextPage">Вперед</button>
          </div>
        </div>

        <div v-if="loading" class="flex items-center justify-center gap-2 py-16 text-gray-500 dark:text-slate-400">
          <RefreshCw class="h-5 w-5 animate-spin" />
          Загрузка
        </div>

        <div v-else-if="!receipts.length" class="py-16 text-center text-gray-500 dark:text-slate-400">Поступлений не найдено</div>

        <div v-else class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm dark:divide-slate-700">
            <thead class="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:bg-slate-900/70 dark:text-slate-400">
              <tr>
                <th class="px-4 py-3">Дата</th>
                <th class="px-4 py-3">Плательщик</th>
                <th class="px-4 py-3">Сумма</th>
                <th class="px-4 py-3">Статус</th>
                <th class="px-4 py-3">Заказ</th>
                <th class="px-4 py-3">Назначение</th>
                <th class="px-4 py-3 text-right">Действия</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100 dark:divide-slate-800">
              <template v-for="receipt in receipts" :key="receipt.id">
                <tr class="align-top hover:bg-gray-50 dark:hover:bg-slate-800/50">
                  <td class="whitespace-nowrap px-4 py-3 text-gray-600 dark:text-slate-300">
                    <div class="font-medium text-gray-900 dark:text-slate-100">#{{ receipt.id }}</div>
                    <div>{{ formatDate(receipt.received_at || receipt.created_at) }}</div>
                  </td>
                  <td class="px-4 py-3">
                    <div class="max-w-[300px] font-medium text-gray-900 dark:text-slate-100">{{ receipt.payer_name || '—' }}</div>
                    <div class="text-xs text-gray-500 dark:text-slate-400">УНП {{ receipt.payer_unp || '—' }}</div>
                    <div class="text-xs text-gray-500 dark:text-slate-400">Док. {{ receipt.payment_document_number || '—' }}</div>
                  </td>
                  <td class="whitespace-nowrap px-4 py-3 font-semibold text-gray-900 dark:text-slate-100">{{ formatAmount(receipt) }}</td>
                  <td class="px-4 py-3">
                    <span class="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold" :class="statusClass(receipt.status)">
                      <CheckCircle2 v-if="receipt.status === 'matched'" class="h-3.5 w-3.5" />
                      <AlertTriangle v-else-if="receipt.status === 'requires_review'" class="h-3.5 w-3.5" />
                      <CheckCircle2 v-else-if="receipt.status === 'closed_orders' || receipt.status === 'non_order_income'" class="h-3.5 w-3.5" />
                      <XCircle v-else-if="receipt.status === 'void'" class="h-3.5 w-3.5" />
                      {{ statusLabel(receipt.status) }}
                    </span>
                    <div v-if="receipt.match_meta?.manual_reason" class="mt-1 max-w-[220px] text-xs text-gray-500 dark:text-slate-400">{{ receipt.match_meta.manual_reason }}</div>
                  </td>
                  <td class="px-4 py-3">
                    <button
                      v-if="receipt.matched_order_id"
                      class="inline-flex items-center gap-1 text-sm font-semibold text-teal-700 hover:text-teal-900 dark:text-teal-300"
                      @click="goToOrder(receipt.matched_order_id)"
                    >
                      #{{ receipt.matched_order_id }}
                      <ExternalLink class="h-3.5 w-3.5" />
                    </button>
                    <div v-else-if="candidateOrders(receipt).length" class="flex flex-wrap gap-1">
                      <button
                        v-for="candidateId in candidateOrders(receipt)"
                        :key="candidateId"
                        class="rounded-md bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800 dark:bg-amber-500/10 dark:text-amber-200"
                        @click="goToOrder(Number(candidateId))"
                      >
                        #{{ candidateId }}
                      </button>
                    </div>
                    <span v-else class="text-gray-400">—</span>
                    <div
                      v-if="groupMatch(receipt)?.available"
                      class="mt-2 rounded-lg border px-2 py-1.5 text-xs"
                      :class="groupMatch(receipt)?.is_exact ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200' : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200'"
                    >
                      <div class="font-semibold">
                        {{ groupMatchLabel(receipt) }}:
                        {{ formatMoneyValue(groupMatch(receipt)?.total_balance_due, receipt.currency) }}
                      </div>
                      <div
                        v-if="groupMatch(receipt)?.selection_mode === 'exact_subset'"
                        class="mt-0.5 opacity-80"
                      >
                        Всего открыто по УНП: {{ formatMoneyValue(groupMatch(receipt)?.open_balance_due, receipt.currency) }}
                      </div>
                      <div class="mt-1 flex flex-wrap gap-1">
                        <button
                          v-for="item in groupOrders(receipt)"
                          :key="item.order_id"
                          class="rounded-md bg-white/70 px-1.5 py-0.5 font-semibold transition hover:bg-white dark:bg-slate-950/40 dark:hover:bg-slate-950/70"
                          @click="goToOrder(Number(item.order_id))"
                        >
                          #{{ item.order_id }} · {{ formatMoneyValue(item.balance_due, receipt.currency) }}
                        </button>
                      </div>
                      <div v-if="groupMatch(receipt)?.is_exact" class="mt-1 font-semibold">
                        Сумма поступления совпадает.
                      </div>
                      <button
                        v-if="canAttachGroup(receipt)"
                        class="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-emerald-500 dark:hover:bg-emerald-400"
                        :disabled="actionId === receipt.id"
                        @click.stop="attachGroup(receipt)"
                      >
                        <CheckCircle2 class="h-4 w-4" />
                        {{ actionId === receipt.id ? 'Разносим...' : 'Разнести по этим заказам' }}
                      </button>
                    </div>
                  </td>
                  <td class="px-4 py-3">
                    <button class="max-w-[360px] text-left text-gray-700 hover:text-gray-950 dark:text-slate-300 dark:hover:text-white" @click="expandedId = expandedId === receipt.id ? null : receipt.id">
                      {{ receipt.payment_purpose || receipt.parse_error || '—' }}
                    </button>
                  </td>
                  <td class="px-4 py-3 text-right">
                    <div class="flex justify-end gap-2">
                      <button
                        v-if="canAttachGroup(receipt)"
                        class="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-emerald-200 text-emerald-700 hover:bg-emerald-50 disabled:opacity-40 dark:border-emerald-500/30 dark:text-emerald-300 dark:hover:bg-emerald-500/10"
                        title="Разнести по группе заказов"
                        :disabled="actionId === receipt.id"
                        @click="attachGroup(receipt)"
                      >
                        <CheckCircle2 class="h-4 w-4" />
                      </button>
                      <button
                        class="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-sky-200 text-sky-700 hover:bg-sky-50 disabled:opacity-40 dark:border-sky-500/30 dark:text-sky-300 dark:hover:bg-sky-500/10"
                        title="Оплата закрытых заказов"
                        :disabled="actionId === receipt.id || receipt.status === 'closed_orders'"
                        @click="markClosedOrders(receipt)"
                      >
                        <CheckCircle2 class="h-4 w-4" />
                      </button>
                      <button
                        class="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-violet-200 text-violet-700 hover:bg-violet-50 disabled:opacity-40 dark:border-violet-500/30 dark:text-violet-300 dark:hover:bg-violet-500/10"
                        title="Не относится к заказам"
                        :disabled="actionId === receipt.id || receipt.status === 'non_order_income'"
                        @click="markNonOrderIncome(receipt)"
                      >
                        <AlertTriangle class="h-4 w-4" />
                      </button>
                      <button
                        class="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-40 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                        title="Ошибочный"
                        :disabled="actionId === receipt.id || receipt.status === 'void'"
                        @click="markVoid(receipt)"
                      >
                        <XCircle class="h-4 w-4" />
                      </button>
                      <button
                        class="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-40 dark:border-red-500/30 dark:text-red-300 dark:hover:bg-red-500/10"
                        title="Удалить"
                        :disabled="actionId === receipt.id || Boolean(receipt.matched_payment_id)"
                        @click="deleteReceipt(receipt)"
                      >
                        <Trash2 class="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
                <tr v-if="expandedId === receipt.id" class="bg-gray-50 dark:bg-slate-950/60">
                  <td colspan="7" class="px-4 py-4">
                    <div class="grid gap-4 text-sm md:grid-cols-2">
                      <div>
                        <div class="mb-2 font-semibold text-gray-900 dark:text-slate-100">Назначение</div>
                        <p class="whitespace-pre-wrap text-gray-700 dark:text-slate-300">{{ receipt.payment_purpose || '—' }}</p>
                      </div>
                      <div>
                        <div class="mb-2 font-semibold text-gray-900 dark:text-slate-100">Сырой текст</div>
                        <p class="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-white p-3 text-xs text-gray-600 dark:bg-slate-900 dark:text-slate-300">{{ receipt.raw_body }}</p>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>
