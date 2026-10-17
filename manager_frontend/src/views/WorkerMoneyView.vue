<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { workerMoneyApi as api, exactAmount, moneyCents, moneyConflict, type Currency, type MoneyWorkspace, type MoneyOverview, type MoneyRecipient, type MoneyEntry } from '../services/worker-money';
import { managerSession } from '../services/manager-session';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';
import { useDialogA11y } from '../composables/useDialogA11y';
import { getApiErrorMessage } from '../utils/api-errors';
const props = withDefaults(defineProps<{ management?: boolean }>(), { management: false });
const workspace = ref<MoneyWorkspace | null>(null), overview = ref<MoneyOverview | null>(null), selected = ref<number | null>(null), page = ref(1), loading = ref(false), busy = ref(false), error = ref(''), stale = ref(false);
const amount = ref(''), currency = ref<Currency>('BYN'), recipient = ref(''), recipients = ref<MoneyRecipient[]>([]), recipientPage = ref(0), recipientTotal = ref(0), recipientsLoading = ref(false), reason = ref('');
const draft = ref<{ label: string; send: () => PromiseLike<unknown> } | null>(null);
const dialogRef = ref<HTMLElement | null>(null), backButtonRef = ref<HTMLElement | null>(null);
useDialogA11y({ open: computed(() => draft.value !== null), dialogRef, initialFocusRef: backButtonRef, close: () => { if (!busy.value && !error.value) draft.value = null; } });
let generation = 0;
const context = computed(() => `${managerSession.isAuthenticated.value}:${managerSession.auth.value?.staff_user_id}:${managerStorefrontSelection.selectedTenantId.value}:${managerStorefrontSelection.selectedSlug.value}`);
const pages = computed(() => Math.max(1, Math.ceil((workspace.value?.total ?? overview.value?.total ?? 0) / 30)));
const canWrite = computed(() => !managerSession.auth.value?.demo_read_only);
const balance = computed(() => workspace.value?.balances.find(item => item.currency === currency.value));
const status: Record<MoneyEntry['status'], string> = { recorded: 'Получено', pending: 'Ждёт подтверждения', confirmed: 'Принято', rejected: 'Отклонено', cancelled: 'Отменено', reversed: 'Исправлено' };
const kind: Record<MoneyEntry['kind'], string> = { client_receipt: 'Получение от клиента', handover: 'Передача денег', receipt_reversal: 'Исправление получения' };
const dateLabel = (value: string) => new Date(value).toLocaleString('ru-BY');
const load = async () => {
  const token = ++generation; loading.value = true; recipientsLoading.value = false; error.value = ''; draft.value = null; stale.value = false; workspace.value = null; overview.value = null;
  try {
    if (props.management && selected.value === null) { const result = await api.overview(page.value); if (token === generation) overview.value = result; }
    else { const result = props.management ? await api.worker(selected.value!, page.value) : await api.own(page.value); if (token === generation) workspace.value = result; }
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause); }
  finally { if (token === generation) loading.value = false; }
};
const loadRecipients = async () => {
  if (recipientsLoading.value) return;
  const token = generation; recipientsLoading.value = true;
  try { const result = await api.recipients(recipientPage.value + 1); if (token === generation) { recipients.value.push(...result.items); recipientTotal.value = result.total; recipientPage.value = result.page; } }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause); }
  finally { if (token === generation) recipientsLoading.value = false; }
};
const openWorker = (id: number | null) => { selected.value = id; page.value = 1; void load(); };
const prepareHandover = () => {
  if (!workspace.value || draft.value || !canWrite.value) return;
  const value = exactAmount(amount.value), person = recipients.value.find(item => item.staff_user_id === Number(recipient.value));
  if (!value || !person || moneyCents(value)! > (moneyCents(balance.value?.available ?? '') ?? 0n)) { error.value = 'Выберите получателя и сумму не больше доступного остатка с точностью до копеек'; return; }
  const body = { idempotency_key: crypto.randomUUID(), expected_version: workspace.value.version, amount: value, currency: currency.value, recipient_staff_user_id: person.staff_user_id };
  error.value = ''; draft.value = { label: `Передать ${value} ${body.currency}: ${person.display_name}?`, send: () => api.handover(body) };
};
const prepareAction = (entry: MoneyEntry, action: 'cancel' | 'confirm' | 'reject' | 'reverse') => {
  if (!workspace.value || draft.value || !canWrite.value) return;
  const worker = selected.value!;
  const body = { idempotency_key: crypto.randomUUID(), expected_version: action === 'reverse' ? workspace.value.version : entry.version ?? 0 };
  const labels = { cancel: 'Отменить передачу', confirm: 'Подтвердить, что вы приняли', reject: 'Отклонить передачу', reverse: 'Исправить ошибочное получение' };
  if (action === 'reverse' && reason.value.trim().length < 3) { error.value = 'Укажите причину исправления (минимум 3 символа)'; return; }
  const correctionReason = reason.value.trim();
  error.value = ''; draft.value = { label: `${labels[action]} ${entry.amount} ${entry.currency}?`, send: () => action === 'cancel' ? api.cancel(entry.id, body) : action === 'reverse' ? api.reverse(worker, entry.id, { ...body, reason: correctionReason }) : api.action(worker, entry.id, action, body) };
};
const submit = async () => {
  if (!draft.value || busy.value || stale.value) return;
  const token = generation; busy.value = true; error.value = '';
  try { await draft.value.send(); if (token === generation) { amount.value = ''; reason.value = ''; await load(); } }
  catch (cause) { if (token === generation) { stale.value = moneyConflict(cause); error.value = stale.value ? 'Данные изменились. Обновите журнал и проверьте операцию.' : `${getApiErrorMessage(cause)}. Повторное подтверждение проверит эту же операцию.`; } }
  finally { if (token === generation || !draft.value) busy.value = false; }
};
watch(context, () => { ++generation; selected.value = null; page.value = 1; workspace.value = null; overview.value = null; draft.value = null; recipients.value = []; recipientPage.value = 0; recipientTotal.value = 0; recipientsLoading.value = false; amount.value = ''; recipient.value = ''; reason.value = ''; busy.value = false; if (managerSession.isAuthenticated.value) void load(); }, { immediate: true });
onBeforeUnmount(() => { ++generation; });
</script>
<template>
  <main class="mx-auto w-full max-w-5xl space-y-5 p-4 pb-12 sm:p-6" data-testid="worker-money">
    <header class="flex items-center justify-between gap-3"><div><h1 class="text-2xl font-bold">{{ management ? 'Деньги у сотрудников' : 'Мои деньги' }}</h1><p class="mt-1 text-sm text-gray-500">Деньги клиентов и передача в кассу</p></div><button type="button" class="rounded-lg border px-3 py-2 disabled:opacity-50" :disabled="busy || loading" @click="load">Обновить</button></header>
    <button v-if="management && selected !== null" type="button" class="text-brand-600" :disabled="busy" @click="openWorker(null)">← Все сотрудники</button>
    <p v-if="loading" role="status">Загружаем журнал…</p>
    <div v-if="error" role="alert" class="rounded-xl bg-red-50 p-4 text-sm text-red-800">{{ error }}</div>
    <template v-if="overview"><p v-if="!overview.items.length" class="p-4 text-gray-500">Операций пока нет</p><button v-for="worker in overview.items" :key="worker.worker_profile_id!" type="button" class="block w-full rounded-xl border p-4 text-left" @click="openWorker(worker.worker_profile_id)"><span class="font-semibold">{{ worker.display_name }}</span><span v-for="item in worker.balances" :key="item.currency" class="mt-2 block text-sm">На руках: {{ item.held }} {{ item.currency }} · Передаётся: {{ item.pending }} {{ item.currency }}</span></button></template>
    <template v-if="workspace">
      <h2 v-if="management" class="text-lg font-semibold">{{ workspace.display_name }}</h2>
      <div class="grid gap-3 sm:grid-cols-3"><section v-for="item in workspace.balances" :key="item.currency" class="rounded-xl border p-4"><h2 class="font-semibold">{{ item.currency }}</h2><p class="mt-2 text-xl font-bold">{{ item.held }} <span class="text-sm font-normal">на руках</span></p><p class="mt-1 text-sm">В передаче: {{ item.pending }}</p><p class="text-sm">Доступно передать: {{ item.available }}</p></section></div>
      <form v-if="!management && canWrite && !draft" class="space-y-3 rounded-xl border p-4" @submit.prevent="prepareHandover"><h2 class="font-semibold">Передать деньги</h2><div class="flex gap-2"><label class="flex-1 text-sm">Сумма<input v-model="amount" aria-label="Сумма передачи" inputmode="decimal" class="mt-1 block w-full rounded-lg border p-3 dark:bg-slate-800" /></label><label class="text-sm">Валюта<select v-model="currency" aria-label="Валюта передачи" class="mt-1 block rounded-lg border p-3 dark:bg-slate-800"><option>BYN</option><option>USD</option><option>EUR</option></select></label></div><label class="block text-sm">Кому передаёте<select v-model="recipient" aria-label="Получатель денег" class="mt-1 block w-full rounded-lg border p-3 dark:bg-slate-800" @focus="recipientPage === 0 && loadRecipients()"><option value="">Выберите сотрудника</option><option v-for="person in recipients" :key="person.staff_user_id" :value="String(person.staff_user_id)">{{ person.display_name }}</option></select></label><button v-if="recipientPage === 0 || recipients.length < recipientTotal" type="button" class="text-sm text-brand-600" :disabled="recipientsLoading" @click="loadRecipients">{{ recipientsLoading ? 'Загружаем…' : 'Загрузить получателей' }}</button><button type="submit" class="block rounded-lg bg-brand-600 px-4 py-3 text-white">Передать деньги</button><p class="text-xs text-gray-500">Деньги останутся на вас до подтверждения получателем.</p></form>
      <section aria-label="Журнал денег" class="space-y-3"><h2 class="font-semibold">Журнал</h2><p v-if="!workspace.items.length" class="text-sm text-gray-500">Операций пока нет</p><article v-for="entry in workspace.items" :key="`${entry.kind}:${entry.id}`" class="rounded-xl border p-4"><div class="flex flex-wrap justify-between gap-2"><h3 class="font-medium">{{ kind[entry.kind] }}</h3><span class="font-semibold tabular-nums">{{ entry.amount }} {{ entry.currency }}</span></div><p class="mt-1 text-sm">{{ status[entry.status] }}<span v-if="entry.recipient_name"> · {{ entry.recipient_name }}</span></p><p v-if="entry.order_id" class="mt-1 text-sm text-gray-500">Заказ №{{ entry.order_id }}<span v-if="entry.title"> · {{ entry.title }}</span></p><time class="mt-1 block text-xs text-gray-500">{{ dateLabel(entry.created_at) }}</time><div v-if="canWrite && !draft" class="mt-3 flex flex-wrap gap-3"><template v-if="entry.kind === 'handover' && entry.status === 'pending'"><button v-if="!management" type="button" class="text-sm text-brand-600" @click="prepareAction(entry, 'cancel')">Отменить передачу</button><button v-if="management && workspace.can_manage && entry.recipient_staff_user_id === managerSession.auth.value?.staff_user_id" type="button" class="text-sm text-brand-600" @click="prepareAction(entry, 'confirm')">Я принял деньги</button><button v-if="management && workspace.can_manage" type="button" class="text-sm text-red-700" @click="prepareAction(entry, 'reject')">Отклонить</button></template><div v-if="management && workspace.can_manage && entry.can_reverse" class="w-full space-y-2"><label class="block text-sm">Причина исправления<input v-model="reason" maxlength="500" aria-label="Причина исправления" class="mt-1 block w-full rounded-lg border p-2 dark:bg-slate-800" /></label><button type="button" class="text-sm text-red-700" @click="prepareAction(entry, 'reverse')">Исправить ошибочное получение</button></div></div></article></section>
    </template>
    <section v-if="draft" ref="dialogRef" tabindex="-1" role="dialog" aria-modal="true" aria-label="Подтверждение операции" class="!mt-0 fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"><div class="w-full max-w-md rounded-2xl bg-white p-5 dark:bg-slate-900"><p class="text-lg font-semibold">{{ draft.label }}</p><p v-if="error" role="alert" class="mt-3 text-sm text-red-700">{{ error }}</p><button type="button" class="mt-4 rounded-lg bg-brand-600 px-4 py-3 text-white disabled:opacity-50" :disabled="busy || stale" @click="submit">{{ busy ? 'Сохраняем…' : 'Подтверждаю' }}</button><button v-if="!error" ref="backButtonRef" type="button" class="ml-3 p-3" :disabled="busy" @click="draft = null">Назад</button><button v-else-if="!busy" type="button" class="ml-3 p-3 underline" @click="load">Обновить журнал</button></div></section>
    <nav v-if="pages > 1 && !draft" aria-label="Страницы журнала" class="flex items-center justify-center gap-4"><button type="button" class="rounded-lg border p-3 disabled:opacity-40" :disabled="page <= 1 || busy || loading" @click="page--; load()">Назад</button><span>{{ page }} / {{ pages }}</span><button type="button" class="rounded-lg border p-3 disabled:opacity-40" :disabled="page >= pages || busy || loading" @click="page++; load()">Далее</button></nav>
  </main>
</template>
