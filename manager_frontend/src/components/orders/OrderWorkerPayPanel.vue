<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue';
import { workerPayApi as api, type ManagerPayAgreement, type PayOrderWorkspace } from '../../services/worker-pay';
import { exactAmount, moneyCents, type Currency } from '../../services/worker-money';
import { managerSession } from '../../services/manager-session';
import { managerStorefrontSelection } from '../../services/manager-storefront-selection';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../../manager-capabilities';
import { useMoneyCommand } from '../../composables/useMoneyCommand';
import MoneyCommandDialog from '../worker-pay/MoneyCommandDialog.vue';
import { getApiErrorMessage } from '../../utils/api-errors';
const props = defineProps<{ orderId: number; contextVersion?: string; disabled?: boolean; beforeAction: () => Promise<boolean> }>();
const emit = defineEmits<{ busy: [value: boolean]; changed: [] }>();
const state = ref<PayOrderWorkspace | null>(null), loading = ref(false), preparing = ref(false), error = ref('');
const assignment = ref(''), amount = ref(''), currency = ref<Currency>('BYN'), costByn = ref(''), editing = ref<ManagerPayAgreement | null>(null), reason = ref('');
const scope = computed(() => `${props.orderId}:${managerSession.auth.value?.staff_user_id}:${managerStorefrontSelection.selectedTenantId.value}:${managerStorefrontSelection.selectedSlug.value}`);
const canRead = computed(() => hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.workerPayRead));
const canManage = computed(() => state.value?.can_manage && hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.workerPayManage) && !managerSession.auth.value?.demo_read_only);
let generation = 0;
let refreshRequested = false;
let activeScope = scope.value;
const load = async (preserveDraft = false) => { const request = ++generation; loading.value = true; if (!preserveDraft) { state.value = null; editing.value = null; } error.value = ''; try { const result = await api.order(props.orderId); if (request === generation) state.value = result; } catch (cause) { if (request === generation) error.value = getApiErrorMessage(cause); } finally { if (request === generation) loading.value = false; } };
const command = useMoneyCommand({ scope, allowed: () => Boolean(canManage.value && !props.disabled && !loading.value), beforeAction: props.beforeAction, onSuccess: async () => { refreshRequested = false; await load(); emit('changed'); } });
const { draft, busy, pending, error: commandError, stale } = command;
const blocked = computed(() => props.disabled || loading.value || preparing.value || pending.value || !canManage.value);
watch(() => pending.value || preparing.value, value => emit('busy', value), { flush: 'sync' });
const refreshContext = () => {
  if (scope.value !== activeScope || !refreshRequested || loading.value || preparing.value || pending.value || !canRead.value) return;
  refreshRequested = false;
  void load(true);
};
watch([scope, () => props.contextVersion], ([nextScope], previous) => {
  if (nextScope !== previous?.[0]) {
    activeScope = nextScope; refreshRequested = false; ++generation; state.value = null; preparing.value = false; assignment.value = ''; amount.value = ''; costByn.value = ''; reason.value = ''; if (canRead.value) void load();
  } else {
    refreshRequested = true;
    refreshContext();
  }
}, { immediate: true });
watch([loading, preparing, pending], refreshContext);
const refresh = () => { command.reset(); void load(); };
onScopeDispose(() => { refreshRequested = false; ++generation; emit('busy', false); });
const prepareAmount = async () => {
  if (blocked.value || !state.value) return;
  const value = exactAmount(amount.value), cost = currency.value === 'BYN' ? value : exactAmount(costByn.value);
  if (!value || !cost) { error.value = 'Укажите положительную сумму с точностью до копеек. Для валютного вознаграждения проверьте расход в BYN.'; return; }
  const current = state.value.candidates.find(item => item.assignment_id === Number(assignment.value)); const item = editing.value;
  if (!item && !current) { error.value = 'Выберите назначенную работу'; return; }
  const request = generation, orderId = props.orderId; preparing.value = true; error.value = '';
  try {
    const version = item ? (await api.worker(item.worker_profile_id)).version : current!.account_version;
    if (request !== generation) return;
    const body = { idempotency_key: crypto.randomUUID(), expected_version: version, amount: value, currency: currency.value, ...(currency.value !== 'BYN' ? { cost_byn_amount: cost } : {}) };
    command.begin(`${item ? 'Изменить' : 'Согласовать'} вознаграждение ${value} ${body.currency}?\nРасход по заказу: ${cost} BYN. Начисление подтверждается отдельно.`, () => item ? api.revise(item.worker_profile_id, item.id, { ...body, expected_agreement_version: item.version }) : api.agree(orderId, { ...body, assignment_id: current!.assignment_id }));
  } catch (cause) { if (request === generation) error.value = getApiErrorMessage(cause); } finally { if (request === generation) preparing.value = false; }
};
const action = async (item: ManagerPayAgreement, operation: 'accrue' | 'cancel') => {
  if (blocked.value) return;
  const why = reason.value.trim(); if (operation === 'cancel' && why.length < 3) { error.value = 'Укажите причину отмены (минимум 3 символа)'; return; }
  const request = generation; preparing.value = true; error.value = '';
  try { const current = await api.worker(item.worker_profile_id); if (request !== generation) return; const body = { idempotency_key: crypto.randomUUID(), expected_version: current.version, expected_agreement_version: item.version, ...(operation === 'cancel' ? { reason: why } : {}) }; command.begin(`${operation === 'accrue' ? 'Начислить' : 'Отменить'} ${item.amount} ${item.currency} за «${item.title}»?`, () => api.agreementAction(item.worker_profile_id, item.id, operation, body)); }
  catch (cause) { if (request === generation) error.value = getApiErrorMessage(cause); } finally { if (request === generation) preparing.value = false; }
};
const edit = (item: ManagerPayAgreement) => { editing.value = item; amount.value = item.amount; currency.value = item.currency as Currency; costByn.value = item.cost_byn_amount; };
const status = { agreed: 'Согласовано', accrued: 'Начислено', cancelled: 'Отменено' };
</script>
<template>
<section v-if="canRead" class="mt-4 space-y-4 rounded-xl border p-4" aria-label="Вознаграждения за работы"><header class="flex items-center justify-between gap-3"><h2 class="font-semibold">Вознаграждения за работы</h2><button type="button" class="min-h-10 text-sm text-brand-600" :disabled="pending || loading || preparing" @click="refresh">Обновить</button></header><p class="text-xs text-gray-500">Фиксированные суммы исполнителям. Деньги клиентов учитываются отдельно.</p><p v-if="loading || preparing" role="status" class="text-sm">Загружаем…</p><p v-if="error" role="alert" class="text-sm text-red-700">{{ error }} <button type="button" class="underline" :disabled="pending" @click="refresh">Обновить</button></p>
<template v-if="state"><p v-if="!state.agreements.length" class="text-sm text-gray-500">Вознаграждения пока не согласованы.</p><article v-for="item in state.agreements" :key="item.id" class="space-y-2 rounded-lg border p-3"><div class="flex flex-wrap justify-between gap-2"><div><h3 class="text-sm font-semibold">{{ item.title }}</h3><p class="text-xs text-gray-500">{{ state.candidates.find(person => person.worker_profile_id === item.worker_profile_id)?.display_name ?? `Исполнитель №${item.worker_profile_id}` }}</p></div><span class="font-semibold">{{ item.amount }} {{ item.currency }}</span></div><p class="text-xs text-gray-500">{{ status[item.status] }} · Выплачено {{ item.paid }} {{ item.currency }} · Расход {{ item.cost_byn_amount }} BYN</p><div v-if="canManage" class="flex flex-wrap gap-3"><button v-if="item.status === 'agreed'" type="button" class="min-h-10 text-sm text-brand-600" :disabled="blocked" @click="edit(item)">Изменить</button><button v-if="item.status === 'agreed'" type="button" class="min-h-10 text-sm text-brand-600" :disabled="blocked" @click="action(item, 'accrue')">Начислить</button><div v-if="item.status !== 'cancelled' && moneyCents(item.paid) === 0n" class="w-full"><label class="text-xs">Причина отмены<input v-model="reason" maxlength="500" aria-label="Причина отмены вознаграждения" class="mt-1 block w-full rounded-lg border bg-transparent p-2" :disabled="blocked" /></label><button type="button" class="mt-2 min-h-10 text-sm text-red-700" :disabled="blocked" @click="action(item, 'cancel')">Отменить вознаграждение</button></div></div></article>
<form v-if="canManage" class="space-y-3" @submit.prevent="prepareAmount"><h3 class="text-sm font-semibold">{{ editing ? 'Изменить вознаграждение' : 'Согласовать вознаграждение' }}</h3><label v-if="!editing" class="block text-xs">Назначенная работа<select v-model="assignment" aria-label="Работа для вознаграждения" class="mt-1 w-full rounded-lg border bg-transparent p-3" :disabled="blocked"><option value="">Выберите работу</option><option v-for="person in state.candidates" :key="person.assignment_id" :value="String(person.assignment_id)">{{ person.display_name }} · {{ person.title }}</option></select></label><div class="grid grid-cols-[1fr_6rem] gap-3"><label class="text-xs">Сумма<input v-model="amount" aria-label="Вознаграждение за работу" inputmode="decimal" class="mt-1 w-full rounded-lg border bg-transparent p-3" :disabled="blocked" /></label><label class="text-xs">Валюта<select v-model="currency" aria-label="Валюта вознаграждения" class="mt-1 w-full rounded-lg border bg-transparent p-3" :disabled="blocked"><option>BYN</option><option>USD</option><option>EUR</option></select></label></div><label v-if="currency !== 'BYN'" class="block text-xs">Проверенный расход в BYN<input v-model="costByn" aria-label="Расход вознаграждения в BYN" inputmode="decimal" class="mt-1 w-full rounded-lg border bg-transparent p-3" :disabled="blocked" /></label><p v-else class="text-xs text-gray-500">Расход в BYN равен сумме вознаграждения.</p><div class="flex gap-3"><button type="submit" class="min-h-10 rounded-lg bg-brand-600 px-4 text-sm text-white disabled:opacity-50" :disabled="blocked">Проверить сумму</button><button v-if="editing" type="button" class="text-sm" :disabled="blocked" @click="editing = null">Отмена изменения</button></div></form></template>
<MoneyCommandDialog :label="draft?.label ?? null" :busy="busy" :error="commandError" :stale="stale" @confirm="command.submit" @close="command.reset" @refresh="refresh" />
</section>
</template>
